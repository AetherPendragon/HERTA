"""
上下文压缩模块

对检索到的chunks进行智能压缩，提取与当前任务相关的部分，
丢弃无关内容，同时保持代码结构完整性。
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum

from herta.generator.schemas import RetrievedChunk
from herta.llm.client import BigModelClient
from herta.logging import get_logger

logger = get_logger(__name__)


class TaskType(Enum):
    """任务类型"""
    CONFIG = "config"
    HANDLER = "handler"
    AUTO = "auto"


@dataclass
class ChunkCompressionInfo:
    """
    单个Chunk的压缩信息
    
    记录压缩前后的状态和处理决策
    """
    original_chunk: RetrievedChunk     # 原始chunk
    is_relevant: bool                  # 是否与任务相关
    relevance_score: float             # 相关性分数（0-10）
    compressed_text: Optional[str]     # 压缩后的文本（None表示丢弃）
    extracted_parts: List[str]         # 提取的相关部分列表
    discard_reason: Optional[str]      # 丢弃原因（如果丢弃）
    compression_ratio: float           # 压缩比例（0-1，越小压缩越多）
    code_blocks_preserved: List[str] = field(default_factory=list)   # 保留的代码块


@dataclass
class CompressionResult:
    """
    压缩结果容器
    
    包含所有压缩后的chunks和统计信息
    """
    compressed_chunks: List[RetrievedChunk]  # 压缩后的chunk列表（已丢弃的不包含）
    discarded_count: int                    # 丢弃的chunk数量
    original_token_count: int               # 原始总token数（估算）
    compressed_token_count: int             # 压缩后总token数（估算）
    compression_stats: List[ChunkCompressionInfo]  # 详细压缩信息
    
    @property
    def compression_ratio(self) -> float:
        """整体压缩比例"""
        if self.original_token_count == 0:
            return 1.0
        return self.compressed_token_count / self.original_token_count
    
    @property
    def preservation_rate(self) -> float:
        """保留比例（1 - 丢弃率）"""
        total = len(self.compression_stats)
        if total == 0:
            return 1.0
        kept = total - self.discarded_count
        return kept / total
    
    def get_summary(self) -> str:
        """获取压缩摘要"""
        return (
            f"压缩统计: {len(self.compression_stats)} → {len(self.compressed_chunks)} chunks "
            f"(丢弃{self.discarded_count}, 保留{self.preservation_rate:.0%}, "
            f"压缩比{self.compression_ratio:.1%})"
        )


class ContextCompressor:
    """
    上下文压缩器
    
    对检索到的chunks进行智能压缩，提取与当前任务相关的部分，
    丢弃无关内容，同时保持代码结构完整性。
    """
    
    # 默认Prompt模板
    RELEVANCE_ANALYSIS_PROMPT = """【任务】
分析以下知识库片段与用户查询的相关性（0-10分）。

【用户查询】
{query}

【知识库片段】
来源: {source}
类型: {kind}
内容:
---
{text}
---

【任务类型】
{task_type}

【评分标准】（0-10分）
10分: 完美匹配 - 直接包含所需的完整信息
8-9分: 高度相关 - 包含核心信息
6-7分: 中度相关 - 包含部分相关信息
4-5分: 弱相关 - 仅有轻微关联
0-3分: 无关 - 与查询无明显关系

【输出格式】
评分: [数字]
理由: [一句话说明]
是否相关: [是/否]

请只输出上述格式内容。"""

    CODE_EXTRACTION_PROMPT = """【任务】
从以下代码片段中提取与"{query}"相关的部分，保持函数结构完整。

【原始代码片段】
来源: {source}
```
{text}
```

【提取要求】
1. 只保留与查询直接相关的函数/结构体
2. 保持代码结构完整（不能截断函数）
3. 保留必要的include和宏定义
4. 去除无关的辅助函数
5. 保留关键注释

【输出格式】
直接输出提取后的代码，用```c包裹。
如果完全不相关，输出: IRRELEVANT"""

    DOC_EXTRACTION_PROMPT = """【任务】
从以下文档片段中提取与"{query}"相关的内容。

【原始文档片段】
来源: {source}
{text}

【提取要求】
1. 保留与查询直接相关的定义和描述
2. 去除冗余的示例和说明
3. 保留关键字段名、命令字等标识符
4. 压缩为简洁的要点形式

【输出格式】
直接输出提取后的内容。
如果完全不相关，输出: IRRELEVANT"""

    def __init__(
        self,
        llm_client: Optional[BigModelClient] = None,
        relevance_threshold: float = 6.0,        # 相关性阈值
        max_compression_ratio: float = 0.5,      # 最大压缩比例
        preserve_code_structure: bool = True,     # 是否保持代码结构
        preserve_function_boundaries: bool = True, # 是否保持函数边界
    ):
        """
        初始化上下文压缩器
        
        Args:
            llm_client: LLM客户端，用于分析相关性和提取内容
            relevance_threshold: 相关性阈值（0-10），低于此值的chunk被过滤
            max_compression_ratio: 最大压缩比例（保留至少此比例的内容）
            preserve_code_structure: 是否保持代码结构完整
            preserve_function_boundaries: 是否保持函数边界
        """
        self.llm_client = llm_client or BigModelClient()
        self.relevance_threshold = relevance_threshold
        self.max_compression_ratio = max_compression_ratio
        self.preserve_code_structure = preserve_code_structure
        self.preserve_function_boundaries = preserve_function_boundaries
        
        logger.info(f"ContextCompressor初始化: threshold={relevance_threshold}")
    
    def compress(
        self,
        query: str,
        chunks: List[RetrievedChunk],
        task_type: str = "auto",
    ) -> CompressionResult:
        """
        压缩上下文（主入口）
        
        流程：
        1. 分析每个chunk与query的相关性
        2. 丢弃明显无关的chunk
        3. 对保留的chunk提取相关部分
        4. 重新组装成压缩后的chunks
        
        Args:
            query: 原始查询（已改写）
            chunks: 检索到的原始chunks
            task_type: 任务类型（config/handler/auto）
        
        Returns:
            CompressionResult压缩结果
        """
        if not chunks:
            return CompressionResult(
                compressed_chunks=[],
                discarded_count=0,
                original_token_count=0,
                compressed_token_count=0,
                compression_stats=[]
            )
        
        logger.info(f"开始上下文压缩: {len(chunks)} chunks, query='{query[:40]}...'")
        
        # 估算原始token数（简单估算：1token ≈ 4字符）
        original_token_count = sum(len(c.text) // 4 for c in chunks)
        
        compression_stats = []
        compressed_chunks = []
        discarded_count = 0
        
        for i, chunk in enumerate(chunks):
            logger.debug(f"处理chunk {i+1}/{len(chunks)}: {chunk.chunk_id}")
            
            # 分析相关性
            relevance_score, is_relevant, reason = self._analyze_relevance(
                query, chunk, task_type
            )
            
            # 判断是否丢弃
            if not is_relevant or relevance_score < self.relevance_threshold:
                compression_stats.append(ChunkCompressionInfo(
                    original_chunk=chunk,
                    is_relevant=False,
                    relevance_score=relevance_score,
                    compressed_text=None,
                    extracted_parts=[],
                    discard_reason=reason or f"相关性评分{relevance_score:.1f}低于阈值{self.relevance_threshold}",
                    compression_ratio=0.0,
                    code_blocks_preserved=[]
                ))
                discarded_count += 1
                continue
            
            # 提取相关部分
            compressed_text, extracted_parts, code_blocks = self._extract_relevant_parts(
                query, chunk, task_type, relevance_score
            )
            
            if compressed_text is None or compressed_text == "IRRELEVANT":
                compression_stats.append(ChunkCompressionInfo(
                    original_chunk=chunk,
                    is_relevant=False,
                    relevance_score=relevance_score,
                    compressed_text=None,
                    extracted_parts=[],
                    discard_reason="提取结果为IRRELEVANT",
                    compression_ratio=0.0,
                    code_blocks_preserved=[]
                ))
                discarded_count += 1
                continue
            
            # 计算压缩比例
            original_len = len(chunk.text)
            compressed_len = len(compressed_text)
            compression_ratio = compressed_len / original_len if original_len > 0 else 1.0
            
            # 创建压缩后的chunk
            compressed_chunk = RetrievedChunk(
                chunk_id=chunk.chunk_id,
                source=chunk.source,
                file=chunk.file,
                kind=chunk.kind,
                section=chunk.section,
                text=compressed_text,
                score=chunk.score,  # 保持原始检索分数
                token_count=len(compressed_text) // 4,  # 估算
                metadata={
                    **chunk.metadata,
                    'compressed': True,
                    'original_length': original_len,
                    'compression_ratio': compression_ratio,
                    'relevance_score': relevance_score,
                    'extracted_parts': extracted_parts,
                }
            )
            
            compression_stats.append(ChunkCompressionInfo(
                original_chunk=chunk,
                is_relevant=True,
                relevance_score=relevance_score,
                compressed_text=compressed_text,
                extracted_parts=extracted_parts,
                discard_reason=None,
                compression_ratio=compression_ratio,
                code_blocks_preserved=code_blocks
            ))
            
            compressed_chunks.append(compressed_chunk)
        
        # 估算压缩后token数
        compressed_token_count = sum(len(c.text) // 4 for c in compressed_chunks)
        
        result = CompressionResult(
            compressed_chunks=compressed_chunks,
            discarded_count=discarded_count,
            original_token_count=original_token_count,
            compressed_token_count=compressed_token_count,
            compression_stats=compression_stats
        )
        
        logger.info(result.get_summary())
        return result
    
    def _analyze_relevance(
        self,
        query: str,
        chunk: RetrievedChunk,
        task_type: str,
    ) -> Tuple[float, bool, str]:
        """
        分析chunk与query的相关性
        
        使用LLM评分（0-10分），并给出理由
        
        Returns:
            (score, is_relevant, reason) 元组
        """
        # 构造prompt
        prompt = self.RELEVANCE_ANALYSIS_PROMPT.format(
            query=query,
            source=chunk.source,
            kind=chunk.kind,
            text=chunk.text[:1500],  # 限制长度避免token过多
            task_type=task_type
        )
        
        try:
            response = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            
            # 解析响应
            score = 5.0  # 默认中等相关
            is_relevant = True
            reason = ""
            
            for line in response.split('\n'):
                line = line.strip()
                if line.startswith("评分:") or line.startswith("分数:"):
                    try:
                        score_str = line.split(":")[1].strip()
                        score = float(score_str)
                    except (ValueError, IndexError):
                        pass
                elif line.startswith("是否相关:"):
                    is_relevant = "是" in line or "yes" in line.lower()
                elif line.startswith("理由:"):
                    reason = line.split(":", 1)[1].strip()
            
            return score, is_relevant and score >= self.relevance_threshold, reason
            
        except Exception as e:
            logger.warning(f"相关性分析失败: {e}，使用默认评分")
            return 5.0, True, "分析失败，默认保留"
    
    def _extract_relevant_parts(
        self,
        query: str,
        chunk: RetrievedChunk,
        task_type: str,
        relevance_score: float,
    ) -> Tuple[Optional[str], List[str], List[str]]:
        """
        从chunk中提取与任务相关的部分
        
        Returns:
            (compressed_text, extracted_parts, code_blocks) 元组
        """
        # 根据chunk类型选择提取策略
        if chunk.kind == "code":
            return self._compress_code_chunk(query, chunk, relevance_score)
        else:
            return self._compress_doc_chunk(query, chunk, relevance_score)
    
    def _compress_code_chunk(
        self,
        query: str,
        chunk: RetrievedChunk,
        relevance_score: float,
    ) -> Tuple[Optional[str], List[str], List[str]]:
        """
        专门处理代码类型的chunk压缩
        
        关键约束：保持函数结构完整
        """
        # 高相关性（8-10）：保留大部分内容，仅去除明显无关部分
        if relevance_score >= 8.0:
            # 使用LLM提取关键部分
            prompt = self.CODE_EXTRACTION_PROMPT.format(
                query=query,
                source=chunk.source,
                text=chunk.text[:2000]
            )
            
            try:
                response = self.llm_client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1
                )
                
                # 提取代码块
                code_blocks = self._extract_code_blocks(response)
                
                if "IRRELEVANT" in response.upper():
                    return None, [], []
                
                # 从响应中提取代码
                extracted = self._extract_code_from_response(response)
                if extracted:
                    return extracted, ["高相关代码提取"], code_blocks
                
            except Exception as e:
                logger.warning(f"代码提取失败: {e}")
        
        # 中等相关性（5-7）：选择性提取
        elif relevance_score >= 5.0:
            # 识别函数边界并选择性保留
            functions = self._identify_function_boundaries(chunk.text)
            
            # 选择与查询相关的函数
            relevant_funcs = self._select_relevant_functions(functions, query)
            
            if relevant_funcs:
                # 组装保留的函数
                preserved_code = self._assemble_functions(chunk.text, relevant_funcs)
                return preserved_code, [f"保留函数: {f['name']}" for f in relevant_funcs], []
        
        # 低相关性：返回IRRELEVANT
        return "IRRELEVANT", [], []
    
    def _compress_doc_chunk(
        self,
        query: str,
        chunk: RetrievedChunk,
        relevance_score: float,
    ) -> Tuple[Optional[str], List[str], List[str]]:
        """
        处理文档类型的chunk压缩
        """
        # 高相关性：提取关键段落
        if relevance_score >= 7.0:
            prompt = self.DOC_EXTRACTION_PROMPT.format(
                query=query,
                source=chunk.source,
                text=chunk.text[:2000]
            )
            
            try:
                response = self.llm_client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1
                )
                
                if "IRRELEVANT" in response.upper():
                    return None, [], []
                
                return response.strip(), ["文档关键信息提取"], []
                
            except Exception as e:
                logger.warning(f"文档提取失败: {e}")
        
        # 中等相关性：返回前N行
        elif relevance_score >= 5.0:
            lines = chunk.text.split('\n')[:20]  # 保留前20行
            return '\n'.join(lines), ["保留前20行"], []
        
        return "IRRELEVANT", [], []
    
    def _extract_code_blocks(self, text: str) -> List[str]:
        """从文本中提取代码块"""
        pattern = r'```(?:c)?\s*\n(.*?)\n```'
        matches = re.findall(pattern, text, re.DOTALL)
        return matches
    
    def _extract_code_from_response(self, response: str) -> Optional[str]:
        """从LLM响应中提取代码"""
        # 尝试提取```c或```代码块
        code_blocks = self._extract_code_blocks(response)
        if code_blocks:
            return code_blocks[0]
        
        # 如果没有代码块标记，返回整个响应
        return response.strip()
    
    def _identify_function_boundaries(self, code: str) -> List[Dict]:
        """
        识别代码中的函数边界
        
        Returns:
            List[{"name": str, "start": int, "end": int}]
        """
        functions = []
        
        # 匹配C函数定义模式
        # 支持：int func(), void func(), static int func()等
        pattern = r'^((?:static\s+|inline\s+)?(?:int|void|bool|uint32_t|int32_t|size_t)\s+(\w+)\s*\([^)]*\))\s*\{'
        
        lines = code.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i]
            match = re.match(pattern, line.strip())
            
            if match:
                func_name = match.group(2)
                start_line = i
                
                # 找到函数结束（匹配大括号）
                brace_count = 1
                i += 1
                while i < len(lines) and brace_count > 0:
                    for char in lines[i]:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                    i += 1
                
                functions.append({
                    'name': func_name,
                    'start': start_line,
                    'end': i - 1,
                    'signature': match.group(1)
                })
            else:
                i += 1
        
        return functions
    
    def _select_relevant_functions(
        self,
        functions: List[Dict],
        query: str,
    ) -> List[Dict]:
        """选择与查询相关的函数"""
        query_lower = query.lower()
        relevant = []
        
        for func in functions:
            func_name_lower = func['name'].lower()
            
            # 检查函数名是否匹配查询中的关键词
            if any(kw in func_name_lower for kw in query_lower.split()):
                relevant.append(func)
            # 检查是否是handler相关函数
            elif 'handler' in func_name_lower or 'handle' in func_name_lower:
                relevant.append(func)
            # 检查是否是dispatch相关
            elif 'dispatch' in func_name_lower or 'route' in func_name_lower:
                relevant.append(func)
        
        return relevant
    
    def _assemble_functions(self, code: str, functions: List[Dict]) -> str:
        """组装保留的函数代码"""
        lines = code.split('\n')
        preserved_lines = []
        
        # 保留文件头部的include和宏定义
        for i, line in enumerate(lines):
            if i < 30:  # 假设前30行包含头信息
                preserved_lines.append(line)
        
        preserved_lines.append("\n/* === Relevant Functions === */\n")
        
        # 添加选中的函数
        for func in functions:
            func_lines = lines[func['start']:func['end']+1]
            preserved_lines.extend(func_lines)
            preserved_lines.append("\n")
        
        return '\n'.join(preserved_lines)


# 便捷函数
def compress_context(
    query: str,
    chunks: List[RetrievedChunk],
    task_type: str = "auto",
    llm_client: Optional[BigModelClient] = None,
    relevance_threshold: float = 6.0,
) -> List[RetrievedChunk]:
    """
    便捷函数：压缩上下文
    
    Args:
        query: 查询字符串
        chunks: 原始chunks
        task_type: 任务类型
        llm_client: LLM客户端
        relevance_threshold: 相关性阈值
    
    Returns:
        压缩后的chunk列表（已丢弃的不包含）
    
    Example:
        >>> compressed = compress_context("dllg handler实现", retrieved_chunks, "handler")
        >>> len(compressed) <= len(retrieved_chunks)  # 数量减少或不变
    """
    compressor = ContextCompressor(
        llm_client=llm_client,
        relevance_threshold=relevance_threshold
    )
    result = compressor.compress(query, chunks, task_type)
    return result.compressed_chunks
