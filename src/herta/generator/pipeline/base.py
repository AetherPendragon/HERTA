"""
Pipeline基础架构

定义Pipeline阶段基类和统一编排器
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List, Union
from pathlib import Path

from herta.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PipelineContext:
    """
    Pipeline上下文对象
    
    在各阶段之间传递数据，记录处理状态
    """
    # 输入数据
    raw_query: str
    target_spec: Any  # TargetProtocolSpec
    generation_type: str  # "config" | "handler"
    
    # 各阶段中间结果（逐步填充）
    rewritten_query: Optional[str] = None
    retrieval_candidates: Optional[List] = None
    fused_results: Optional[List] = None
    reranked_results: Optional[List] = None
    compressed_context: Optional[List] = None
    structured_context: Optional[Dict] = None
    function_manifest: Optional[Any] = None  # FunctionList
    final_prompt: Optional[str] = None
    generated_content: Optional[str] = None
    
    # 元数据（用于调试和评估）
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_current_query(self) -> str:
        """获取当前阶段使用的查询（可能已被改写）"""
        return self.rewritten_query or self.raw_query
    
    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            'raw_query': self.raw_query,
            'generation_type': self.generation_type,
            'rewritten': self.rewritten_query is not None,
            'retrieval_count': len(self.retrieval_candidates) if self.retrieval_candidates else 0,
            'final_context_count': len(self.compressed_context) if self.compressed_context else 0,
            'has_function_manifest': self.function_manifest is not None,
        }


class PipelineStage(ABC):
    """
    Pipeline阶段基类
    
    所有处理模块必须继承此类，实现统一接口
    """
    
    def __init__(self, config: Dict[str, Any], enabled: bool = True):
        self.config = config
        self.enabled = enabled
        self.stage_name = self.__class__.__name__
    
    @abstractmethod
    def process(self, input_data: PipelineContext) -> PipelineContext:
        """
        处理输入数据，返回更新后的上下文
        
        Args:
            input_data: Pipeline上下文对象
        
        Returns:
            更新后的Pipeline上下文
        """
        pass
    
    def is_enabled(self) -> bool:
        """检查此阶段是否启用"""
        return self.enabled


class UnifiedPipeline:
    """
    统一RAG Pipeline orchestrator
    
    管理所有阶段，按顺序执行，支持配置控制
    """
    
    def __init__(self, pipeline_config: 'PipelineConfig'):
        from .config import PipelineConfig
        self.config: PipelineConfig = pipeline_config
        self.stages: List[PipelineStage] = []
        self._build_pipeline()
    
    def _build_pipeline(self):
        """根据配置构建pipeline阶段"""
        # Stage 1: Query Rewrite
        if self.config.query_rewrite.enabled:
            from .stages import QueryRewriteStage
            self.stages.append(QueryRewriteStage(
                config=self.config.query_rewrite.params,
                enabled=True
            ))
        
        # Stage 2: Retrieval (Fusion)
        if self.config.retrieval.enabled:
            from .stages import FusionRetrievalStage
            self.stages.append(FusionRetrievalStage(
                config=self.config.retrieval.params,
                enabled=True
            ))
        
        # Stage 3: Rerank
        if self.config.rerank.enabled:
            from .stages import RerankStage
            self.stages.append(RerankStage(
                config=self.config.rerank.params,
                enabled=True
            ))
        
        # Stage 4: Context Compression
        if self.config.context_compression.enabled:
            from .stages import ContextCompressionStage
            self.stages.append(ContextCompressionStage(
                config=self.config.context_compression.params,
                enabled=True
            ))
        
        # Stage 5: Structured Context Injection
        if self.config.structured_context.enabled:
            from .stages import StructuredContextStage
            self.stages.append(StructuredContextStage(
                config=self.config.structured_context.params,
                enabled=True
            ))
        
        # Stage 6: Prompt Building (always enabled)
        from .stages import PromptBuildingStage
        self.stages.append(PromptBuildingStage(
            config=self.config.prompt_building.params,
            enabled=True
        ))
        
        # Stage 7: LLM Generation (always enabled)
        from .stages import LLMGenerationStage
        self.stages.append(LLMGenerationStage(
            config=self.config.llm_generation.params,
            enabled=True
        ))
        
        logger.info(f"Pipeline构建完成: {len(self.stages)} 个阶段")
    
    def execute(self, context: PipelineContext) -> PipelineContext:
        """
        执行完整pipeline
        
        Args:
            context: 初始Pipeline上下文
        
        Returns:
            完成所有阶段的上下文（包含生成结果）
        """
        for stage in self.stages:
            if stage.is_enabled():
                start_time = time.time()
                logger.info(f"执行阶段: {stage.stage_name}")
                
                try:
                    context = stage.process(context)
                    duration = (time.time() - start_time) * 1000
                    context.metadata[f'{stage.stage_name}_duration_ms'] = duration
                    logger.info(f"阶段完成: {stage.stage_name} ({duration:.1f}ms)")
                except Exception as e:
                    logger.error(f"阶段失败: {stage.stage_name} - {e}")
                    context.metadata[f'{stage.stage_name}_error'] = str(e)
                    if self.config.fail_on_error:
                        raise
            else:
                context.metadata[f'{stage.stage_name}_status'] = 'skipped'
        
        return context
    
    def execute_with_trace(self, context: PipelineContext) -> tuple[PipelineContext, Dict]:
        """
        执行pipeline并返回详细trace（用于调试）
        """
        trace = {
            'pipeline_config': self.config.to_dict(),
            'stages': []
        }
        
        for stage in self.stages:
            stage_trace = {
                'name': stage.stage_name,
                'enabled': stage.is_enabled(),
            }
            
            if stage.is_enabled():
                try:
                    start_time = time.time()
                    context = stage.process(context)
                    stage_trace['status'] = 'success'
                    stage_trace['duration_ms'] = (time.time() - start_time) * 1000
                    stage_trace['output_preview'] = str(context.to_dict())[:200]
                except Exception as e:
                    stage_trace['status'] = 'error'
                    stage_trace['error'] = str(e)
                    if self.config.fail_on_error:
                        raise
            else:
                stage_trace['status'] = 'skipped'
            
            trace['stages'].append(stage_trace)
        
        return context, trace
