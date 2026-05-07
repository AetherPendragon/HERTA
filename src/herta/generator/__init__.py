"""
生成器模块（增强版，支持Pipeline）

提供配置生成功能：
- 目标协议文档解析
- 知识库检索（Vector + BM25融合检索）
- Prompt 模板加载
- 配置生成
- Handler生成（函数清单强制约束）

新增Pipeline支持：
- Query改写
- 融合检索
- 精排
- 上下文压缩
- 结构化函数清单注入
"""

from herta.generator.schemas import (
    TargetProtocolSpec,
    RetrievedChunk,
    GenerationContext,
    GenerationResult,
)
from herta.generator.target_parser import TargetParser, parse_target_protocol
from herta.generator.retriever import (
    KnowledgeRetriever,
    FusionKnowledgeRetriever,
    retrieve_from_kb,
)
from herta.generator.reranker import ChunkReranker, RerankedChunk, rerank_chunks
from herta.generator.query_rewriter import QueryRewriter, RewriteResult, rewrite_query
from herta.generator.context_compressor import (
    ContextCompressor,
    CompressionResult,
    compress_context,
)
from herta.generator.function_registry import (
    FunctionRegistryBuilder,
    FunctionList,
    FunctionSpec,
    build_function_list,
)
from herta.generator.prompt_loader import PromptLoader, load_prompt, render_prompt
from herta.generator.config_generator import ConfigGenerator, generate_config
from herta.generator.handler_generator import (
    HandlerGenerator,
    HandlerGenerationResult,
    generate_handler,
)

# Pipeline模块
from herta.generator.pipeline import (
    UnifiedPipeline,
    PipelineConfig,
    PipelineContext,
    QueryRewriteStage,
    FusionRetrievalStage,
    RerankStage,
    ContextCompressionStage,
    StructuredContextStage,
    PromptBuildingStage,
    LLMGenerationStage,
)

__all__ = [
    # Schemas
    "TargetProtocolSpec",
    "RetrievedChunk",
    "GenerationContext",
    "GenerationResult",
    # Target Parser
    "TargetParser",
    "parse_target_protocol",
    # Retriever (增强版)
    "KnowledgeRetriever",
    "FusionKnowledgeRetriever",
    "retrieve_from_kb",
    # Reranker (新增)
    "ChunkReranker",
    "RerankedChunk",
    "rerank_chunks",
    # Query Rewriter (新增)
    "QueryRewriter",
    "RewriteResult",
    "rewrite_query",
    # Context Compressor (新增)
    "ContextCompressor",
    "CompressionResult",
    "compress_context",
    # Function Registry (新增)
    "FunctionRegistryBuilder",
    "FunctionList",
    "FunctionSpec",
    "build_function_list",
    # Prompt Loader
    "PromptLoader",
    "load_prompt",
    "render_prompt",
    # Config Generator
    "ConfigGenerator",
    "generate_config",
    # Handler Generator
    "HandlerGenerator",
    "HandlerGenerationResult",
    "generate_handler",
    # Pipeline (新增)
    "UnifiedPipeline",
    "PipelineConfig",
    "PipelineContext",
    "QueryRewriteStage",
    "FusionRetrievalStage",
    "RerankStage",
    "ContextCompressionStage",
    "StructuredContextStage",
    "PromptBuildingStage",
    "LLMGenerationStage",
]
