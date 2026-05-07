"""
Handler 生成器模块（增强版，支持Pipeline）

采用模块化Pipeline策略：
1. Query Rewrite - 查询改写
2. Fusion Retrieval - 融合检索
3. Rerank - 精排
4. Context Compression - 上下文压缩
5. Structured Context Injection - 函数清单注入
6. Prompt Building - Prompt构建
7. LLM Generation - 代码生成

同时保留传统两阶段生成作为fallback。

输出：
- handler.c：完整的 C 代码文件
- handler_plan.md（可选）：设计草图文档
"""

import json
import re
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass, field
from datetime import datetime

from herta.generator.schemas import TargetProtocolSpec, RetrievedChunk
from herta.generator.target_parser import TargetParser
from herta.generator.retriever import KnowledgeRetriever
from herta.generator.prompt_loader import PromptLoader
from herta.generator.function_registry import FunctionRegistryBuilder, FunctionList, FunctionType
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


@dataclass
class HandlerGenerationResult:
    """Handler 生成结果（增强版）"""

    code: str
    plan: str
    target: str
    source_kb: str
    retrieved_chunk_count: int
    model: str
    temperature: float
    code_output_path: Optional[str] = None
    plan_output_path: Optional[str] = None
    generation_time: Optional[str] = None
    is_valid: bool = True
    error_message: Optional[str] = None
    
    # 新增：Pipeline相关字段
    function_manifest: Optional[FunctionList] = None  # 函数清单
    missing_functions: List[str] = field(default_factory=list)  # 缺失的函数
    pipeline_metadata: Dict[str, Any] = field(default_factory=dict)  # Pipeline执行元数据
    function_count: int = 0  # 函数总数

    def __post_init__(self):
        if self.generation_time is None:
            self.generation_time = datetime.now().isoformat()

    def save_code(self, output_path: Path) -> None:
        """保存代码到文件"""
        output_path = Path(output_path)
        ensure_dir(output_path.parent)
        output_path.write_text(self.code, encoding='utf-8')
        self.code_output_path = str(output_path)
        logger.info(f"Handler 代码已保存: {output_path}")

    def save_plan(self, output_path: Path) -> None:
        """保存设计计划到文件"""
        output_path = Path(output_path)
        ensure_dir(output_path.parent)
        output_path.write_text(self.plan, encoding='utf-8')
        self.plan_output_path = str(output_path)
        logger.info(f"Handler 设计计划已保存: {output_path}")
    
    def get_summary(self) -> str:
        """获取生成摘要"""
        lines = [
            f"Handler生成结果摘要:",
            f"  Target: {self.target}",
            f"  函数总数: {self.function_count}",
            f"  检索片段: {self.retrieved_chunk_count}",
            f"  缺失函数: {len(self.missing_functions)}",
        ]
        if self.missing_functions:
            lines.append(f"  缺失列表: {', '.join(self.missing_functions[:5])}")
        return "\n".join(lines)


class HandlerGenerator:
    """
    Handler 生成器（增强版，支持Pipeline）

    支持两种模式：
    1. Pipeline模式（推荐）：模块化7阶段处理
    2. 传统模式：两阶段生成（向后兼容）
    """

    PLAN_TEMPLATE = "generate_handler_plan.md"
    CODE_TEMPLATE = "generate_handler_code.md"
    DEFAULT_TOP_K = 20  # 两阶段检索：召回20
    RERANK_TOP_K = 5    # 精排后保留5
    DEFAULT_TEMPERATURE = 0.1

    def __init__(
        self,
        llm_client: Optional[BigModelClient] = None,
        prompt_loader: Optional[PromptLoader] = None,
        use_pipeline: bool = True,
        pipeline_config_path: Optional[str] = "config/rag_pipeline.yaml",
    ):
        self.llm_client = llm_client or BigModelClient()
        self.prompt_loader = prompt_loader or PromptLoader()

        settings = get_settings()
        self.default_model = settings.chat_model

        self.target_parser = TargetParser()
        self.function_builder = FunctionRegistryBuilder(self.llm_client)
        
        # Pipeline支持
        self.use_pipeline = use_pipeline
        self.pipeline: Optional[UnifiedPipeline] = None
        
        if use_pipeline and pipeline_config_path:
            try:
                # 加载handler专用的pipeline配置
                config = PipelineConfig.from_yaml(pipeline_config_path)
                handler_config = config.get_config_for_generation_type("handler_generation")
                self.pipeline = UnifiedPipeline(handler_config)
                logger.info("Pipeline模式已启用")
            except Exception as e:
                logger.warning(f"Pipeline初始化失败: {e}，回退到传统模式")
                self.use_pipeline = False
                self.pipeline = None

    def generate(
        self,
        target_doc_path: Path,
        source_kb_dir: Path,
        target_name: Optional[str] = None,
        top_k: int = DEFAULT_TOP_K,
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        output_dir: Optional[Path] = None,
        save_plan: bool = False,
        intermediate_dir: Optional[Path] = None,
        use_pipeline: Optional[bool] = None,  # 强制使用/禁用pipeline
    ) -> HandlerGenerationResult:
        """
        生成 Handler 代码

        支持两种模式：
        1. Pipeline模式（推荐）：Query改写→融合检索→精排→压缩→函数清单→生成
        2. 传统模式：两阶段生成（向后兼容）

        Args:
            target_doc_path: 目标协议文档路径
            source_kb_dir: 源协议知识库目录
            target_name: 目标协议名称
            top_k: 检索的参考片段数量（传统模式）/ 召回数量（Pipeline模式）
            model: 使用的 LLM 模型
            temperature: 生成温度
            output_dir: 代码输出目录
            save_plan: 是否保存设计计划
            intermediate_dir: 设计计划输出目录
            use_pipeline: 强制使用/禁用pipeline（None则使用初始化设置）

        Returns:
            HandlerGenerationResult 生成结果
        """
        # 确定使用哪种模式
        should_use_pipeline = use_pipeline if use_pipeline is not None else self.use_pipeline
        
        if should_use_pipeline and self.pipeline:
            return self._generate_with_pipeline(
                target_doc_path, source_kb_dir, target_name,
                model, temperature, output_dir, save_plan, intermediate_dir
            )
        else:
            return self._generate_traditional(
                target_doc_path, source_kb_dir, target_name,
                top_k, model, temperature, output_dir, save_plan, intermediate_dir
            )
    
    def _generate_with_pipeline(
        self,
        target_doc_path: Path,
        source_kb_dir: Path,
        target_name: Optional[str],
        model: Optional[str],
        temperature: float,
        output_dir: Optional[Path],
        save_plan: bool,
        intermediate_dir: Optional[Path],
    ) -> HandlerGenerationResult:
        """
        使用Pipeline模式生成Handler
        """
        start_time = datetime.now()
        model = model or self.default_model
        if target_name is None:
            target_name = Path(target_doc_path).stem
        
        logger.info("=" * 60)
        logger.info(f"[Pipeline模式] 开始生成 Handler: target={target_name}")
        logger.info("=" * 60)
        
        # 1. 解析目标协议
        try:
            target_spec = self.target_parser.parse(target_doc_path, target_name)
            logger.info(f"✓ 目标协议解析完成: {target_name}")
        except Exception as e:
            logger.error(f"解析失败: {e}")
            return self._create_error_result(target_name, str(source_kb_dir), 0, model, temperature, f"解析失败: {e}")
        
        # 2. 构建Pipeline上下文
        query = self._build_handler_retrieval_query(target_spec)
        context = PipelineContext(
            raw_query=query,
            target_spec=target_spec,
            generation_type="handler"
        )
        
        # 更新retrieval阶段的kb_dir配置
        self.pipeline.config.retrieval.params['kb_dir'] = str(source_kb_dir)
        
        # 3. 执行Pipeline
        try:
            final_context = self.pipeline.execute(context)
            logger.info(f"✓ Pipeline执行完成")
        except Exception as e:
            logger.error(f"Pipeline执行失败: {e}")
            return self._create_error_result(target_name, str(source_kb_dir), 0, model, temperature, f"Pipeline失败: {e}")
        
        # 4. 提取生成结果
        code = final_context.generated_content or ""
        
        # 5. 【关键】后验证：检查函数完整性
        function_list = final_context.function_manifest
        missing_funcs = []
        
        if function_list:
            missing_funcs = function_list.get_missing_functions(code)
            if missing_funcs:
                logger.warning(f"⚠ 检测到缺失函数: {len(missing_funcs)} 个")
                for func in missing_funcs[:5]:  # 只显示前5个
                    logger.warning(f"  - 缺失: {func.name}")
                
                # 补充生成缺失函数
                if len(missing_funcs) > 0:
                    logger.info("开始补充生成缺失函数...")
                    code = self._supplement_missing_functions(code, missing_funcs, target_spec, model, temperature)
        
        # 6. 构建结果
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # 生成简化的plan（从函数清单）
        plan = ""
        if function_list:
            plan = function_list.to_checklist()
        
        result = HandlerGenerationResult(
            code=code,
            plan=plan,
            target=target_name,
            source_kb=str(source_kb_dir),
            retrieved_chunk_count=len(final_context.compressed_context or []),
            model=model,
            temperature=temperature,
            is_valid=True,
            error_message=None,
            function_manifest=function_list,
            missing_functions=[f.name for f in missing_funcs],
            pipeline_metadata=final_context.metadata,
            function_count=function_list.total_count if function_list else 0,
        )
        
        # 7. 保存输出
        if output_dir is None:
            output_dir = Path(f"output/generated/{target_name}")
        output_dir = ensure_dir(output_dir)
        
        code_path = output_dir / f"{target_name}_handler.c"
        result.save_code(code_path)
        
        if save_plan and intermediate_dir:
            plan_path = ensure_dir(intermediate_dir) / "handler_plan.md"
            result.save_plan(plan_path)
        
        # 输出摘要
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ [Pipeline模式] Handler 生成完成！")
        logger.info("=" * 60)
        logger.info(f"  Target:       {target_name}")
        logger.info(f"  函数总数:     {result.function_count}")
        logger.info(f"  缺失函数:     {len(result.missing_functions)}")
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
        save_plan: bool,
        intermediate_dir: Optional[Path],
    ) -> HandlerGenerationResult:
        """
        使用传统模式生成Handler（向后兼容）
        """
        start_time = datetime.now()
        model = model or self.default_model
        if target_name is None:
            target_name = Path(target_doc_path).stem
        
        logger.info("=" * 60)
        logger.info(f"[传统模式] 开始生成 Handler: target={target_name}")
        logger.info("=" * 60)
        
        # 1. 解析目标协议
        try:
            target_spec = self.target_parser.parse(target_doc_path, target_name)
            logger.info(f"✓ 目标协议解析完成: {target_name}")
        except Exception as e:
            logger.error(f"解析失败: {e}")
            return self._create_error_result(target_name, str(source_kb_dir), top_k, model, temperature, f"解析失败: {e}")
        
        # 2. 检索知识库
        try:
            retriever = KnowledgeRetriever(source_kb_dir, self.llm_client)
            query = self._build_handler_retrieval_query(target_spec)
            logger.info(f"检索 Query: {query[:100]}...")
            
            retrieved_chunks = retriever.retrieve(query, top_k=top_k)
            logger.info(f"✓ 检索完成: {len(retrieved_chunks)} 个片段")
        except Exception as e:
            logger.error(f"检索失败: {e}")
            return self._create_error_result(target_name, str(source_kb_dir), top_k, model, temperature, f"检索失败: {e}")
        
        # 3. 【新增】构建函数清单
        function_list = self.function_builder.build_from_target(target_spec, retrieved_chunks)
        logger.info(f"✓ 函数清单: {function_list.total_count} 个函数")
        
        # 4. 生成设计草图
        logger.info("-" * 60)
        logger.info("阶段A：生成 Handler 设计草图...")
        logger.info("-" * 60)
        
        try:
            plan = self._generate_plan(target_spec, retrieved_chunks, model, temperature)
            logger.info("✓ 设计草图生成完成")
        except Exception as e:
            logger.error(f"生成设计草图失败: {e}")
            return self._create_error_result(target_name, str(source_kb_dir), top_k, model, temperature, f"阶段A失败: {e}")
        
        # 5. 生成完整代码（使用函数清单）
        logger.info("-" * 60)
        logger.info("阶段B：生成 Handler C 代码...")
        logger.info("-" * 60)
        
        try:
            code = self._generate_code_with_manifest(target_spec, plan, retrieved_chunks, function_list, model, temperature)
            logger.info("✓ 代码生成完成")
        except Exception as e:
            logger.error(f"生成代码失败: {e}")
            return self._create_error_result(target_name, str(source_kb_dir), top_k, model, temperature, f"阶段B失败: {e}")
        
        # 6. 【新增】后验证：检查函数完整性
        missing_funcs = function_list.get_missing_functions(code)
        if missing_funcs:
            logger.warning(f"⚠ 检测到缺失函数: {len(missing_funcs)} 个")
            code = self._supplement_missing_functions(code, missing_funcs, target_spec, model, temperature)
        
        # 7. 构建结果
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        result = HandlerGenerationResult(
            code=code,
            plan=plan,
            target=target_name,
            source_kb=str(source_kb_dir),
            retrieved_chunk_count=len(retrieved_chunks),
            model=model,
            temperature=temperature,
            is_valid=True,
            error_message=None,
            function_manifest=function_list,
            missing_functions=[f.name for f in missing_funcs],
            function_count=function_list.total_count,
        )
        
        # 8. 保存输出
        if output_dir is None:
            output_dir = Path(f"output/generated/{target_name}")
        output_dir = ensure_dir(output_dir)
        
        code_path = output_dir / f"{target_name}_handler.c"
        result.save_code(code_path)
        
        if save_plan:
            if intermediate_dir is None:
                intermediate_dir = Path(f"output/intermediate/{target_name}")
            plan_path = ensure_dir(intermediate_dir) / "handler_plan.md"
            result.save_plan(plan_path)
        
        # 输出摘要
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ [传统模式] Handler 生成完成！")
        logger.info("=" * 60)
        logger.info(f"  Target:       {target_name}")
        logger.info(f"  函数总数:     {result.function_count}")
        logger.info(f"  缺失函数:     {len(result.missing_functions)}")
        logger.info(f"  检索片段:     {result.retrieved_chunk_count}")
        logger.info(f"  生成耗时:     {duration:.2f} 秒")
        logger.info("=" * 60)
        
        return result

    def _build_handler_retrieval_query(self, target_spec: TargetProtocolSpec) -> str:
        """
        构造面向 handler 的检索 Query

        重点面向：
        - handler 处理流程
        - 命令分发逻辑
        - 遥测解析逻辑
        - 内部通信逻辑
        - 相关函数结构
        - 参考 C 代码片段
        """
        query_parts = [
            f"{target_spec.target_name} handler 处理流程",
            "命令分发 command dispatch",
            "遥测解析 telemetry parsing",
            "内部通信 internal communication",
            "C 代码实现 函数结构",
            "handle_cmd process_command",
            "消息解析 协议处理",
        ]

        # 添加摘要关键词
        if target_spec.summary:
            summary_keywords = target_spec.summary[:80].replace('\n', ' ')
            query_parts.append(summary_keywords)

        return " ".join(query_parts)

    def _generate_plan(
        self,
        target_spec: TargetProtocolSpec,
        retrieved_chunks: list[RetrievedChunk],
        model: str,
        temperature: float,
    ) -> str:
        """
        阶段A：生成 Handler 设计草图
        """
        # 准备上下文
        context_text = self._format_retrieved_context(retrieved_chunks)
        target_summary = self._format_target_summary(target_spec)

        # 准备模板变量
        variables = {
            "target_summary": target_summary,
            "retrieved_context": context_text,
        }

        # 加载并渲染 Prompt
        try:
            prompt = self.prompt_loader.load_and_render(self.PLAN_TEMPLATE, variables)
        except FileNotFoundError:
            logger.warning(f"模板 {self.PLAN_TEMPLATE} 不存在，使用默认模板")
            prompt = self._get_default_plan_prompt(variables)

        # 调用 LLM
        messages = [
            {"role": "system", "content": "你是一位资深的嵌入式系统架构师，专注于协议处理模块的设计。"},
            {"role": "user", "content": prompt},
        ]

        plan = self.llm_client.chat(
            messages=messages,
            model=model,
            temperature=temperature,
        )

        return plan

    def _generate_code(
        self,
        target_spec: TargetProtocolSpec,
        plan: str,
        retrieved_chunks: list[RetrievedChunk],
        model: str,
        temperature: float,
    ) -> str:
        """
        阶段B：基于 Plan 生成完整 C 代码（传统模式，无函数清单）
        """
        return self._generate_code_with_manifest(target_spec, plan, retrieved_chunks, None, model, temperature)
    
    def _generate_code_with_manifest(
        self,
        target_spec: TargetProtocolSpec,
        plan: str,
        retrieved_chunks: list[RetrievedChunk],
        function_list: Optional[FunctionList],
        model: str,
        temperature: float,
    ) -> str:
        """
        阶段B：基于 Plan 和函数清单生成完整 C 代码
        """
        # 准备上下文
        context_text = self._format_retrieved_context(retrieved_chunks, max_length=6000)
        target_summary = self._format_target_summary(target_spec)

        # 准备模板变量
        variables = {
            "target_summary": target_summary,
            "handler_plan": plan,
            "retrieved_context": context_text,
        }
        
        # 添加函数清单（如果有）
        if function_list:
            variables["function_manifest"] = function_list.to_manifest()
            variables["function_checklist"] = function_list.to_checklist()
            variables["required_function_count"] = function_list.total_count
            
            # 构建命令映射
            cmd_mapping = "\n".join([
                f"  {f.cmd_code} -> {f.name} ({f.display_name})"
                for f in function_list.get_by_type(FunctionType.CMD)
                if f.cmd_code
            ])
            variables["cmd_mapping"] = cmd_mapping

        # 加载并渲染 Prompt
        try:
            prompt = self.prompt_loader.load_and_render(self.CODE_TEMPLATE, variables)
        except FileNotFoundError:
            logger.warning(f"模板 {self.CODE_TEMPLATE} 不存在，使用默认模板")
            prompt = self._get_default_code_prompt_with_manifest(variables, function_list)

        # 调用 LLM
        system_prompt = """你是一位资深的嵌入式 C 语言开发者，擅长编写高效、健壮的协议处理代码。
你必须严格按照函数清单生成所有必需的函数，不能遗漏任何函数。
每个函数都需要有完整的实现，不确定的地方用 TODO 标记。
"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        code = self.llm_client.chat(
            messages=messages,
            model=model,
            temperature=temperature,
        )

        # 清理代码（移除可能的 markdown 围栏）
        code = self._clean_code_output(code)

        return code
    
    def _supplement_missing_functions(
        self,
        existing_code: str,
        missing_funcs: List[Any],  # List[FunctionSpec]
        target_spec: TargetProtocolSpec,
        model: str,
        temperature: float,
    ) -> str:
        """
        补充生成缺失的函数
        """
        if not missing_funcs:
            return existing_code
        
        logger.info(f"开始补充生成 {len(missing_funcs)} 个缺失函数...")
        
        # 构建补充函数描述
        func_specs_text = "\n\n".join([
            f"函数: {f.name}\n"
            f"类型: {f.func_type.value}\n"
            f"描述: {f.description}\n"
            f"输入: {[p.get('name') for p in f.input_params]}\n"
            f"输出: {[p.get('name') for p in f.output_params]}"
            for f in missing_funcs
        ])
        
        prompt = f"""【任务】
为以下缺失的函数生成C语言实现。

【已有代码上下文】（前2000字符）
```c
{existing_code[:2000]}
```

【需要补充的函数】
{func_specs_text}

【要求】
1. 生成的函数必须与已有代码风格一致
2. 使用相同的命名规范和数据结构
3. 确保函数签名与描述一致
4. 只输出函数实现代码，不要其他内容
5. 每个函数包含必要的注释说明

【输出格式】
直接输出C代码，用```c包裹。
"""

        try:
            messages = [
                {"role": "system", "content": "你是一位资深的嵌入式C开发者。"},
                {"role": "user", "content": prompt},
            ]
            
            supplement_code = self.llm_client.chat(
                messages=messages,
                model=model,
                temperature=temperature,
            )
            
            # 提取代码
            supplement_clean = self._clean_code_output(supplement_code)
            
            # 追加到现有代码
            return existing_code + "\n\n/* === 补充生成的函数 === */\n\n" + supplement_clean
            
        except Exception as e:
            logger.error(f"补充生成失败: {e}")
            return existing_code

    def _format_retrieved_context(
        self,
        chunks: list[RetrievedChunk],
        max_length: int = 8000,
    ) -> str:
        """格式化检索到的上下文"""
        if not chunks:
            return "（未检索到相关参考信息）"

        sections = []
        for i, chunk in enumerate(chunks, 1):
            sections.append(f"【参考片段 {i}】来源: {chunk.source} | 文件: {chunk.file} | 相关度: {chunk.score:.3f}\n{chunk.text}\n---")

        context = "\n\n".join(sections)

        if len(context) > max_length:
            context = context[:max_length] + "\n...（上下文已截断）"

        return context

    def _format_target_summary(self, target_spec: TargetProtocolSpec) -> str:
        """格式化目标协议摘要"""
        sections_info = ""
        if target_spec.sections:
            sections_info = "\n文档结构:\n" + "\n".join(
                f"  - {s.get('title', s.get('name', '未命名章节'))}"
                for s in target_spec.sections[:10]
            )
            if len(target_spec.sections) > 10:
                sections_info += f"\n  ... 等共 {len(target_spec.sections)} 个章节"

        return f"""【目标协议】
名称: {target_spec.target_name}
文档路径: {target_spec.document_path}
摘要: {target_spec.summary}{sections_info}
"""

    def _clean_code_output(self, code: str) -> str:
        """清理 LLM 输出的代码"""
        code = code.strip()

        # 移除 ```c 或 ``` 围栏
        if code.startswith("```"):
            lines = code.split('\n')
            # 移除第一行的 ```c 或 ```
            if lines[0].startswith("```"):
                lines = lines[1:]
            # 移除最后一行的 ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = '\n'.join(lines).strip()

        return code

    def _validate_code(self, code: str) -> bool:
        """
        简单验证代码有效性

        检查：
        - 代码不为空
        - 包含基本的 C 语法结构
        - 不是纯文本/说明
        """
        if not code or len(code) < 100:
            return False

        # 检查是否包含 C 代码特征
        c_indicators = [
            "#include",
            "int ",
            "void ",
            "static ",
            "{",
            "}",
            ";",
            "/*",
            "//",
        ]

        indicator_count = sum(1 for ind in c_indicators if ind in code)
        return indicator_count >= 3  # 至少包含3个C特征

    def _get_default_plan_prompt(self, variables: Dict[str, str]) -> str:
        """默认设计计划 Prompt（模板不存在时使用）"""
        return f"""请为以下目标协议设计一份 handler 实现计划：

{variables.get('target_summary', '')}

参考信息：
{variables.get('retrieved_context', '')}

请输出结构化的设计计划，包括：
1. 概述和职责
2. 函数列表（含输入输出）
3. 主入口函数设计
4. 命令分发逻辑
5. 遥测处理逻辑
6. 内部通信逻辑
7. 辅助函数设计
8. 未知点与 TODO

只输出设计文档，不要包含具体的 C 代码实现。"""

    def _get_default_code_prompt(self, variables: Dict[str, str]) -> str:
        """默认代码生成 Prompt（模板不存在时使用）"""
        return self._get_default_code_prompt_with_manifest(variables, None)
    
    def _get_default_code_prompt_with_manifest(
        self,
        variables: Dict[str, str],
        function_list: Optional[FunctionList],
    ) -> str:
        """默认代码生成 Prompt（支持函数清单）"""
        manifest_section = ""
        if function_list:
            manifest_section = f"""
【必须实现的函数清单】共 {function_list.total_count} 个函数
{variables.get('function_manifest', function_list.to_manifest())}

【生成后检查清单】
{variables.get('function_checklist', function_list.to_checklist())}

【命令处理映射】
{variables.get('cmd_mapping', '')}
"""
        
        return f"""【任务】
生成完整的 C 语言 handler 实现代码。

{variables.get('target_summary', '')}

{manifest_section}

【设计计划】
{variables.get('handler_plan', '')}

【参考代码片段】
{variables.get('retrieved_context', '')}

【强制要求】
1. **必须生成清单中所有函数**，每个函数都需要有完整实现
2. 函数名称必须与清单完全一致
3. 命令处理函数必须正确处理对应的命令字
4. 不确定的地方用 /* TODO: ... */ 标记，但不能省略函数框架
5. 保持代码风格统一，包含必要的错误处理
6. 包含所有必要的 include、宏定义、结构体声明

【输出格式】
直接输出C代码，用```c包裹。
生成完成后在注释中标记已实现的所有函数名。"""

    def _create_error_result(
        self,
        target: str,
        source_kb: str,
        top_k: int,
        model: str,
        temperature: float,
        error_message: str,
    ) -> HandlerGenerationResult:
        """创建错误结果"""
        return HandlerGenerationResult(
            code=f"/* Error: {error_message} */",
            plan=f"/* Error: {error_message} */",
            target=target,
            source_kb=source_kb,
            retrieved_chunk_count=0,
            model=model,
            temperature=temperature,
            is_valid=False,
            error_message=error_message,
        )


def generate_handler(
    target_doc_path: str,
    source_kb_dir: str,
    target_name: Optional[str] = None,
    top_k: int = 8,
    save_plan: bool = False,
    output_dir: Optional[str] = None,
) -> HandlerGenerationResult:
    """
    便捷函数：生成 Handler 代码

    Args:
        target_doc_path: 目标协议文档路径
        source_kb_dir: 源协议知识库目录
        target_name: 目标协议名称
        top_k: 检索片段数量
        save_plan: 是否保存设计计划
        output_dir: 输出目录

    Returns:
        HandlerGenerationResult 生成结果
    """
    generator = HandlerGenerator()
    return generator.generate(
        target_doc_path=Path(target_doc_path),
        source_kb_dir=Path(source_kb_dir),
        target_name=target_name,
        top_k=top_k,
        save_plan=save_plan,
        output_dir=Path(output_dir) if output_dir else None,
    )
