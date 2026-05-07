"""
混合索引存储模块

同时管理向量索引和BM25索引，提供融合检索能力
"""

import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path
from dataclasses import dataclass

from herta.kb.store import VectorStore
from herta.kb.bm25_index import BM25Index
from herta.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FusionResult:
    """融合检索结果"""
    chunk_id: str
    fusion_score: float
    vector_score: float
    vector_norm: float
    bm25_score: float
    bm25_norm: float
    rank: int


class HybridIndexStore:
    """
    融合索引存储
    
    同时管理向量索引和BM25索引，提供融合检索能力
    """
    
    def __init__(
        self,
        vector_dimension: int = 1024,
        vector_metric: str = "ip",
        bm25_k1: float = 1.5,
        bm25_b: float = 0.75,
    ):
        """
        初始化混合索引存储
        
        Args:
            vector_dimension: 向量维度
            vector_metric: 向量距离度量（ip/l2）
            bm25_k1: BM25参数
            bm25_b: BM25参数
        """
        self.vector_store = VectorStore(
            dimension=vector_dimension,
            metric=vector_metric,
        )
        self.bm25_index = BM25Index(k1=bm25_k1, b=bm25_b)
        
        logger.debug(f"HybridIndexStore初始化: vector_dim={vector_dimension}")
    
    def build(
        self,
        chunks: List[Any],  # List[Chunk]
        embeddings: np.ndarray,
    ) -> None:
        """
        同时构建两种索引
        
        Args:
            chunks: Chunk列表
            embeddings: 向量数组 (n, dimension)
        """
        logger.info(f"开始构建混合索引: {len(chunks)} chunks, embeddings shape={embeddings.shape}")
        
        # 1. 构建向量索引
        self.vector_store.create_index()
        self.vector_store.add_vectors(embeddings, [c.chunk_id for c in chunks])
        
        # 2. 构建BM25索引
        self.bm25_index.build(chunks)
        
        logger.info("混合索引构建完成")
    
    def fusion_search(
        self,
        query: str,
        query_vector: np.ndarray,
        top_k: int = 5,
        initial_k: int = 20,
        alpha: float = 0.6,           # 向量权重
    ) -> List[FusionResult]:
        """
        融合检索（主入口）
        
        流程：
        1. 两种检索各自召回initial_k个候选
        2. 归一化分数
        3. 加权融合
        4. 返回top_k结果
        
        Args:
            query: 原始查询文本
            query_vector: 查询向量
            top_k: 最终返回结果数
            initial_k: 每种检索的初始召回数
            alpha: 向量检索权重（0-1），1-alpha为BM25权重
        
        Returns:
            融合后的结果列表
        """
        logger.debug(f"融合检索: query='{query[:30]}...', alpha={alpha}")
        
        # 1. 向量检索
        vector_results = self._vector_search(query_vector, initial_k)
        
        # 2. BM25检索
        bm25_results = self._bm25_search(query, initial_k)
        
        # 3. 融合并排序
        fused_results = self._fuse_results(
            vector_results,
            bm25_results,
            alpha=alpha,
        )
        
        # 4. 返回top_k
        return fused_results[:top_k]
    
    def _vector_search(
        self,
        query_vector: np.ndarray,
        top_k: int,
    ) -> Dict[str, float]:
        """
        向量检索，返回{chunk_id: score}映射
        """
        indices, scores = self.vector_store.search(query_vector, top_k)
        
        results = {}
        for idx, score in zip(indices, scores):
            chunk_id = self.vector_store.get_chunk_id_by_index(idx)
            if chunk_id:
                results[chunk_id] = float(score)
        
        return results
    
    def _bm25_search(
        self,
        query: str,
        top_k: int,
    ) -> Dict[str, float]:
        """
        BM25检索，返回{chunk_id: score}映射
        """
        results = {}
        for result in self.bm25_index.search(query, top_k):
            results[result.chunk_id] = result.score
        
        return results
    
    def _fuse_results(
        self,
        vector_results: Dict[str, float],
        bm25_results: Dict[str, float],
        alpha: float,
    ) -> List[FusionResult]:
        """
        融合两种检索结果
        
        步骤：
        1. 收集所有候选chunk_id
        2. 分别归一化分数（min-max）
        3. 加权融合
        4. 按融合分数排序
        """
        # 收集所有候选
        all_chunk_ids = set(vector_results.keys()) | set(bm25_results.keys())
        
        if not all_chunk_ids:
            return []
        
        # 归一化向量分数
        if vector_results:
            vector_scores = np.array(list(vector_results.values()))
            vector_min, vector_max = vector_scores.min(), vector_scores.max()
            vector_range = vector_max - vector_min if vector_max > vector_min else 1.0
        else:
            vector_min, vector_range = 0.0, 1.0
        
        # 归一化BM25分数
        if bm25_results:
            bm25_scores = np.array(list(bm25_results.values()))
            bm25_min, bm25_max = bm25_scores.min(), bm25_scores.max()
            bm25_range = bm25_max - bm25_min if bm25_max > bm25_min else 1.0
        else:
            bm25_min, bm25_range = 0.0, 1.0
        
        # 融合
        fused = []
        for chunk_id in all_chunk_ids:
            v_score = vector_results.get(chunk_id, 0.0)
            b_score = bm25_results.get(chunk_id, 0.0)
            
            # 归一化到0-1
            v_norm = (v_score - vector_min) / vector_range if vector_range > 0 else 0.0
            b_norm = (b_score - bm25_min) / bm25_range if bm25_range > 0 else 0.0
            
            # 加权融合
            fusion_score = alpha * v_norm + (1 - alpha) * b_norm
            
            fused.append(FusionResult(
                chunk_id=chunk_id,
                fusion_score=fusion_score,
                vector_score=v_score,
                vector_norm=v_norm,
                bm25_score=b_score,
                bm25_norm=b_norm,
                rank=0  # 稍后设置
            ))
        
        # 按融合分数降序排序
        fused.sort(key=lambda x: x.fusion_score, reverse=True)
        
        # 设置排名
        for i, result in enumerate(fused, 1):
            result.rank = i
        
        return fused
    
    def search_by_strategy(
        self,
        query: str,
        query_vector: np.ndarray,
        strategy: str = "fusion",  # "fusion" | "vector_only" | "bm25_only"
        top_k: int = 5,
        alpha: float = 0.6,
    ) -> List[FusionResult]:
        """
        根据策略执行检索
        
        Args:
            query: 查询文本
            query_vector: 查询向量
            strategy: 检索策略
            top_k: 返回结果数
            alpha: 融合权重（仅fusion模式使用）
        """
        if strategy == "fusion":
            return self.fusion_search(query, query_vector, top_k, alpha=alpha)
        
        elif strategy == "vector_only":
            vector_results = self._vector_search(query_vector, top_k)
            return [
                FusionResult(
                    chunk_id=chunk_id,
                    fusion_score=score,
                    vector_score=score,
                    vector_norm=1.0,
                    bm25_score=0.0,
                    bm25_norm=0.0,
                    rank=i+1
                )
                for i, (chunk_id, score) in enumerate(vector_results.items())
            ]
        
        elif strategy == "bm25_only":
            bm25_results = self._bm25_search(query, top_k)
            return [
                FusionResult(
                    chunk_id=chunk_id,
                    fusion_score=score,
                    vector_score=0.0,
                    vector_norm=0.0,
                    bm25_score=score,
                    bm25_norm=1.0,
                    rank=i+1
                )
                for i, (chunk_id, score) in enumerate(bm25_results.items())
            ]
        
        else:
            raise ValueError(f"未知检索策略: {strategy}")
    
    def save(self, output_dir: Path) -> None:
        """保存两种索引"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        self.vector_store.save(output_dir)
        self.bm25_index.save(output_dir)
        
        logger.info(f"混合索引已保存到: {output_dir}")
    
    def load(self, input_dir: Path) -> None:
        """加载两种索引"""
        input_dir = Path(input_dir)
        
        self.vector_store.load(input_dir)
        self.bm25_index.load(input_dir)
        
        logger.info(f"混合索引已加载: {input_dir}")
    
    @property
    def is_built(self) -> bool:
        """检查索引是否已构建"""
        return (
            self.vector_store.index is not None and
            self.bm25_index.is_built
        )
