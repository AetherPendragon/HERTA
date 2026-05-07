"""
目标协议文档解析模块

解析目标协议文档，提取结构化信息
支持格式：docx, pdf（doc 需要转换）
"""

from pathlib import Path
from typing import Optional, List, Dict, Any

from herta.generator.schemas import TargetProtocolSpec
from herta.parser.doc_parser import DocParser, parse_document
from herta.utils.text import normalize_text, strip_extra_blank_lines
from herta.logging import get_logger

logger = get_logger(__name__)


class TargetParser:
    """
    目标协议文档解析器

    将目标协议文档解析为结构化的 TargetProtocolSpec
    """

    SUPPORTED_EXTS = ['.docx', '.pdf']

    def __init__(self):
        self.doc_parser = DocParser()

    def parse(self, file_path: Path, target_name: Optional[str] = None) -> TargetProtocolSpec:
        """
        解析目标协议文档

        Args:
            file_path: 文档路径
            target_name: 目标协议名称，默认从文件名推断

        Returns:
            TargetProtocolSpec 结构化规范对象

        Raises:
            ValueError: 不支持的文件格式
            FileNotFoundError: 文件不存在
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 确定目标名称
        if target_name is None:
            target_name = file_path.stem

        ext = file_path.suffix.lower()

        # 检查格式支持
        if ext == '.doc':
            raise ValueError(
                f"不支持 .doc 格式: {file_path}\n"
                f"请将文档转换为 .docx 或 .pdf 格式后再解析。\n"
                f"转换方式：使用 Microsoft Word 或 LibreOffice 另存为 docx/pdf"
            )

        if ext not in self.SUPPORTED_EXTS:
            raise ValueError(
                f"不支持的文件格式: {ext}\n"
                f"支持格式: {', '.join(self.SUPPORTED_EXTS)}"
            )

        logger.info(f"解析目标协议文档: {file_path}")

        # 使用 doc_parser 解析文档
        try:
            source_docs = parse_document(str(file_path), target_name)
        except Exception as e:
            logger.error(f"解析文档失败: {file_path}, 错误: {e}")
            raise

        # 合并所有文本
        full_text = "\n\n".join(doc.text for doc in source_docs)
        full_text = strip_extra_blank_lines(full_text)

        # 提取章节结构
        sections = self._extract_sections(source_docs)

        # 生成摘要（简化版：提取前500字符作为摘要）
        summary = self._generate_summary(full_text)

        spec = TargetProtocolSpec(
            target_name=target_name,
            document_path=str(file_path),
            raw_text=full_text,
            summary=summary,
            sections=sections,
            metadata={
                "file_size": file_path.stat().st_size,
                "doc_count": len(source_docs),
                "text_length": len(full_text),
            }
        )

        logger.info(f"目标协议解析完成: {target_name}, 文本长度: {len(full_text)}, 章节数: {len(sections)}")
        return spec

    def _extract_sections(self, source_docs: List[Any]) -> List[Dict[str, Any]]:
        """
        从解析的文档中提取章节结构

        Args:
            source_docs: SourceDocument 列表

        Returns:
            章节列表
        """
        sections = []

        for doc in source_docs:
            section = {
                "name": doc.section,
                "kind": doc.kind,
                "file": doc.file,
                "preview": doc.text[:200] + "..." if len(doc.text) > 200 else doc.text,
            }
            sections.append(section)

        return sections

    def _generate_summary(self, text: str, max_length: int = 500) -> str:
        """
        生成文本摘要（简化版）

        当前实现：提取前 max_length 个字符，尝试在句子边界截断

        Args:
            text: 完整文本
            max_length: 摘要最大长度

        Returns:
            摘要文本
        """
        if len(text) <= max_length:
            return text.strip()

        # 尝试在句子边界截断
        truncated = text[:max_length]

        # 寻找最后一个句子结束符
        sentence_ends = ['。', '！', '？', '. ', '! ', '? ', '\n']
        last_end = -1

        for end_char in sentence_ends:
            pos = truncated.rfind(end_char)
            if pos > last_end:
                last_end = pos

        if last_end > 0:
            truncated = truncated[:last_end + 1]

        summary = truncated.strip()

        # 添加省略号
        if len(text) > len(truncated):
            summary += " ...（内容已截断）"

        return summary

    def can_parse(self, file_path: Path) -> bool:
        """
        检查是否可以解析该文件

        Args:
            file_path: 文件路径

        Returns:
            是否支持解析
        """
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTS


def parse_target_protocol(file_path: str, target_name: Optional[str] = None) -> TargetProtocolSpec:
    """
    便捷函数：解析目标协议文档

    Args:
        file_path: 文档路径
        target_name: 目标协议名称

    Returns:
        TargetProtocolSpec 结构化规范对象

    Example:
        >>> spec = parse_target_protocol("data/target_proto/dllg/dllg.docx", "dllg")
        >>> print(spec.summary)
    """
    parser = TargetParser()
    return parser.parse(Path(file_path), target_name)
