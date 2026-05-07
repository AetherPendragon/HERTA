"""
配置生成器模块（增强版，支持Pipeline）

支持模块化Pipeline流程：
1. Query Rewrite - 查询改写
2. Fusion Retrieval - 融合检索
3. Rerank - 精排
4. Context Compression - 上下文压缩
5. Prompt Building - Prompt构建
6. LLM Generation - 配置生成

同时保留传统模式作为fallback。
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from herta.generator.schemas import (
    TargetProtocolSpec,
    RetrievedChunk,
    GenerationContext,
    GenerationResult,
)
from herta.generator.target_parser import TargetParser, parse_target_protocol
from herta.generator.retriever import KnowledgeRetriever
from herta.generator.prompt_loader import PromptLoader
from herta.llm.client import BigModelClient
from herta.config import get_settings
from herta.logging import get_logger
from herta.utils.paths import ensure_dir

# Pipeline支持
from herta.generator.pipeline import (
    UnifiedPipeline,
    PipelineConfig,
    PipelineContext,
)

logger = get_logger(__name__)


class ConfigGenerator:
    """
    配置生成器（增强版，支持Pipeline）

    支持两种模式：
    1. Pipeline模式（推荐）：模块化RAG流程
    2. 传统模式：向后兼容
    """

    DEFAULT_TEMPLATE = "generate_config.md"
    DEFAULT_TOP_K = 20   # Pipeline模式：召回20
    RERANK_TOP_K = 5     # 精排后保留5
    DEFAULT_TEMPERATURE = 0.1

    def __init__(
        self,
        llm_client: Optional[BigModelClient] = None,
        prompt_loader: Optional[PromptLoader] = None,
        use_pipeline: bool = True,
        pipeline_config_path: Optional[str] = "config/rag_pipeline.yaml",
    ):
        """
        初始化配置生成器

        Args:
            llm_client: LLM 客户端实例
            prompt_loader: Prompt 加载器实例
            use_pipeline: 是否使用Pipeline模式
            pipeline_config_path: Pipeline配置文件路径
        """
        self.llm_client = llm_client or BigModelClient()
        self.prompt_loader = prompt_loader or PromptLoader()

        settings = get_settings()
        self.default_model = settings.chat_model

        self.target_parser = TargetParser()
        
        # Pipeline支持
        self.use_pipeline = use_pipeline
        self.pipeline: Optional[UnifiedPipeline] = None
        
        if use_pipeline and pipeline_config_path:
            try:
                config = PipelineConfig.from_yaml(pipeline_config_path)
                config_gen_config = config.get_config_for_generation_type("config_generation")
                self.pipeline = UnifiedPipeline(config_gen_config)
                logger.info("ConfigGenerator Pipeline模式已启用")
            except Exception as e:
                logger.warning(f"Pipeline初始化失败: {e}，回退到传统模式")
                self.use_pipeline = False

    def generate(
        self,
        target_doc_path: Path,
        source_kb_dir: Path,
        target_name: Optional[str] = None,
        top_k: int = DEFAULT_TOP_K,
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        output_dir: Optional[Path] = None,
        use_pipeline: Optional[bool] = None,
    ) -> GenerationResult:
        """
        生成目标协议的配置文件

        支持两种模式：
        1. Pipeline模式（推荐）：模块化RAG流程
        2. 传统模式：向后兼容

        Args:
            target_doc_path: 目标协议文档路径
            source_kb_dir: 源协议知识库目录
            target_name: 目标协议名称（默认从文件名推断）
            top_k: 检索的参考片段数量（传统模式）/召回数量（Pipeline模式）
            model: 使用的 LLM 模型
            temperature: 生成温度
            output_dir: 输出目录（默认 output/generated/<target>/）
            use_pipeline: 强制使用/禁用pipeline

        Returns:
            GenerationResult 生成结果
        """
        # 确定使用哪种模式
        should_use_pipeline = use_pipeline if use_pipeline is not None else self.use_pipeline
        
        if should_use_pipeline and self.pipeline:
            return self._generate_with_pipeline(
                target_doc_path, source_kb_dir, target_name,
                model, temperature, output_dir
            )
        else:
            return self._generate_traditional(
                target_doc_path, source_kb_dir, target_name,
                top_k, model, temperature, output_dir
            )
    
    def _generate_with_pipeline(
        self,
        target_doc_path: Path,
        source_kb_dir: Path,
        target_name: Optional[str],
        model: Optional[str],
        temperature: float,
        output_dir: Optional[Path],
    ) -> GenerationResult:
        """使用Pipeline模式生成配置"""
        start_time = datetime.now()
        model = model or self.default_model
        if target_name is None:
            target_name = Path(target_doc_path).stem
        
        logger.info("=" * 60)
        logger.info(f"[Pipeline模式] 开始生成配置: target={target_name}")
        logger.info("=" * 60)
        
        # 1. 解析目标协议
        try:
            target_spec = self.target_parser.parse(target_doc_path, target_name)
            logger.info(f"✓ 目标协议解析完成: {target_name}")
        except Exception as e:
            logger.error(f"解析失败: {e}")
            return self._create_error_result(target_name, str(source_kb_dir), 0, model, temperature, f"解析失败: {e}")
        
        # 2. 构建Pipeline上下文
        query = self._build_retrieval_query(target_spec)
        context = PipelineContext(
            raw_query=query,
            target_spec=target_spec,
            generation_type="config"
        )
        
        # 更新配置
        self.pipeline.config.retrieval.params['kb_dir'] = str(source_kb_dir)
        
        # 3. 执行Pipeline
        try:
            final_context = self.pipeline.execute(context)
            logger.info(f"✓ Pipeline执行完成")
        except Exception as e:
            logger.error(f"Pipeline执行失败: {e}")
            return self._create_error_result(target_name, str(source_kb_dir), 0, model, temperature, f"Pipeline失败: {e}")
        
        # 4. 提取结果
        config = self._extract_and_parse_json(final_context.generated_content or "{}")
        
        # 5. 构建结果
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        result = GenerationResult(
            config=config,
            raw_response=final_context.generated_content or "",
            target=target_name,
            source_kb=str(source_kb_dir),
            retrieved_chunk_count=len(final_context.compressed_context or []),
            model=model,
            temperature=temperature,
            is_valid_json=True,
            error_message=None,
        )
        result.metadata = final_context.metadata  # 添加pipeline元数据
        
        # 6. 保存
        if output_dir is None:
            output_dir = Path(f"output/generated/{target_name}")
        output_dir = ensure_dir(output_dir)
        output_path = output_dir / f"{target_name}_config.json"
        
        try:
            result.save_config(output_path)
            logger.info(f"✓ 配置已保存: {output_path}")
        except Exception as e:
            logger.error(f"保存失败: {e}")
            result.error_message = f"保存失败: {e}"
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ [Pipeline模式] 配置生成完成！")
        logger.info("=" * 60)
        logger.info(f"  Target:       {target_name}")
        logger.info(f"  检索片段:     {result.retrieved_chunk_count}")
        logger.info(f"  生成耗时:     {duration:.2f} 秒")
        logger.info("=" * 60)
        
        return result
    
    def _generate_traditional(
        self,
        target_doc_path: Path,
        source_kb_dir: Path,
        target_name: Optional[str],
        top_k: int,
        model: Optional[str],
        temperature: float,
        output_dir: Optional[Path],
    ) -> GenerationResult:
        """使用传统模式生成配置（向后兼容）"""
        start_time = datetime.now()

        model = model or self.default_model
        if target_name is None:
            target_name = Path(target_doc_path).stem

        logger.info("=" * 60)
        logger.info(f"[传统模式] 开始生成配置: target={target_name}")
        logger.info("=" * 60)

        # 1. 解析目标协议文档
        try:
            target_spec = self.target_parser.parse(target_doc_path, target_name)
            logger.info(f"✓ 目标协议解析完成: {target_name}")
        except Exception as e:
            logger.error(f"解析失败: {e}")
            return self._create_error_result(target_name, str(source_kb_dir), top_k, model, temperature, f"解析失败: {e}")

        # 2. 从知识库检索相关信息
        try:
            retriever = KnowledgeRetriever(source_kb_dir, self.llm_client)
            query = self._build_retrieval_query(target_spec)
            logger.info(f"检索 Query: {query[:100]}...")

            retrieved_chunks = retriever.retrieve(query, top_k=top_k)
            logger.info(f"✓ 检索完成: {len(retrieved_chunks)} 个相关片段")
        except Exception as e:
            logger.error(f"检索失败: {e}")
            return self._create_error_result(target_name, str(source_kb_dir), top_k, model, temperature, f"检索失败: {e}")

        # 3. 构造生成上下文
        context = GenerationContext(
            target=target_spec,
            retrieved_chunks=retrieved_chunks,
            source_kb=str(source_kb_dir),
            top_k=top_k,
            model=model,
            temperature=temperature,
        )

        # 4. 调用 LLM 生成配置
        try:
            config, raw_response = self._generate_config_with_llm(context)
            logger.info("LLM 生成完成")
        except Exception as e:
            logger.error(f"LLM 生成失败: {e}")
            return self._create_error_result(
                target_name, str(source_kb_dir), top_k, model, temperature, f"生成失败: {e}"
            )

        # 5. 创建生成结果
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        result = GenerationResult(
            config=config,
            raw_response=raw_response,
            target=target_name,
            source_kb=str(source_kb_dir),
            retrieved_chunk_count=len(retrieved_chunks),
            model=model,
            temperature=temperature,
            is_valid_json=True,
            error_message=None,
        )

        # 6. 保存结果
        if output_dir is None:
            output_dir = Path(f"output/generated/{target_name}")

        output_dir = ensure_dir(output_dir)
        output_path = output_dir / f"{target_name}_config.json"

        try:
            result.save_config(output_path)
            logger.info(f"配置已保存: {output_path}")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            result.error_message = f"保存失败: {e}"

        # 输出摘要
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ 配置生成完成！")
        logger.info("=" * 60)
        logger.info(f"  Target:       {target_name}")
        logger.info(f"  Source KB:    {source_kb_dir}")
        logger.info(f"  Top-K:        {top_k}")
        logger.info(f"  检索片段数:   {len(retrieved_chunks)}")
        logger.info(f"  LLM 模型:     {model}")
        logger.info(f"  生成耗时:     {duration:.2f} 秒")
        logger.info(f"  输出路径:     {output_path}")
        logger.info("=" * 60)

        return result

    def _build_retrieval_query(self, target_spec: TargetProtocolSpec) -> str:
        """
        构造检索 Query

        基于目标协议信息构造用于检索源知识库的 query

        Args:
            target_spec: 目标协议规范

        Returns:
            检索 query 字符串
        """
        # 简单版本：使用目标协议名称和摘要关键词
        query_parts = [
            f"{target_spec.target_name} 协议配置",
            "配置字段 参数映射",
            "命令字 指令",
            "遥测字段 数据结构",
            "配置文件结构",
        ]

        # 添加摘要中的关键词（取前50字）
        if target_spec.summary:
            summary_keywords = target_spec.summary[:100].replace('\n', ' ')
            query_parts.append(summary_keywords)

        return " ".join(query_parts)

    def _generate_config_with_llm(self, context: GenerationContext) -> tuple[Dict[str, Any], str]:
        """
        使用 LLM 生成配置

        Args:
            context: 生成上下文

        Returns:
            (config_dict, raw_response) 元组

        Raises:
            RuntimeError: LLM 调用失败或返回无效 JSON
        """
        # 准备模板变量
        variables = {
            "target_summary": context.format_target_summary(),
            "retrieved_context": context.format_retrieved_context(max_length=8000),
            "output_schema": context.output_schema,
        }

        # 加载并渲染 Prompt
        try:
            prompt = self.prompt_loader.load_and_render(self.DEFAULT_TEMPLATE, variables)
            logger.debug(f"Prompt 渲染完成: {len(prompt)} 字符")
        except FileNotFoundError:
            # 如果模板不存在，使用内置默认模板
            logger.warning(f"模板 {self.DEFAULT_TEMPLATE} 不存在，使用默认模板")
            prompt = self._get_default_prompt(variables)

        # 调用 LLM
        messages = [
            {"role": "system", "content": "你是一个专业的协议配置生成助手。请严格按照要求输出 JSON 格式的配置文件。"},
            {"role": "user", "content": prompt},
        ]

        try:
            raw_response = self.llm_client.chat(
                messages=messages,
                model=context.model,
                temperature=context.temperature,
            )
            logger.debug(f"LLM 响应: {raw_response[:200]}...")
        except Exception as e:
            raise RuntimeError(f"LLM 调用失败: {e}") from e

        # 解析 JSON
        try:
            config = self._extract_and_parse_json(raw_response)
            return config, raw_response
        except Exception as e:
            raise RuntimeError(f"解析 LLM 返回的 JSON 失败: {e}\n原始响应:\n{raw_response[:500]}...") from e

    def _extract_and_parse_json(self, text: str) -> Dict[str, Any]:
        """
        从文本中提取并解析 JSON

        处理 LLM 返回的各种格式：
        - 纯 JSON
        - 包含在 ```json ... ``` 代码块中
        - 包含在 ``` ... ``` 代码块中
        - 包含额外文本

        Args:
            text: 原始文本

        Returns:
            解析后的 JSON 字典

        Raises:
            json.JSONDecodeError: 解析失败
        """
        text = text.strip()

        # 尝试 1: 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试 2: 提取 ```json ... ``` 代码块
        import re
        json_block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        matches = re.findall(json_block_pattern, text, re.DOTALL)

        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        # 尝试 3: 查找第一个 { 和最后一个 } 之间的内容
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and start < end:
            try:
                return json.loads(text[start:end+1])
            except json.JSONDecodeError:
                pass

        # 尝试 4: 查找第一个 [ 和最后一个 ] 之间的内容（如果配置是数组）
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1 and start < end:
            try:
                return json.loads(text[start:end+1])
            except json.JSONDecodeError:
                pass

        # 所有尝试都失败
        raise json.JSONDecodeError("无法从文本中提取有效的 JSON", text, 0)

    def _get_default_prompt(self, variables: Dict[str, str]) -> str:
        """
        获取默认 Prompt 模板（当模板文件不存在时使用）

        Args:
            variables: 模板变量

        Returns:
            默认 Prompt 字符串
        """
        return f"""【任务】
根据以下目标协议信息和参考上下文，生成一份完整的协议配置文件（config.json）。

{variables.get('target_summary', '')}

【参考上下文】
{variables.get('retrieved_context', '')}

【输出要求】
请输出严格符合以下 JSON Schema 的配置：
{variables.get('output_schema', '')}

【约束】
1. 严格输出 JSON 格式，不要包含任何 markdown 标记或额外说明文字
2. 如果信息不足无法确定的字段，使用 null 或 "TODO" 占位
3. 不允许虚构字段名和命令字，所有字段必须有依据
4. 保持 JSON 结构清晰，使用合适的缩进

请直接输出 JSON："""

    def _create_error_result(
        self,
        target: str,
        source_kb: str,
        top_k: int,
        model: str,
        temperature: float,
        error_message: str,
    ) -> GenerationResult:
        """创建错误结果"""
        return GenerationResult(
            config={"error": error_message, "target": target},
            raw_response="",
            target=target,
            source_kb=source_kb,
            retrieved_chunk_count=0,
            model=model,
            temperature=temperature,
            is_valid_json=False,
            error_message=error_message,
        )


def generate_config(
    target_doc_path: str,
    source_kb_dir: str,
    target_name: Optional[str] = None,
    top_k: int = 5,
    output_dir: Optional[str] = None,
) -> GenerationResult:
    """
    便捷函数：生成配置文件

    Args:
        target_doc_path: 目标协议文档路径
        source_kb_dir: 源协议知识库目录
        target_name: 目标协议名称
        top_k: 检索片段数量
        output_dir: 输出目录

    Returns:
        GenerationResult 生成结果

    Example:
        >>> result = generate_config(
        ...     "data/target_proto/dllg/dllg.docx",
        ...     "data/kb/gdwx",
        ...     target_name="dllg",
        ... )
        >>> print(result.output_path)
    """
    generator = ConfigGenerator()
    return generator.generate(
        target_doc_path=Path(target_doc_path),
        source_kb_dir=Path(source_kb_dir),
        target_name=target_name,
        top_k=top_k,
        output_dir=Path(output_dir) if output_dir else None,
    )
