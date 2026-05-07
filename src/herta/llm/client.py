"""
智谱 AI 客户端封装模块

封装 ZhipuAiClient，提供 BigModelClient 类
支持 chat 和 embeddings 调用
"""

from typing import List, Optional, Dict, Any

from zai import ZhipuAiClient

from herta.config import get_settings, Settings
from herta.logging import get_logger

logger = get_logger(__name__)


class BigModelClient:
    """
    智谱 BigModel API 客户端封装

    自动读取配置，提供 chat 和 embed 方法

    Example:
        >>> client = BigModelClient()
        >>> # 聊天调用
        >>> response = client.chat([{"role": "user", "content": "你好"}])
        >>> # Embedding 调用
        >>> embeddings = client.embed_texts(["hello", "world"])
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        初始化客户端

        Args:
            settings: 配置对象，如果为 None 则自动从环境变量加载

        Raises:
            ValueError: 当 API 密钥未设置时
        """
        self.settings = settings or get_settings()
        self._client = ZhipuAiClient(api_key=self.settings.zai_api_key)
        logger.debug(f"BigModelClient 初始化完成，使用模型: {self.settings.chat_model}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.1,
        stream: bool = False,
    ) -> str:
        """
        调用聊天模型

        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}, ...]
            model: 模型名称，默认使用配置中的 chat_model
            temperature: 采样温度，默认 0.1（更确定性）
            stream: 是否流式输出，当前简化版仅支持 False

        Returns:
            模型生成的纯文本字符串

        Raises:
            ValueError: 当 messages 为空或格式错误时
            RuntimeError: 当 API 调用失败时

        Example:
            >>> client = BigModelClient()
            >>> messages = [{"role": "user", "content": "你好，请介绍自己"}]
            >>> response = client.chat(messages)
            >>> print(response)
        """
        # 输入校验
        if not messages:
            raise ValueError("messages 不能为空列表")

        if not isinstance(messages, list):
            raise ValueError("messages 必须是列表类型")

        for msg in messages:
            if not isinstance(msg, dict):
                raise ValueError("messages 中的每项必须是字典类型")
            if "role" not in msg or "content" not in msg:
                raise ValueError('messages 中的每项必须包含 "role" 和 "content" 字段')

        # 简化版暂不支持流式输出
        if stream:
            logger.warning("stream=True 暂不支持，已自动切换为同步模式")
            stream = False

        model_name = model or self.settings.chat_model

        try:
            logger.debug(f"调用 chat 接口，模型: {model_name}, 消息数: {len(messages)}")

            response = self._client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                stream=False,
            )

            # 提取返回文本
            if hasattr(response, "choices") and len(response.choices) > 0:
                content = response.choices[0].message.content
                logger.debug(f"chat 调用成功，返回长度: {len(content)}")
                return content
            else:
                raise RuntimeError("API 返回格式异常，未找到 choices 字段")

        except Exception as e:
            logger.error(f"chat 调用失败: {e}")
            raise RuntimeError(f"chat API 调用失败: {e}") from e

    def embed_texts(
        self,
        texts: List[str],
        model: Optional[str] = None,
        dimensions: Optional[int] = None,
        batch_size: int = 64,
    ) -> List[List[float]]:
        """
        批量获取文本的 Embedding 向量

        支持自动分批处理，每批不超过 batch_size（默认64，适配智谱API限制）

        Args:
            texts: 文本列表，每项是一个字符串
            model: Embedding 模型名称，默认使用配置中的 embedding_model
            dimensions: 向量维度，默认使用配置中的 embedding_dimensions
            batch_size: 每批处理的文本数量，默认64（智谱API限制）

        Returns:
            Embedding 向量列表，每个向量是一个 float 列表

        Raises:
            ValueError: 当 texts 为空或包含空字符串时
            RuntimeError: 当 API 调用失败时

        Example:
            >>> client = BigModelClient()
            >>> texts = ["hello world", "你好世界"] * 100  # 200条文本
            >>> embeddings = client.embed_texts(texts)  # 自动分批处理
            >>> print(len(embeddings))  # 200
            >>> print(len(embeddings[0]))  # 1024 (默认维度)
        """
        # 输入校验
        if not texts:
            raise ValueError("texts 不能为空列表")

        if not isinstance(texts, list):
            raise ValueError("texts 必须是列表类型")

        # 检查空字符串
        for i, text in enumerate(texts):
            if not isinstance(text, str):
                raise ValueError(f"texts[{i}] 必须是字符串类型")
            if not text.strip():
                raise ValueError(f"texts[{i}] 不能为空或空白字符串")

        model_name = model or self.settings.embedding_model
        dims = dimensions or self.settings.embedding_dimensions

        # 分批处理
        total = len(texts)
        all_embeddings = []

        logger.info(f"开始生成 embeddings: {total} 个文本，批大小: {batch_size}")

        for i in range(0, total, batch_size):
            batch = texts[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total + batch_size - 1) // batch_size

            logger.debug(f"处理第 {batch_num}/{total_batches} 批: {len(batch)} 个文本")

            try:
                response = self._client.embeddings.create(
                    model=model_name,
                    input=batch,
                    dimensions=dims,
                )

                # 提取向量
                if hasattr(response, "data") and len(response.data) > 0:
                    batch_embeddings = [item.embedding for item in response.data]
                    all_embeddings.extend(batch_embeddings)
                    logger.debug(f"第 {batch_num} 批完成: 返回 {len(batch_embeddings)} 个向量")
                else:
                    raise RuntimeError("API 返回格式异常，未找到 data 字段")

            except Exception as e:
                logger.error(f"第 {batch_num} 批 embeddings 调用失败: {e}")
                raise RuntimeError(f"embeddings API 调用失败 (batch {batch_num}): {e}") from e

        logger.info(f"embeddings 生成完成: 共 {len(all_embeddings)} 个向量")
        return all_embeddings

    def embed_query(
        self,
        text: str,
        model: Optional[str] = None,
        dimensions: Optional[int] = None,
    ) -> List[float]:
        """
        获取单个查询文本的 Embedding 向量

        这是 embed_texts 的便捷封装，用于单条查询场景

        Args:
            text: 查询文本字符串
            model: Embedding 模型名称
            dimensions: 向量维度

        Returns:
            Embedding 向量（float 列表）

        Raises:
            ValueError: 当 text 为空字符串时
            RuntimeError: 当 API 调用失败时

        Example:
            >>> client = BigModelClient()
            >>> vector = client.embed_query("查询内容")
            >>> print(len(vector))  # 1024
        """
        if not isinstance(text, str):
            raise ValueError("text 必须是字符串类型")

        if not text.strip():
            raise ValueError("text 不能为空或空白字符串")

        # 复用批量接口
        embeddings = self.embed_texts([text], model=model, dimensions=dimensions)
        return embeddings[0]
