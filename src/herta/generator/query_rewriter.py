"""
Query改写模块

将原始查询改写为检索友好的形式：
1. 代码语义化（强调handler、dispatch等代码概念）
2. 结构化（提取关键元素）
3. LLM增强（智能扩展）
"""

import re
from enum import Enum
from typing import Optional, List, Callable
from dataclasses import dataclass

from herta.llm.client import BigModelClient
from herta.logging import get_logger

logger = get_logger(__name__)


class RewriteMode(Enum):
    """改写模式"""
    CODE_SEMANTIC = "code_semantic"    # 代码语义化
    STRUCTURED = "structured"          # 结构化
    LLM_ENHANCED = "llm_enhanced"      # LLM智能增强
    HYBRID = "hybrid"                  # 混合模式


@dataclass
class RewriteResult:
    """改写结果"""
    original_query: str
    rewritten_query: str
    mode: RewriteMode
    expansions: List[str] = None  # 扩展的查询变体
    
    def __post_init__(self):
        if self.expansions is None:
            self.expansions = []


class QueryRewriter:
    """
    Query改写器
    
    将原始查询改写为检索友好的形式
    """
    
    # 代码语义关键词映射
    CODE_PATTERNS = {
        "handler": ["handler", "处理函数", "消息处理", "cmd handler", "event handler"],
        "dispatch": ["dispatch", "分发", "命令分发", "cmd dispatch", "路由", "route"],
        "parse": ["parse", "解析", "消息解析", "packet parse", "解码"],
        "telemetry": ["telemetry", "遥测", "遥测数据", "状态上报", "status report"],
        "command": ["command", "cmd", "命令", "指令", "控制命令", "command handler"],
        "struct": ["struct", "结构体", "消息结构", "数据格式", "packet format"],
        "callback": ["callback", "回调", "通知机制", "事件回调", "hook"],
        "protocol": ["protocol", "协议", "通信协议", "消息协议"],
        "init": ["init", "初始化", "模块初始化", "init handler"],
        "process": ["process", "处理入口", "主处理", "process message"],
    }
    
    def __init__(
        self,
        llm_client: Optional[BigModelClient] = None,
        rewrite_mode: str = "code_semantic",
    ):
        """
        初始化Query改写器
        
        Args:
            llm_client: LLM客户端，用于LLM增强模式
            rewrite_mode: 改写模式
        """
        self.llm_client = llm_client or BigModelClient()
        self.rewrite_mode = RewriteMode(rewrite_mode)
        
        logger.info(f"QueryRewriter初始化: mode={rewrite_mode}")
    
    def rewrite(
        self,
        original_query: str,
        context_type: str = "handler",  # "config" | "handler"
    ) -> RewriteResult:
        """
        改写原始查询
        
        Args:
            original_query: 原始查询字符串
            context_type: 上下文类型，影响改写策略
        
        Returns:
            RewriteResult改写结果
        """
        logger.debug(f"改写查询: '{original_query[:50]}...' (type={context_type})")
        
        if self.rewrite_mode == RewriteMode.CODE_SEMANTIC:
            rewritten = self._build_code_semantic_query(original_query, context_type)
            expansions = []
        
        elif self.rewrite_mode == RewriteMode.STRUCTURED:
            rewritten = self._build_structured_query(original_query, context_type)
            expansions = []
        
        elif self.rewrite_mode == RewriteMode.LLM_ENHANCED:
            rewritten, expansions = self._llm_rewrite(original_query, context_type)
        
        elif self.rewrite_mode == RewriteMode.HYBRID:
            # 先代码语义化，再LLM增强
            base = self._build_code_semantic_query(original_query, context_type)
            rewritten, expansions = self._llm_rewrite(base, context_type)
        
        else:
            rewritten = original_query
            expansions = []
        
        result = RewriteResult(
            original_query=original_query,
            rewritten_query=rewritten,
            mode=self.rewrite_mode,
            expansions=expansions
        )
        
        logger.info(f"查询改写完成: '{original_query[:30]}...' -> '{rewritten[:50]}...'")
        return result
    
    def _build_code_semantic_query(
        self,
        query: str,
        context_type: str,
    ) -> str:
        """
        构建代码语义化查询（基于规则）
        
        示例转换：
        "dllg协议处理" -> "dllg protocol handler dispatch logic cmd handler structure"
        """
        query_lower = query.lower()
        enhanced_terms = []
        
        # 1. 保留原始查询中的协议名/标识符
        # 提取驼峰命名或下划线命名的标识符
        identifiers = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', query)
        enhanced_terms.extend(identifiers)
        
        # 2. 根据关键词映射添加代码语义
        for concept, terms in self.CODE_PATTERNS.items():
            # 检查原始查询是否包含相关概念
            if any(term.lower() in query_lower for term in terms):
                # 添加对应的代码术语（取前2个）
                enhanced_terms.extend(terms[:2])
        
        # 3. 根据context_type添加特定术语
        if context_type == "handler":
            handler_terms = [
                "handler implementation",
                "command dispatch",
                "message processing",
                "C code"
            ]
            enhanced_terms.extend(handler_terms)
        
        elif context_type == "config":
            config_terms = [
                "configuration",
                "config fields",
                "parameter mapping",
                "JSON schema"
            ]
            enhanced_terms.extend(config_terms)
        
        # 4. 去重并保持顺序
        seen = set()
        unique_terms = []
        for term in enhanced_terms:
            term_lower = term.lower()
            if term_lower not in seen:
                seen.add(term_lower)
                unique_terms.append(term)
        
        # 5. 组合成最终查询
        rewritten = " ".join(unique_terms)
        
        return rewritten if rewritten else query
    
    def _build_structured_query(
        self,
        query: str,
        context_type: str,
    ) -> str:
        """
        构建结构化查询
        
        提取query中的关键元素并重组：
        - 协议名称
        - 功能意图
        - 目标类型
        """
        # 提取协议名（通常是大写字母或特定格式）
        protocol_pattern = r'\b([A-Z]{2,}|[a-z]+_?[a-z]+)\b'
        protocols = re.findall(protocol_pattern, query)
        
        # 构建结构化表示
        parts = []
        
        # 协议标识
        if protocols:
            parts.append(f"protocol:{protocols[0]}")
        
        # 功能意图
        intent_keywords = {
            "handler": ["handle", "process", "dispatch"],
            "config": ["config", "configuration", "field", "parameter"],
            "parse": ["parse", "decode", "unpack"],
        }
        
        for intent, keywords in intent_keywords.items():
            if any(kw in query.lower() for kw in keywords):
                parts.append(f"intent:{intent}")
                break
        
        # 目标类型
        type_keywords = {
            "function": ["function", "handler", "api"],
            "structure": ["struct", "format", "packet"],
            "field": ["field", "parameter", "variable"],
        }
        
        for t, keywords in type_keywords.items():
            if any(kw in query.lower() for kw in keywords):
                parts.append(f"type:{t}")
                break
        
        # 原始查询作为补充
        parts.append(f"raw:{query}")
        
        return " | ".join(parts)
    
    def _llm_rewrite(
        self,
        query: str,
        context_type: str,
    ) -> tuple[str, List[str]]:
        """
        使用LLM进行智能改写
        
        返回：(改写后查询, 扩展查询列表)
        """
        prompt = f"""【任务】
请将以下查询改写为更适合代码检索的形式，并生成2-3个语义相近的扩展查询。

【原始查询】
{query}

【上下文类型】
{context_type} ("handler"表示需要查找代码实现，"config"表示需要查找配置定义)

【改写要求】
1. 提取关键的技术术语和标识符
2. 添加相关的代码语义词汇（如handler、dispatch、parse等）
3. 使用英文技术术语增强检索效果
4. 生成多个变体以覆盖不同表达方式

【输出格式】
主改写: [改写后的主要查询]
扩展1: [第一个扩展查询]
扩展2: [第二个扩展查询]
扩展3: [第三个扩展查询(可选)]

请直接输出格式化的结果。"""
        
        try:
            response = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            # 解析响应
            lines = response.strip().split('\n')
            main_query = query
            expansions = []
            
            for line in lines:
                line = line.strip()
                if line.startswith("主改写:") or line.startswith("改写:"):
                    main_query = line.split(":", 1)[1].strip()
                elif line.startswith("扩展") and ":" in line:
                    expansion = line.split(":", 1)[1].strip()
                    if expansion:
                        expansions.append(expansion)
            
            return main_query, expansions
            
        except Exception as e:
            logger.warning(f"LLM改写失败: {e}，使用原始查询")
            return query, []


# 便捷函数
def rewrite_query(
    query: str,
    context_type: str = "handler",
    mode: str = "code_semantic",
    llm_client: Optional[BigModelClient] = None,
) -> str:
    """
    便捷函数：改写查询
    
    Args:
        query: 原始查询
        context_type: 上下文类型
        mode: 改写模式
        llm_client: LLM客户端
    
    Returns:
        改写后的查询字符串
    
    Example:
        >>> rewritten = rewrite_query("dllg协议处理", "handler")
        >>> print(rewritten)
        "dllg protocol handler dispatch logic cmd handler structure"
    """
    rewriter = QueryRewriter(llm_client=llm_client, rewrite_mode=mode)
    result = rewriter.rewrite(query, context_type)
    return result.rewritten_query
