"""
Herta Web API - FastAPI 应用

提供知识库管理、代码生成、评测对比的 REST API。
"""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from herta.api.routes import kb, generate, compare, settings as settings_route
from herta.api.task_store import tasks
from herta.logging import get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Herta API",
        description="工业协议代码生成系统 - RAG 驱动的协议处理器自动生成",
        version="0.1.0",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(kb.router, prefix="/api/kb", tags=["知识库"])
    app.include_router(generate.router, prefix="/api/generate", tags=["代码生成"])
    app.include_router(compare.router, prefix="/api/compare", tags=["评测对比"])
    app.include_router(settings_route.router, prefix="/api/settings", tags=["设置"])

    # 前端静态文件服务
    frontend_dir = Path(__file__).resolve().parent.parent.parent.parent / "frontend"
    if frontend_dir.exists():
        @app.get("/")
        async def serve_index():
            return FileResponse(str(frontend_dir / "index.html"))

        # JS 和 CSS 通过各自路径提供
        @app.get("/assets/style.css")
        async def serve_css():
            return FileResponse(str(frontend_dir / "css" / "style.css"), media_type="text/css")

        @app.get("/assets/app.js")
        async def serve_js():
            return FileResponse(str(frontend_dir / "js" / "app.js"), media_type="application/javascript")

    return app


app = create_app()
