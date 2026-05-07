"""
配置系统模块

支持从环境变量读取配置，提供 Settings dataclass 和 get_settings() 单例接口
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from herta.constants import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_DATA_DIR,
    DEFAULT_OUTPUT_DIR,
)


@dataclass
class Settings:
    """
    应用配置类

    属性:
        zai_api_key: 智谱 AI API 密钥（必填，从环境变量 ZAI_API_KEY 读取）
        chat_model: 聊天模型名称
        embedding_model: Embedding 模型名称
        embedding_dimensions: Embedding 向量维度
        data_dir: 数据目录路径
        output_dir: 输出目录路径
    """

    # 智谱 AI 配置
    zai_api_key: str = field(default="")
    chat_model: str = field(default=DEFAULT_CHAT_MODEL)
    embedding_model: str = field(default=DEFAULT_EMBEDDING_MODEL)
    embedding_dimensions: int = field(default=DEFAULT_EMBEDDING_DIMENSIONS)

    # 目录配置
    data_dir: str = field(default=DEFAULT_DATA_DIR)
    output_dir: str = field(default=DEFAULT_OUTPUT_DIR)

    def __post_init__(self):
        """初始化后校验必填项"""
        if not self.zai_api_key:
            raise ValueError(
                "ZAI_API_KEY 环境变量未设置，请先设置环境变量:\n"
                "  export ZAI_API_KEY='your-api-key'"
            )


# 全局配置缓存
_settings_instance: Optional[Settings] = None


def _get_env_or_default(env_name: str, default_value: str) -> str:
    """从环境变量获取值，如果不存在则返回默认值"""
    return os.environ.get(env_name, default_value)


def _get_env_int_or_default(env_name: str, default_value: int) -> int:
    """从环境变量获取整数值，如果不存在或解析失败则返回默认值"""
    env_value = os.environ.get(env_name)
    if env_value is None:
        return default_value
    try:
        return int(env_value)
    except ValueError:
        return default_value


def load_settings_from_env() -> Settings:
    """
    从环境变量加载配置

    支持的环境变量:
        - ZAI_API_KEY: 智谱 AI API 密钥（必填）
        - HERTA_CHAT_MODEL: 聊天模型名称
        - HERTA_EMBEDDING_MODEL: Embedding 模型名称
        - HERTA_EMBEDDING_DIMENSIONS: Embedding 向量维度
        - HERTA_DATA_DIR: 数据目录路径
        - HERTA_OUTPUT_DIR: 输出目录路径

    Returns:
        Settings 配置对象

    Raises:
        ValueError: 当必填项 ZAI_API_KEY 未设置时
    """
    return Settings(
        zai_api_key=_get_env_or_default("ZAI_API_KEY", ""),
        chat_model=_get_env_or_default("HERTA_CHAT_MODEL", DEFAULT_CHAT_MODEL),
        embedding_model=_get_env_or_default(
            "HERTA_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL
        ),
        embedding_dimensions=_get_env_int_or_default(
            "HERTA_EMBEDDING_DIMENSIONS", DEFAULT_EMBEDDING_DIMENSIONS
        ),
        data_dir=_get_env_or_default("HERTA_DATA_DIR", DEFAULT_DATA_DIR),
        output_dir=_get_env_or_default("HERTA_OUTPUT_DIR", DEFAULT_OUTPUT_DIR),
    )


def get_settings() -> Settings:
    """
    获取配置单例

    首次调用时会从环境变量加载配置，后续调用返回缓存实例

    Returns:
        Settings 配置对象

    Example:
        >>> from herta.config import get_settings
        >>> settings = get_settings()
        >>> print(settings.chat_model)
    """
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = load_settings_from_env()
    return _settings_instance


def reload_settings() -> Settings:
    """
    重新加载配置（用于配置变更后刷新）

    Returns:
        新的 Settings 配置对象
    """
    global _settings_instance
    _settings_instance = load_settings_from_env()
    return _settings_instance
