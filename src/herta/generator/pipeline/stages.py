"""
Pipeline各阶段的具体实现

实现7个阶段的处理逻辑：
1. QueryRewriteStage - 查询改写
2. FusionRetrievalStage - 融合检索
3. RerankStage - 精排
4. ContextCompressionStage - 上下文压缩
5. StructuredContextStage - 结构化上下文注入
6. PromptBuildingStage - Prompt构建
7. LLMGenerationStage - LLM生成
"""

import time
from typing import Dict, Any, List
import numpy as np

from .base import PipelineStage, PipelineContext
from herta.logging import get_logger

logger = get_logger(__name__)


# ===== Stage 1: Query Rewrite =====
class QueryRewriteStage(PipelineStage):
    """查询改写阶段"""
    
    def __init__(self, config: Dict[str, Any], enabled: bool = True):
        super().__init__(config, enabled)
        from ..query_rewriter import QueryRewriter
        self.rewriter = QueryRewriter(
            rewrite_mode=config.get('mode', 'code_semantic')
        )
    
    def process(self, context: PipelineContext) -> PipelineContext:
        rewritten = self.rewriter.rewrite(
            context.raw_query,
            context_type=context.generation_type
        )
        context.rewritten_query = rewritten.rewritten_query
        context.metadata['query_rewrite'] = {
            'original': context.raw_query,
            'rewritten': rewritten.rewritten_query,
            'mode': rewritten.mode.value,
            'expansions': rewritten.expansions
        }
        logger.debug(f"Query改写: '{context.raw_query[:30]}...' -> '{rewritten.rewritten_query[:50]}...'")
        return context


# ===== Stage 2: Fusion Retrieval =====
class FusionRetrievalStage(PipelineStage):
    """融合检索阶段（Vector + BM25）"""
    
    def __init__(self, config: Dict[str, Any], enabled: bool = True):
        super().__init__(config, enabled)
        from ..retriever import FusionKnowledgeRetriever
        
        strategy = config.get('strategy', 'fusion')
        if strategy == 'fusion':
            self.retriever = FusionKnowledgeRetriever(
                kb_dir=config['kb_dir'],
                fusion_alpha=config.get('alpha', 0.6)
            )
        else:
            # 使用基础检索器
            from ..retriever import KnowledgeRetriever
            self.retriever = KnowledgeRetriever(kb_dir=config['kb_dir'])
        
        self.strategy = strategy
        self.top_k = config.get('top_k', 20)
    
    def process(self, context: PipelineContext) -> PipelineContext:
        query = context.get_current_query()
        
        if self.strategy == 'fusion':
            candidates = self.retriever.retrieve(
                query=query,
                top_k=self.top_k,
                context_type=context.generation_type
            )
        else:
            candidates = self.retriever.retrieve(
                query=query,
                top_k=self.top_k
            )
        
        context.retrieval_candidates = candidates
        context.metadata['retrieval'] = {
            'query_used': query,
            'candidates_count': len(candidates),
            'strategy': self.strategy,
            'top_k': self.top_k
        }
        
        logger.info(f"检索完成: {len(candidates)} candidates (strategy={self.strategy})")
        return context


# ===== Stage 3: Rerank =====
class RerankStage(PipelineStage):
    """重排序阶段（LLM-based精排）"""
    
    def __init__(self, config: Dict[str, Any], enabled: bool = True):
        super().__init__(config, enabled)
        from ..reranker import ChunkReranker
        self.reranker = ChunkReranker(
            score_threshold=config.get('threshold', 5.0)
        )
        self.top_n = config.get('top_n', 5)
    
    def process(self, context: PipelineContext) -> PipelineContext:
        candidates = context.retrieval_candidates
        if not candidates:
            logger.warning("无候选chunks可供精排")
            return context
        
        reranked = self.reranker.rerank(
            query=context.get_current_query(),
            candidates=candidates,
            top_n=self.top_n
        )
        
        context.reranked_results = reranked
        context.metadata['rerank'] = {
            'input_count': len(candidates),
            'output_count': len(reranked),
            'threshold': self.config.get('threshold', 5.0)
        }
        
        logger.info(f"精排完成: {len(candidates)} -> {len(reranked)}")
        return context


# ===== Stage 4: Context Compression =====
class ContextCompressionStage(PipelineStage):
    """上下文压缩阶段"""
    
    def __init__(self, config: Dict[str, Any], enabled: bool = True):
        super().__init__(config, enabled)
        from ..context_compressor import ContextCompressor
        self.compressor = ContextCompressor(
            relevance_threshold=config.get('threshold', 6.0),
            preserve_code_structure=config.get('preserve_code_structure', True)
        )
    
    def process(self, context: PipelineContext) -> PipelineContext:
        chunks = context.reranked_results or context.retrieval_candidates
        if not chunks:
            logger.warning("无chunks可供压缩")
            return context
        
        result = self.compressor.compress(
            query=context.get_current_query(),
            chunks=chunks,
            task_type=context.generation_type
        )
        
        context.compressed_context = result.compressed_chunks
        context.metadata['compression'] = {
            'original_count': len(chunks),
            'compressed_count': len(result.compressed_chunks),
            'discarded_count': result.discarded_count,
            'compression_ratio': result.compression_ratio,
            'preservation_rate': result.preservation_rate
        }
        
        logger.info(f"上下文压缩: {len(chunks)} -> {len(result.compressed_chunks)} "
                   f"(ratio={result.compression_ratio:.1%})")
        return context


# ===== Stage 5: Structured Context Injection =====
class StructuredContextStage(PipelineStage):
    """结构化上下文注入阶段"""
    
    def __init__(self, config: Dict[str, Any], enabled: bool = True):
        super().__init__(config, enabled)
        from ..function_registry import FunctionRegistryBuilder
        self.registry_builder = FunctionRegistryBuilder()
        self.build_function_manifest = config.get('build_function_manifest', True)
    
    def process(self, context: PipelineContext) -> PipelineContext:
        # 构建函数清单（主要用于handler生成）
        if context.generation_type == "handler" and self.build_function_manifest:
            function_list = self.registry_builder.build_from_target(
                target_spec=context.target_spec,
                retrieved_chunks=context.compressed_context or context.reranked_results
            )
            
            context.function_manifest = function_list
            context.structured_context = {
                'function_manifest': function_list.to_dict(),
                'checklist': function_list.to_checklist(),
                'manifest_text': function_list.to_manifest(),
                'function_count': function_list.total_count
            }
            
            context.metadata['structured_context'] = {
                'function_count': function_list.total_count,
                'cmd_count': function_list.cmd_count,
                'telemetry_count': function_list.telemetry_count,
                'internal_count': function_list.internal_count
            }
            
            logger.info(f"函数清单构建: {function_list.total_count} functions")
        
        else:
            # config生成或其他类型，构建字段清单
            context.structured_context = {
                'field_schema': self._build_field_schema(context.target_spec),
            }
            logger.info("字段清单构建完成")
        
        return context
    
    def _build_field_schema(self, target_spec) -> Dict[str, Any]:
        """构建配置字段schema"""
        # 简化的字段schema构建
        return {
            'protocol_name': target_spec.target_name,
            'fields': [],  # 可从sections提取
            'commands': {},
            'telemetry': {}
        }


# ===== Stage 6: Prompt Building =====
class PromptBuildingStage(PipelineStage):
    """Prompt构建阶段"""
    
    def __init__(self, config: Dict[str, Any], enabled: bool = True):
        super().__init__(config, enabled)
        from ..prompt_loader import PromptLoader
        self.prompt_loader = PromptLoader()
        self.max_context_length = config.get('max_context_length', 8000)
    
    def process(self, context: PipelineContext) -> PipelineContext:
        # 准备模板变量
        variables = self._prepare_variables(context)
        
        # 选择模板
        template_name = self._select_template(context.generation_type)
        
        # 渲染prompt
        try:
            prompt = self.prompt_loader.load_and_render(template_name, variables)
        except Exception as e:
            logger.warning(f"模板渲染失败: {e}，使用默认prompt")
            prompt = self._build_default_prompt(variables)
        
        # 截断过长的上下文
        if len(prompt) > self.max_context_length * 2:  # 简单估算
            prompt = self._truncate_context(prompt, variables)
        
        context.final_prompt = prompt
        context.metadata['prompt_building'] = {
            'template': template_name,
            'prompt_length': len(prompt),
            'has_function_manifest': context.function_manifest is not None
        }
        
        logger.info(f"Prompt构建完成: {len(prompt)} chars")
        return context
    
    def _prepare_variables(self, context: PipelineContext) -> Dict[str, Any]:
        """准备模板变量"""
        variables = {
            'target_summary': self._format_target_summary(context.target_spec),
            'generation_type': context.generation_type,
        }
        
        # 添加上下文
        if context.compressed_context:
            variables['retrieved_context'] = self._format_chunks(context.compressed_context)
        elif context.reranked_results:
            variables['retrieved_context'] = self._format_chunks(context.reranked_results)
        else:
            variables['retrieved_context'] = "（无检索上下文）"
        
        # 添加结构化上下文
        if context.structured_context:
            variables.update(context.structured_context)
        
        return variables
    
    def _format_target_summary(self, target_spec) -> str:
        """格式化目标协议摘要"""
        sections_info = ""
        if target_spec.sections:
            sections_info = "\n文档结构:\n" + "\n".join(
                f"  - {s.get('title', s.get('name', '未命名章节'))}"
                for s in target_spec.sections[:10]
            )
        
        return f"""【目标协议】
名称: {target_spec.target_name}
文档路径: {target_spec.document_path}
摘要: {target_spec.summary}{sections_info}
"""
    
    def _format_chunks(self, chunks: List) -> str:
        """格式化chunks为文本"""
        sections = []
        for i, chunk in enumerate(chunks, 1):
            score_str = f" (score: {chunk.score:.3f})" if hasattr(chunk, 'score') else ""
            sections.append(
                f"【参考片段 {i}】来源: {chunk.source}{score_str}\n{chunk.text}\n---"
            )
        return "\n\n".join(sections)
    
    def _select_template(self, gen_type: str) -> str:
        """选择模板"""
        templates = {
            'config': 'generate_config.md',
            'handler': 'generate_handler_code.md'
        }
        return templates.get(gen_type, 'generate_default.md')
    
    def _build_default_prompt(self, variables: Dict[str, Any]) -> str:
        """构建默认prompt"""
        return f"""【任务】
根据以下信息生成{variables.get('generation_type', '配置')}。

【目标】
{variables.get('target_summary', '')}

【参考上下文】
{variables.get('retrieved_context', '')}

请生成完整且正确的结果。"""
    
    def _truncate_context(self, prompt: str, variables: Dict[str, Any]) -> str:
        """截断过长的上下文"""
        # 简化的截断策略：缩短retrieved_context
        if 'retrieved_context' in variables:
            ctx = variables['retrieved_context']
            # 保留前5000字符
            truncated = ctx[:5000] + "\n...（上下文已截断）"
            variables['retrieved_context'] = truncated
            
            # 重新渲染
            return self._build_default_prompt(variables)
        
        return prompt[:self.max_context_length * 2]


# ===== Stage 7: LLM Generation =====
class LLMGenerationStage(PipelineStage):
    """LLM生成阶段"""
    
    def __init__(self, config: Dict[str, Any], enabled: bool = True):
        super().__init__(config, enabled)
        from ...llm.client import BigModelClient
        self.llm_client = BigModelClient()
        self.model = config.get('model')  # None表示使用默认
        self.temperature = config.get('temperature', 0.1)
    
    def process(self, context: PipelineContext) -> PipelineContext:
        if not context.final_prompt:
            raise ValueError("No prompt available for generation")
        
        messages = [
            {
                "role": "system",
                "content": self._get_system_prompt(context.generation_type)
            },
            {
                "role": "user",
                "content": context.final_prompt
            }
        ]
        
        try:
            start_time = time.time()
            response = self.llm_client.chat(
                messages=messages,
                model=self.model,
                temperature=self.temperature
            )
            duration = (time.time() - start_time) * 1000
            
            context.generated_content = response
            context.metadata['generation'] = {
                'model': self.model or 'default',
                'temperature': self.temperature,
                'output_length': len(response),
                'duration_ms': duration
            }
            
            logger.info(f"LLM生成完成: {len(response)} chars ({duration:.0f}ms)")
            
        except Exception as e:
            logger.error(f"LLM生成失败: {e}")
            context.metadata['generation'] = {'error': str(e)}
            raise
        
        return context
    
    def _get_system_prompt(self, gen_type: str) -> str:
        """获取系统prompt"""
        prompts = {
            'config': '''你是一个专业的协议配置生成助手。
请严格按照要求输出JSON格式的配置文件。
确保字段完整、类型正确。''',
            'handler': '''你是一位资深的嵌入式C语言开发者，擅长编写高效、健壮的协议处理代码。
请严格按照函数清单生成所有必需的函数，保持代码风格一致。
使用TODO标记不确定的部分，但不要省略任何必需函数。'''
        }
        return prompts.get(gen_type, '你是一个专业的代码生成助手。')
