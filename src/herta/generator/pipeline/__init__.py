"""
统一RAG Pipeline模块

提供模块化、可配置的RAG处理流程：
1. Query Rewrite - 查询改写
2. Fusion Retrieval - 融合检索(Vector + BM25)
3. Rerank - 精排
4. Context Compression - 上下文压缩
5. Structured Context - 结构化上下文注入
6. Prompt Building - Prompt构建
7. LLM Generation - LLM生成
"""

from .base import PipelineStage, PipelineContext, UnifiedPipeline
from .config import PipelineConfig, StageConfig
from .stages import (
    QueryRewriteStage,
    FusionRetrievalStage,
    RerankStage,
    ContextCompressionStage,
    StructuredContextStage,
    PromptBuildingStage,
    LLMGenerationStage,
)

__all__ = [
    "PipelineStage",
    "PipelineContext",
    "UnifiedPipeline",
    "PipelineConfig",
    "StageConfig",
    "QueryRewriteStage",
    "FusionRetrievalStage",
    "RerankStage",
    "ContextCompressionStage",
    "StructuredContextStage",
    "PromptBuildingStage",
    "LLMGenerationStage",
]
