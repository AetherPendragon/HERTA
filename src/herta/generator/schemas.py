"""
生成器数据结构定义模块

定义配置生成相关的数据结构：
- TargetProtocolSpec: 目标协议规范
- RetrievedChunk: 检索到的知识库片段
- GenerationContext: 生成上下文
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from pathlib import Path
import json


@dataclass
class TargetProtocolSpec:
    """
    目标协议规范

    从目标协议文档解析出的结构化信息
    """

    target_name: str
    document_path: str
    raw_text: str
    summary: str
    sections: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TargetProtocolSpec":
        """从字典创建"""
        return cls(**data)


@dataclass
class RetrievedChunk:
    """
    检索到的知识库片段

    包含从源协议知识库检索到的相关信息
    """

    chunk_id: str
    source: str
    file: str
    kind: str
    section: str
    text: str
    score: float  # 相似度分数
    token_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetrievedChunk":
        """从字典创建"""
        return cls(**data)

    def format_for_prompt(self) -> str:
        """
        格式化为 Prompt 中的引用文本

        Returns:
            格式化的字符串，包含来源和片段内容
        """
        return f"""【来源: {self.source} | 文件: {self.file} | 章节: {self.section} | 相关度: {self.score:.3f}】
{self.text}
---"""


@dataclass
class GenerationContext:
    """
    配置生成上下文

    整合目标协议信息、检索到的参考信息、生成参数等
    """

    target: TargetProtocolSpec
    retrieved_chunks: List[RetrievedChunk]
    source_kb: str
    top_k: int
    model: str
    temperature: float
    output_schema: str = """{
  "protocol_name": "协议名称",
  "protocol_id": "协议ID",
  "version": "版本号",
  "fields": [
    {
      "name": "字段名",
      "type": "字段类型",
      "description": "字段描述",
      "default": "默认值"
    }
  ],
  "commands": {
    "cmd_name": {
      "code": "命令字",
      "description": "命令描述",
      "parameters": []
    }
  },
  "telemetry": {
    "fields": []
  }
}"""

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "target": self.target.to_dict(),
            "retrieved_chunks": [c.to_dict() for c in self.retrieved_chunks],
            "source_kb": self.source_kb,
            "top_k": self.top_k,
            "model": self.model,
            "temperature": self.temperature,
            "output_schema": self.output_schema,
            "metadata": self.metadata,
        }

    def format_retrieved_context(self, max_length: Optional[int] = None) -> str:
        """
        格式化检索到的上下文，用于 Prompt

        Args:
            max_length: 最大字符长度，超出则截断

        Returns:
            格式化的上下文字符串
        """
        if not self.retrieved_chunks:
            return "（未检索到相关参考信息）"

        sections = []
        for i, chunk in enumerate(self.retrieved_chunks, 1):
            sections.append(f"【参考片段 {i}】\n{chunk.format_for_prompt()}")

        context = "\n\n".join(sections)

        if max_length and len(context) > max_length:
            context = context[:max_length] + "\n...（上下文已截断）"

        return context

    def format_target_summary(self) -> str:
        """
        格式化目标协议摘要，用于 Prompt

        Returns:
            格式化的摘要字符串
        """
        sections_info = ""
        if self.target.sections:
            sections_info = "\n文档结构:\n" + "\n".join(
                f"  - {s.get('title', s.get('name', '未命名章节'))}" 
                for s in self.target.sections[:10]  # 最多显示10个章节
            )
            if len(self.target.sections) > 10:
                sections_info += f"\n  ... 等共 {len(self.target.sections)} 个章节"

        return f"""【目标协议】
名称: {self.target.target_name}
文档路径: {self.target.document_path}
摘要: {self.target.summary}{sections_info}
"""


@dataclass
class GenerationResult:
    """
    生成结果

    包含生成的配置内容和元数据
    """

    config: Dict[str, Any]
    raw_response: str
    target: str
    source_kb: str
    retrieved_chunk_count: int
    model: str
    temperature: float
    output_path: Optional[str] = None
    generation_time: Optional[str] = None
    is_valid_json: bool = True
    error_message: Optional[str] = None

    def __post_init__(self):
        """初始化后处理"""
        if self.generation_time is None:
            from datetime import datetime
            self.generation_time = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save_config(self, output_path: Path) -> None:
        """
        保存配置到文件

        Args:
            output_path: 输出文件路径
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

        self.output_path = str(output_path)
        logger.info(f"配置已保存: {output_path}")


from herta.logging import get_logger
logger = get_logger(__name__)
