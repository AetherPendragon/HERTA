"""
设置路由
"""

import os
from fastapi import APIRouter
from pydantic import BaseModel

from herta.api.task_store import tasks
from herta.config import get_settings
from herta.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


class UpdateSettingsRequest(BaseModel):
    api_key: str = ""
    chat_model: str = ""
    embedding_model: str = ""


@router.get("")
async def get_settings_api():
    """获取当前设置"""
    try:
        settings = get_settings()
        return {
            "api_key_set": bool(settings.zai_api_key),
            "api_key_preview": (settings.zai_api_key[:8] + "...") if settings.zai_api_key else "",
            "chat_model": settings.chat_model,
            "embedding_model": settings.embedding_model,
            "embedding_dimensions": settings.embedding_dimensions,
        }
    except Exception:
        return {
            "api_key_set": bool(os.environ.get("ZAI_API_KEY")),
            "api_key_preview": "",
            "chat_model": "glm-5.1",
            "embedding_model": "embedding-3",
            "embedding_dimensions": 1024,
        }


@router.post("")
async def update_settings(req: UpdateSettingsRequest):
    """更新设置"""
    if req.api_key:
        os.environ["ZAI_API_KEY"] = req.api_key
    if req.chat_model:
        os.environ["HERTA_CHAT_MODEL"] = req.chat_model
    if req.embedding_model:
        os.environ["HERTA_EMBEDDING_MODEL"] = req.embedding_model

    return {"status": "ok"}


@router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """获取后台任务状态"""
    if task_id not in tasks:
        return {"exists": False}

    task = tasks[task_id]
    return {
        "exists": True,
        "type": task["type"],
        "status": task["status"],
        "progress": task["progress"],
        "message": task["message"],
        "result": task["result"],
        "error": task["error"],
    }
