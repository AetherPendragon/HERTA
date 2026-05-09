"""
代码生成路由
"""

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from herta.api.task_store import tasks
from herta.utils.paths import project_relative
from herta.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


class GenerateConfigRequest(BaseModel):
    target: str
    source_kb: str = ""
    top_k: int = 5


class GenerateHandlerRequest(BaseModel):
    target: str
    source_kb: str = ""
    top_k: int = 8


@router.get("/targets")
async def list_targets():
    """列出可用的目标协议"""
    target_dir = project_relative("data/target_proto")
    if not target_dir.exists():
        return {"targets": []}

    result = []
    for d in sorted(target_dir.iterdir()):
        if d.is_dir():
            has_docx = any(d.glob("*.docx"))
            has_gt_config = (d / f"{d.name}_config.json").exists()
            has_gt_handler = (d / f"{d.name}_handler.c").exists()
            result.append({
                "name": d.name,
                "has_docx": has_docx,
                "has_gt_config": has_gt_config,
                "has_gt_handler": has_gt_handler,
            })

    return {"targets": result}


@router.post("/config")
async def generate_config(req: GenerateConfigRequest):
    """生成 config.json（后台任务）"""
    import uuid
    task_id = str(uuid.uuid4())[:8]

    tasks[task_id] = {
        "type": "generate_config",
        "status": "pending",
        "progress": 0,
        "message": "准备生成配置...",
        "target": req.target,
        "created_at": asyncio.get_event_loop().time(),
        "result": None,
        "error": None,
    }

    asyncio.get_event_loop().run_in_executor(
        None, _run_generate_config, task_id, req
    )

    return {"task_id": task_id, "status": "pending"}


@router.post("/handler")
async def generate_handler(req: GenerateHandlerRequest):
    """生成 handler.c（后台任务）"""
    import uuid
    task_id = str(uuid.uuid4())[:8]

    tasks[task_id] = {
        "type": "generate_handler",
        "status": "pending",
        "progress": 0,
        "message": "准备生成 Handler 代码...",
        "target": req.target,
        "created_at": asyncio.get_event_loop().time(),
        "result": None,
        "error": None,
    }

    asyncio.get_event_loop().run_in_executor(
        None, _run_generate_handler, task_id, req
    )

    return {"task_id": task_id, "status": "pending"}


def _run_generate_config(task_id: str, req: GenerateConfigRequest):
    """线程池中执行配置生成"""
    try:
        tasks[task_id]["status"] = "running"
        tasks[task_id]["message"] = "正在检索知识库..."
        tasks[task_id]["progress"] = 20

        from herta.generator.config_generator import ConfigGenerator

        kb_dir = project_relative(f"data/kb/{req.source_kb}") if req.source_kb else None
        target_doc = project_relative(f"data/target_proto/{req.target}/{req.target}.docx")

        output_dir = project_relative(f"output/generated/{req.target}")
        output_dir.mkdir(parents=True, exist_ok=True)

        generator = ConfigGenerator()

        tasks[task_id]["message"] = "正在调用 LLM 生成配置..."
        tasks[task_id]["progress"] = 50

        result = generator.generate(
            target_doc_path=target_doc,
            source_kb_dir=kb_dir,
            target_name=req.target,
            top_k=req.top_k,
            output_dir=output_dir,
        )

        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["message"] = "配置生成完成"
        tasks[task_id]["result"] = {
            "config_path": result.output_path,
            "retrieval_count": result.retrieved_chunk_count,
            "model": result.model,
        }

    except Exception as e:
        logger.error(f"配置生成失败: {e}")
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)
        tasks[task_id]["message"] = f"生成失败: {e}"


def _run_generate_handler(task_id: str, req: GenerateHandlerRequest):
    """线程池中执行 Handler 生成"""
    try:
        tasks[task_id]["status"] = "running"
        tasks[task_id]["message"] = "正在检索知识库..."
        tasks[task_id]["progress"] = 10

        from herta.generator.handler_generator import HandlerGenerator

        kb_dir = project_relative(f"data/kb/{req.source_kb}") if req.source_kb else None
        target_doc = project_relative(f"data/target_proto/{req.target}/{req.target}.docx")

        output_dir = project_relative(f"output/generated/{req.target}")
        output_dir.mkdir(parents=True, exist_ok=True)

        generator = HandlerGenerator()

        tasks[task_id]["message"] = "阶段A: 生成设计草图..."
        tasks[task_id]["progress"] = 30

        result = generator.generate(
            target_doc_path=target_doc,
            source_kb_dir=kb_dir,
            target_name=req.target,
            top_k=req.top_k,
            output_dir=output_dir,
        )

        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["message"] = "Handler 代码生成完成"
        tasks[task_id]["result"] = {
            "handler_path": result.code_output_path,
            "plan_path": result.plan_output_path,
            "retrieval_count": result.retrieved_chunk_count,
            "model": result.model,
        }

    except Exception as e:
        logger.error(f"Handler 生成失败: {e}")
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)
        tasks[task_id]["message"] = f"生成失败: {e}"


@router.get("/result/{target}")
async def get_generated_result(target: str):
    """获取已生成的结果"""
    gen_dir = project_relative(f"output/generated/{target}")
    if not gen_dir.exists():
        return {"exists": False}

    result = {"exists": True, "target": target}

    config_file = gen_dir / f"{target}_config.json"
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            result["config"] = json.load(f)

    handler_file = gen_dir / f"{target}_handler.c"
    if handler_file.exists():
        with open(handler_file, "r", encoding="utf-8") as f:
            result["handler_source"] = f.read()
            result["handler_lines"] = result["handler_source"].count("\n") + 1

    return result
