"""
Chunk精排模块

对召回的候选chunk进行相关性评分和排序，使用LLM评分（0-10）
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from herta.generator.schemas import RetrievedChunk
from herta.llm.client import BigModelClient
from herta.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RerankedChunk(RetrievedChunk):
    """
    重排序后的Chunk（继承RetrievedChunk）
    
    新增字段：
    - rerank_score: LLM评分（0-10）
    - relevance_reason: 相关性说明
    - original_rank: 原始排序位置
    - vector_score: 原始向量相似度分数
    """
    rerank_score: float = 0.0           # LLM评分 0-10
    relevance_reason: str = ""          # 评分理由
    original_rank: int = 0              # 原始排名（召回阶段）
    vector_score: float = 0.0             # 原始向量相似度分数


class ChunkReranker:
    """
    Chunk精排器（使用LLM评分）
    
    对召回的候选chunk进行相关性评分和排序
    """
    
    # 默认评分Prompt模板
    DEFAULT_SCORE_PROMPT = """【任务】
你是一个专业的代码检索相关性评估专家。请评估以下知识库片段与用户查询的相关性。

【用户查询】
{query}

【知识库片段】
来源: {source}
类型: {kind}
内容:
---
{text}
---

【评分标准】（0-10分）
10分: 完美匹配 - 直接包含查询所需的完整信息（如具体的handler函数实现、配置字段定义）
8-9分: 高度相关 - 包含查询相关的核心信息（如类似功能的代码示例、相关结构体定义）
6-7分: 中度相关 - 包含部分相关信息（如同一文件的其他函数、相关但不直接的描述）
4-5分: 弱相关 - 仅有轻微关联（如同一项目但不同功能）
0-3分: 无关 - 与查询无明显关系

【输出格式】
评分: [数字]
理由: [一句话说明相关性原因]

请只输出评分和理由，不要其他内容。"""

    def __init__(
        self,
        llm_client: Optional[BigModelClient] = None,
        score_threshold: float = 5.0,      # 最低接受分数
        batch_size: int = 10,               # 每批评分的chunk数
        model: Optional[str] = None,        # 评分使用的模型
    ):
        """
        初始化Chunk精排器
        
        Args:
            llm_client: LLM客户端
            score_threshold: 相关性评分阈值（0-10），低于此值的chunk被过滤
            batch_size: 批量评分的chunk数量
            model: 指定评分模型，默认使用settings中的chat_model
        """
        self.llm_client = llm_client or BigModelClient()
        self.score_threshold = score_threshold
        self.batch_size = batch_size
        self.model = model
        
        logger.info(f"ChunkReranker初始化: threshold={score_threshold}")
    
    def rerank(
        self,
        query: str,
        candidates: List[RetrievedChunk],
        top_n: int = 5,
    ) -> List[RerankedChunk]:
        """
        对候选chunk进行重排序
        
        流程：
        1. 批量调用LLM评分
        2. 过滤低分chunk
        3. 按评分排序
        4. 返回top_n
        
        Args:
            query: 原始查询（改写后的）
            candidates: 召回的候选chunk列表
            top_n: 最终返回的chunk数量
        
        Returns:
            按LLM评分排序的RerankedChunk列表
        """
        if not candidates:
            return []
        
        logger.info(f"开始精排: {len(candidates)} candidates -> top {top_n}")
        
        # 评分
        scored_results = []
        for i, chunk in enumerate(candidates):
            score, reason = self._llm_score_relevance(query, chunk)
            scored_results.append((chunk, score, reason, i + 1))  # i+1为原始排名
            
            logger.debug(f"  Chunk {i+1}: score={score:.1f}, reason={reason[:50]}...")
        
        # 过滤低分
        filtered = [
            (chunk, score, reason, orig_rank)
            for chunk, score, reason, orig_rank in scored_results
            if score >= self.score_threshold
        ]
        
        # 按评分降序排序
        filtered.sort(key=lambda x: x[1], reverse=True)
        
        # 构建结果
        results = []
        for i, (chunk, score, reason, orig_rank) in enumerate(filtered[:top_n], 1):
            reranked = RerankedChunk(
                chunk_id=chunk.chunk_id,
                source=chunk.source,
                file=chunk.file,
                kind=chunk.kind,
                section=chunk.section,
                text=chunk.text,
                score=chunk.score,  # 保持原始分数
                token_count=chunk.token_count,
                metadata=chunk.metadata,
                rerank_score=score,
                relevance_reason=reason,
                original_rank=orig_rank,
                vector_score=chunk.score
            )
            results.append(reranked)
        
        logger.info(f"精排完成: {len(candidates)} -> {len(results)} (threshold={self.score_threshold})")
        return results
    
    def _llm_score_relevance(
        self,
        query: str,
        chunk: RetrievedChunk,
    ) -> Tuple[float, str]:
        """
        使用LLM对单个chunk评分
        
        Args:
            query: 查询字符串
            chunk: 待评分的chunk
        
        Returns:
            (score, reason) 元组
        """
        # 构造prompt
        prompt = self.DEFAULT_SCORE_PROMPT.format(
            query=query,
            source=chunk.source,
            kind=chunk.kind,
            text=chunk.text[:1500]  # 限制长度
        )
        
        try:
            response = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.1
            )
            
            # 解析评分
            score = 5.0  # 默认中等
            reason = ""
            
            for line in response.split('\n'):
                line = line.strip()
                if line.startswith("评分:") or line.startswith("分数:"):
                    try:
                        score_str = line.split(":")[1].strip()
                        # 提取数字
                        score_match = re.search(r'(\d+(?:\.\d+)?)', score_str)
                        if score_match:
                            score = float(score_match.group(1))
                    except (ValueError, IndexError):
                        pass
                elif line.startswith("理由:"):
                    reason = line.split(":", 1)[1].strip()
            
            return score, reason
            
        except Exception as e:
            logger.warning(f"LLM评分失败: {e}，使用默认评分")
            return 5.0, "评分失败，默认保留"
    
    def rerank_batch(
        self,
        queries: List[str],
        candidates_batch: List[List[RetrievedChunk]],
        top_n: int = 5,
    ) -> List[List[RerankedChunk]]:
        """
        批量精排
        
        Args:
            queries: 查询列表
            candidates_batch: 候选chunk列表的列表
            top_n: 每个查询返回的结果数
        
        Returns:
            每个查询的精排结果列表
        """
        return [
            self.rerank(query, candidates, top_n)
            for query, candidates in zip(queries, candidates_batch)
        ]


# 便捷函数
def rerank_chunks(
    query: str,
    chunks: List[RetrievedChunk],
    top_n: int = 5,
    score_threshold: float = 5.0,
    llm_client: Optional[BigModelClient] = None,
) -> List[RerankedChunk]:
    """
    便捷函数：精排chunks
    
    Args:
        query: 查询字符串
        chunks: 候选chunks
        top_n: 返回结果数
        score_threshold: 评分阈值
        llm_client: LLM客户端
    
    Returns:
        精排后的RerankedChunk列表
    """
    reranker = ChunkReranker(
        llm_client=llm_client,
        score_threshold=score_threshold
    )
    return reranker.rerank(query, chunks, top_n)
