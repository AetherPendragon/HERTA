"""
知识库检索模块（增强版）

负责从知识库中检索相关信息：
- 加载索引和元数据
- 执行向量检索、BM25检索、融合检索
- 支持Query改写和精排
- 返回结构化的检索结果
"""

import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
import numpy as np

from herta.generator.schemas import RetrievedChunk
from herta.generator.reranker import RerankedChunk
from herta.kb.store import VectorStore
from herta.kb.hybrid_store import HybridIndexStore
from herta.kb.schemas import Chunk
from herta.llm.client import BigModelClient
from herta.logging import get_logger

logger = get_logger(__name__)


class KnowledgeRetriever:
    """
    知识库检索器（基础版）

    从源协议知识库中检索与查询相关的信息片段
    """

    def __init__(
        self,
        kb_dir: Path,
        llm_client: Optional[BigModelClient] = None,
        enable_fusion: bool = False,
        fusion_alpha: float = 0.6,
    ):
        """
        初始化知识库检索器

        Args:
            kb_dir: 知识库目录路径
            llm_client: LLM 客户端实例，用于生成 query embedding
            enable_fusion: 是否启用融合检索（Vector + BM25）
            fusion_alpha: 融合权重（向量权重，1-alpha为BM25权重）
        """
        self.kb_dir = Path(kb_dir)
        self.llm_client = llm_client or BigModelClient()
        self.enable_fusion = enable_fusion
        self.fusion_alpha = fusion_alpha

        # 加载知识库组件
        self.vector_store: Optional[VectorStore] = None
        self.hybrid_store: Optional[HybridIndexStore] = None
        self.chunks: Dict[str, Chunk] = {}  # chunk_id -> Chunk
        self.meta: Optional[Dict[str, Any]] = None

        self._loaded = False

    def load(self) -> None:
        """
        加载知识库文件
        """
        if self._loaded:
            return

        logger.info(f"加载知识库: {self.kb_dir}")

        # 1. 加载元数据
        meta_path = self.kb_dir / "meta.json"
        if meta_path.exists():
            with open(meta_path, 'r', encoding='utf-8') as f:
                self.meta = json.load(f)
            logger.debug(f"加载元数据: source={self.meta.get('source')}, chunks={self.meta.get('chunk_count')}")
        else:
            logger.warning(f"元数据文件不存在: {meta_path}")

        # 2. 加载 chunks
        chunks_path = self.kb_dir / "chunks.jsonl"
        if chunks_path.exists():
            self._load_chunks(chunks_path)
        else:
            raise FileNotFoundError(f"chunks 文件不存在: {chunks_path}")

        # 3. 加载索引
        if self.enable_fusion:
            # 尝试加载融合索引
            try:
                self._load_hybrid_index()
            except Exception as e:
                logger.warning(f"融合索引加载失败: {e}，降级到纯向量检索")
                self.enable_fusion = False
                self._load_vector_index()
        else:
            self._load_vector_index()

        self._loaded = True
        logger.info(f"知识库加载完成: {len(self.chunks)} 个 chunks")

    def _load_vector_index(self) -> None:
        """加载纯向量索引"""
        index_path = self.kb_dir / "vector.index"
        if index_path.exists():
            self.vector_store = VectorStore(
                dimension=self.meta.get("embedding_dimensions", 1024) if self.meta else 1024,
                metric="ip",
            )
            self.vector_store.load(self.kb_dir)
            logger.info(f"加载向量索引: {self.vector_store.vector_count} 个向量")
        else:
            raise FileNotFoundError(f"向量索引不存在: {index_path}")

    def _load_hybrid_index(self) -> None:
        """加载融合索引"""
        self.hybrid_store = HybridIndexStore(
            vector_dimension=self.meta.get("embedding_dimensions", 1024) if self.meta else 1024,
            vector_metric="ip",
        )
        self.hybrid_store.load(self.kb_dir)
        logger.info(f"加载融合索引: vector={self.hybrid_store.vector_store.vector_count}, "
                    f"bm25={self.hybrid_store.bm25_index.doc_count}")

    def _load_chunks(self, chunks_path: Path) -> None:
        """加载 chunks.jsonl 文件"""
        logger.debug(f"加载 chunks: {chunks_path}")

        count = 0
        with open(chunks_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    chunk = Chunk.from_dict(data)
                    self.chunks[chunk.chunk_id] = chunk
                    count += 1
                except json.JSONDecodeError as e:
                    logger.warning(f"解析 chunk 失败: {e}, line={line[:100]}...")
                except Exception as e:
                    logger.warning(f"加载 chunk 失败: {e}")

        logger.debug(f"加载了 {count} 个 chunks")

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_score: Optional[float] = None,
        use_fusion: Optional[bool] = None,
        context_type: str = "handler",
    ) -> List[RetrievedChunk]:
        """
        检索相关知识库片段（增强版）

        Args:
            query: 查询文本
            top_k: 返回的最相似结果数量
            min_score: 最小相似度阈值（可选）
            use_fusion: 强制使用/禁用融合检索（None则使用初始化设置）
            context_type: 上下文类型（用于融合检索的日志）

        Returns:
            RetrievedChunk 列表，按相似度降序排列
        """
        # 确定是否使用融合检索
        should_use_fusion = use_fusion if use_fusion is not None else self.enable_fusion

        if should_use_fusion and self.hybrid_store:
            return self._fusion_retrieve(query, top_k, min_score, context_type)
        else:
            return self._vector_retrieve(query, top_k, min_score)

    def _vector_retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_score: Optional[float] = None,
    ) -> List[RetrievedChunk]:
        """纯向量检索"""
        if not self._loaded:
            self.load()

        logger.info(f"执行向量检索: query='{query[:50]}...', top_k={top_k}")

        # 1. 生成 query embedding
        try:
            query_vector = self.llm_client.embed_query(query)
            logger.debug(f"Query embedding 生成完成: dimension={len(query_vector)}")
        except Exception as e:
            logger.error(f"生成 query embedding 失败: {e}")
            raise

        # 2. 向量检索
        try:
            indices, scores = self.vector_store.search(
                query_vector=np.array(query_vector),
                top_k=top_k,
            )
            logger.debug(f"向量检索完成: 返回 {len(indices)} 个结果")
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            raise

        return self._assemble_results(indices, scores, min_score, retrieval_type="vector")

    def _fusion_retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_score: Optional[float] = None,
        context_type: str = "handler",
    ) -> List[RetrievedChunk]:
        """融合检索（Vector + BM25）"""
        if not self._loaded:
            self.load()

        logger.info(f"执行融合检索: query='{query[:50]}...', alpha={self.fusion_alpha}, top_k={top_k}")

        # 1. 生成 query embedding
        try:
            query_vector = self.llm_client.embed_query(query)
        except Exception as e:
            logger.error(f"生成 query embedding 失败: {e}")
            raise

        # 2. 融合检索
        fusion_results = self.hybrid_store.fusion_search(
            query=query,
            query_vector=np.array(query_vector),
            top_k=top_k,
            initial_k=20,  # 每种检索召回20个
            alpha=self.fusion_alpha,
        )

        # 3. 组装结果
        results = []
        for item in fusion_results:
            chunk_id = item.chunk_id
            chunk = self.chunks.get(chunk_id)

            if chunk is None:
                continue

            # 应用分数阈值（使用融合分数）
            if min_score is not None and item.fusion_score < min_score:
                continue

            retrieved = RetrievedChunk(
                chunk_id=chunk.chunk_id,
                source=chunk.source,
                file=chunk.file,
                kind=chunk.kind,
                section=chunk.section,
                text=chunk.text,
                score=item.fusion_score,  # 使用融合分数
                token_count=chunk.token_count,
                metadata={
                    **chunk.metadata,
                    'vector_score': item.vector_score,
                    'bm25_score': item.bm25_score,
                    'fusion_alpha': self.fusion_alpha,
                },
            )
            results.append(retrieved)

        logger.info(f"融合检索完成: 返回 {len(results)} 个 chunks")
        for i, r in enumerate(results[:3], 1):
            meta = r.metadata
            logger.debug(f"  Top {i}: {r.chunk_id} (fusion={r.score:.3f}, "
                        f"vector={meta.get('vector_score', 0):.3f}, "
                        f"bm25={meta.get('bm25_score', 0):.3f})")

        return results

    def _assemble_results(
        self,
        indices: List[int],
        scores: List[float],
        min_score: Optional[float],
        retrieval_type: str = "vector",
    ) -> List[RetrievedChunk]:
        """组装检索结果"""
        if not indices:
            logger.warning("检索未返回任何结果")
            return []

        results = []
        for idx, score in zip(indices, scores):
            chunk_id = self.vector_store.get_chunk_id_by_index(idx)
            if chunk_id is None:
                continue

            chunk = self.chunks.get(chunk_id)
            if chunk is None:
                continue

            # 应用分数阈值
            if min_score is not None and score < min_score:
                continue

            retrieved = RetrievedChunk(
                chunk_id=chunk.chunk_id,
                source=chunk.source,
                file=chunk.file,
                kind=chunk.kind,
                section=chunk.section,
                text=chunk.text,
                score=float(score),
                token_count=chunk.token_count,
                metadata={
                    **chunk.metadata,
                    'retrieval_type': retrieval_type,
                },
            )
            results.append(retrieved)

        logger.info(f"{retrieval_type}检索完成: 返回 {len(results)} 个 chunks")
        return results

    def get_source_info(self) -> Dict[str, Any]:
        """获取知识库源信息"""
        if not self._loaded:
            self.load()

        return {
            "source": self.meta.get("source") if self.meta else None,
            "chunk_count": len(self.chunks),
            "vector_count": self.vector_store.vector_count if self.vector_store else 0,
            "embedding_model": self.meta.get("embedding_model") if self.meta else None,
            "chunk_strategy": self.meta.get("chunk_strategy") if self.meta else None,
            "fusion_enabled": self.enable_fusion,
            "fusion_alpha": self.fusion_alpha if self.enable_fusion else None,
        }


class FusionKnowledgeRetriever(KnowledgeRetriever):
    """
    融合检索器（专门用于融合检索的便捷类）

    继承自KnowledgeRetriever，默认启用融合检索
    """

    def __init__(
        self,
        kb_dir: Path,
        llm_client: Optional[BigModelClient] = None,
        fusion_alpha: float = 0.6,
    ):
        """
        初始化融合检索器

        Args:
            kb_dir: 知识库目录路径
            llm_client: LLM客户端
            fusion_alpha: 融合权重（向量权重，默认0.6）
        """
        super().__init__(
            kb_dir=kb_dir,
            llm_client=llm_client,
            enable_fusion=True,
            fusion_alpha=fusion_alpha,
        )

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        context_type: str = "handler",
        min_score: Optional[float] = None,
    ) -> List[RetrievedChunk]:
        """
        执行融合检索

        Args:
            query: 查询文本
            top_k: 返回结果数量
            context_type: 上下文类型
            min_score: 最小分数阈值

        Returns:
            RetrievedChunk列表
        """
        return self._fusion_retrieve(query, top_k, min_score, context_type)


def retrieve_from_kb(
    kb_dir: str,
    query: str,
    top_k: int = 5,
    use_fusion: bool = False,
    fusion_alpha: float = 0.6,
) -> List[RetrievedChunk]:
    """
    便捷函数：从知识库检索

    Args:
        kb_dir: 知识库目录路径
        query: 查询文本
        top_k: 返回结果数量
        use_fusion: 是否使用融合检索
        fusion_alpha: 融合权重（当use_fusion=True时有效）

    Returns:
        RetrievedChunk 列表

    Example:
        >>> results = retrieve_from_kb("data/kb/gdwx", "协议配置字段", use_fusion=True)
        >>> for r in results:
        ...     print(f"{r.chunk_id}: {r.text[:100]}...")
    """
    retriever = KnowledgeRetriever(
        Path(kb_dir),
        enable_fusion=use_fusion,
        fusion_alpha=fusion_alpha,
    )
    return retriever.retrieve(query, top_k=top_k)
