"""
BM25稀疏索引模块

基于词频统计的关键词检索，对精确匹配敏感
适合匹配：函数名、命令字、字段名等标识符
"""

import re
import pickle
import json
import numpy as np
from typing import List, Tuple, Optional, Callable, Dict, Any
from pathlib import Path
from dataclasses import dataclass

try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False

try:
    import jieba
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False

from herta.kb.schemas import Chunk
from herta.logging import get_logger

logger = get_logger(__name__)


@dataclass
class BM25SearchResult:
    """BM25搜索结果"""
    chunk_id: str
    score: float
    rank: int


class BM25Index:
    """
    BM25稀疏索引
    
    基于词频统计的关键词检索
    """
    
    def __init__(
        self,
        tokenizer: Optional[Callable[[str], List[str]]] = None,
        k1: float = 1.5,          # BM25参数：词频饱和度
        b: float = 0.75,          # BM25参数：文档长度归一化
    ):
        """
        初始化BM25索引
        
        Args:
            tokenizer: 分词器函数，默认使用jieba+标识符提取
            k1: BM25参数，控制词频饱和度（通常1.2-2.0）
            b: BM25参数，控制文档长度归一化（通常0.75）
        """
        if not BM25_AVAILABLE:
            raise ImportError(
                "rank_bm25未安装，请执行: pip install rank-bm25"
            )
        
        self.tokenizer = tokenizer or self._default_tokenizer
        self.k1 = k1
        self.b = b
        
        self.corpus: List[str] = []           # 原始文档列表
        self.tokenized_corpus: List[List[str]] = []  # 分词后的文档
        self.chunk_ids: List[str] = []        # chunk_id映射
        self.bm25: Optional[BM25Okapi] = None # BM25索引实例
        
        logger.debug(f"BM25Index初始化: k1={k1}, b={b}")
    
    def _default_tokenizer(self, text: str) -> List[str]:
        """
        默认分词器
        
        策略：
        1. 使用jieba进行中文分词
        2. 保留英文单词和代码标识符
        3. 提取代码标识符（驼峰、下划线命名）
        4. 识别命令字（如CMD_XXX, 0x01）
        """
        tokens = []
        
        # 1. 中文分词
        if JIEBA_AVAILABLE:
            chinese_tokens = jieba.lcut(text)
            tokens.extend([t.lower() for t in chinese_tokens if len(t) > 1])
        
        # 2. 提取英文标识符（函数名、变量名等）
        # 匹配：驼峰命名、下划线命名
        identifier_pattern = r'\b[a-zA-Z_][a-zA-Z0-9_]*\b'
        identifiers = re.findall(identifier_pattern, text)
        
        # 为重要的标识符（大写或包含handler等关键词）增加权重
        important_keywords = ['handler', 'cmd', 'dispatch', 'parse', 'init', 'process', 'config']
        for ident in identifiers:
            tokens.append(ident.lower())
            # 如果是重要标识符，重复添加以提升权重
            if any(kw in ident.lower() for kw in important_keywords):
                tokens.append(ident.lower())  # 双倍权重
        
        # 3. 提取命令字/指令（如 CMD_XXX, 0x01等）
        cmd_pattern = r'\b(CMD_[A-Z_]+|0x[0-9A-Fa-f]{2,})\b'
        commands = re.findall(cmd_pattern, text)
        for cmd in commands:
            tokens.append(cmd.lower())
            tokens.append(cmd.lower())  # 双倍权重
        
        # 4. 提取结构体名（以_t结尾或全大写）
        struct_pattern = r'\b([A-Z][a-zA-Z0-9_]*_t|[A-Z_]{3,})\b'
        structs = re.findall(struct_pattern, text)
        for struct in structs:
            tokens.append(struct.lower())
        
        return tokens
    
    def build(
        self,
        chunks: List[Chunk],
    ) -> None:
        """
        构建BM25索引
        
        Args:
            chunks: Chunk列表
        """
        logger.info(f"开始构建BM25索引: {len(chunks)} chunks")
        
        self.corpus = []
        self.tokenized_corpus = []
        self.chunk_ids = []
        
        for chunk in chunks:
            text = chunk.text
            
            # 根据chunk类型增强文本
            if chunk.kind == "code":
                text = self._enhance_code_text(text, chunk.metadata)
            
            self.corpus.append(text)
            self.tokenized_corpus.append(self.tokenizer(text))
            self.chunk_ids.append(chunk.chunk_id)
        
        # 构建BM25索引
        self.bm25 = BM25Okapi(
            self.tokenized_corpus,
            k1=self.k1,
            b=self.b
        )
        
        logger.info(f"BM25索引构建完成: {len(self.corpus)} 文档")
    
    def _enhance_code_text(
        self,
        text: str,
        metadata: Dict[str, Any],
    ) -> str:
        """
        增强代码文本，提高BM25检索效果
        
        策略：
        1. 提取函数名并重复（提升权重）
        2. 添加结构体名
        3. 添加宏定义名
        """
        enhanced_parts = []
        
        # 如果metadata中有函数名信息，重复添加以提升权重
        if "functions" in metadata and isinstance(metadata["functions"], list):
            func_names = " ".join([f.get("name", "") for f in metadata["functions"] if f.get("name")])
            if func_names:
                enhanced_parts.append(func_names * 3)  # 3倍权重
        
        # 添加chunk中识别的函数名（通过正则）
        func_pattern = r'(?:static\s+|int\s+|void\s+)?(\w+)\s*\([^)]*\)\s*\{'
        funcs_in_code = re.findall(func_pattern, text)
        if funcs_in_code:
            enhanced_parts.append(" ".join(funcs_in_code) * 2)
        
        # 原始文本
        enhanced_parts.append(text)
        
        return " ".join(enhanced_parts)
    
    def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[BM25SearchResult]:
        """
        BM25检索
        
        Args:
            query: 查询字符串
            top_k: 返回结果数量
        
        Returns:
            BM25搜索结果列表，按分数降序
        """
        if self.bm25 is None:
            raise RuntimeError("BM25索引未构建")
        
        # 分词
        tokenized_query = self.tokenizer(query)
        
        if not tokenized_query:
            logger.warning("查询分词结果为空")
            return []
        
        # 获取分数
        scores = self.bm25.get_scores(tokenized_query)
        
        # 获取top_k索引
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        results = []
        rank = 1
        for idx in top_indices:
            if scores[idx] > 0:  # 只返回有分数的
                results.append(BM25SearchResult(
                    chunk_id=self.chunk_ids[idx],
                    score=float(scores[idx]),
                    rank=rank
                ))
                rank += 1
        
        logger.debug(f"BM25检索完成: {len(results)} 结果")
        return results
    
    def batch_search(
        self,
        queries: List[str],
        top_k: int = 10,
    ) -> List[List[BM25SearchResult]]:
        """
        批量BM25检索
        
        Args:
            queries: 查询字符串列表
            top_k: 每个查询返回结果数
        
        Returns:
            每个查询的结果列表
        """
        return [self.search(q, top_k) for q in queries]
    
    def save(self, output_dir: Path) -> None:
        """
        保存BM25索引到磁盘
        
        Args:
            output_dir: 输出目录
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 使用pickle保存BM25对象
        bm25_path = output_dir / "bm25_index.pkl"
        with open(bm25_path, 'wb') as f:
            pickle.dump({
                'bm25': self.bm25,
                'corpus': self.corpus,
                'chunk_ids': self.chunk_ids,
                'k1': self.k1,
                'b': self.b,
            }, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        # 保存元数据（JSON格式便于查看）
        meta_path = output_dir / "bm25_meta.json"
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump({
                'chunk_count': len(self.chunk_ids),
                'k1': self.k1,
                'b': self.b,
                'chunk_ids': self.chunk_ids,
            }, f, indent=2, ensure_ascii=False)
        
        logger.info(f"BM25索引已保存: {bm25_path}")
    
    def load(self, input_dir: Path) -> None:
        """
        从磁盘加载BM25索引
        
        Args:
            input_dir: 索引所在目录
        """
        input_dir = Path(input_dir)
        
        bm25_path = input_dir / "bm25_index.pkl"
        if not bm25_path.exists():
            raise FileNotFoundError(f"BM25索引文件不存在: {bm25_path}")
        
        with open(bm25_path, 'rb') as f:
            data = pickle.load(f)
            self.bm25 = data['bm25']
            self.corpus = data['corpus']
            self.chunk_ids = data['chunk_ids']
            self.k1 = data.get('k1', 1.5)
            self.b = data.get('b', 0.75)
        
        # 重新构建tokenized_corpus（tokenizer可能不同）
        self.tokenized_corpus = [self.tokenizer(text) for text in self.corpus]
        
        logger.info(f"BM25索引已加载: {len(self.chunk_ids)} chunks")
    
    @property
    def is_built(self) -> bool:
        """检查索引是否已构建"""
        return self.bm25 is not None
    
    @property
    def doc_count(self) -> int:
        """返回文档数量"""
        return len(self.chunk_ids)
