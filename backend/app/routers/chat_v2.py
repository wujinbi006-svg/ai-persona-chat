"""
Chat Core 2.0 - 统一聊天路由（v2）

使用 Conversation Orchestrator 内核，提供统一的生成接口。
所有模式（普通/群聊/剧情）和发言策略（指定/@/智能）都走这一个入口。

这是 Phase 1 的集成层。旧的 /api/chat/* 路由保持不变，向后兼容。
前端将在 Phase 2/6 逐步迁移到这个新接口。
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from ..services.orchestrator import (
    get_orchestrator, ChatMode, SpeakerStrategy,
    GenerationConflictError,
)
from ..services.generation_executor import execute_character_generation
from ..services import conversation_service as svc
from ..services import router_service as router_svc
from ..services.auth import get_current_user, check_rate_limit
from ..database import SessionLocal

router = APIRouter(prefix="/api/chat/v2", tags=["chat-v2"])


# ============================================================
# 请求/响应 Schema
# ============================================================

class GenerateRequest(BaseModel):
    """统一生成请求"""
    conversation_id: int
    message: str = ""
    # 模式：normal（普通）/ group（群聊）/ drama（剧情）
    mode: str = "normal"
    # 发言策略：specific（指定）/ mention（@）/ smart（智能）
    strategy: str = "specific"
    # 指定角色 ID（strategy=specific 时使用）
    character_id: Optional[int] = None
    # @角色 ID 列表（strategy=mention 时使用，按顺序）
    mentioned_character_ids: Optional[List[int]] = None
    # 剧情模式配置
    drama_config: Optional[Dict[str, Any]] = None
    # 生成会话 ID（用于停止/暂停/继续，可选）
    generation_id: Optional[str] = None


class ControlRequest(BaseModel):
    """控制请求（停止/暂停/继续）"""
    conversation_id: int
    generation_id: Optional[str] = None


class GenerationStatusResponse(BaseModel):
    """生成状态响应"""
    conversation_id: int
    generation_id: Optional[str] = None
    status: str
    current_character_id: Optional[int] = None
    current_speaker_index: int = 0
    mode: Optional[str] = None
    speakers: List[int] = Field(default_factory=list)


# ============================================================
# 工具函数
# ============================================================

def _parse_mentions_from_message(message: str, characters) -> List[int]:
    """从消息文本中解析 @角色，返回按出现顺序的 character_id 列表。"""
    import re
    mentioned = []
    for char in characters:
        pattern = rf'@{re.escape(char.name)}'
        matches = list(re.finditer(pattern, message))
        for m in matches:
            mentioned.append((m.start(), char.id))
    mentioned.sort(key=lambda x: x[0])
    return [cid for _, cid in mentioned]


def _smart_router(user_message: str, characters) -> List[int]:
    """智能路由：判断谁该说话。包装现有的 router_service。"""
    try:
        result = router_svc.route_speaker(user_message, characters)
        if isinstance(result, list):
            return result
        if isinstance(result, int):
            return [result]
    except Exception:
        pass
    # 回退到第一个角色
    if characters:
        return [characters[0].id]
    return []


# ============================================================
# 统一生成接口
# ============================================================

@router.post("/generate")
async def generate(body: GenerateRequest, current_user: dict = Depends(get_current_user)):
    """
    统一生成接口。

    所有模式（普通/群聊/剧情）和发言策略（指定/@/智能）都走这一个入口。
    返回 SSE 事件流。
    """
    user_id = current_user["id"]

    if not check_rate_limit(user_id):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    # 验证模式和策略
    try:
        mode = ChatMode(body.mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的 mode: {body.mode}")

    try:
        strategy = SpeakerStrategy(body.strategy)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的 strategy: {body.strategy}")

    # 获取会话和角色
    db = SessionLocal()
    try:
        conv = svc.get_conversation(db, body.conversation_id, user_id=user_id)
        if not conv:
            raise HTTPException(status_code=404, detail="会话不存在")

        characters = svc.list_characters(db, body.conversation_id, user_id=user_id)
        if not characters:
            raise HTTPException(status_code=400, detail="请先添加 AI 角色")

        # 如果有用户消息，先保存
        if body.message.strip():
            svc.add_message(db, body.conversation_id, user_id, "user", body.message.strip())

        # 解析 @角色（如果策略是 mention 但没有显式提供 IDs）
        mentioned_ids = body.mentioned_character_ids
        if strategy == SpeakerStrategy.MENTION and not mentioned_ids:
            mentioned_ids = _parse_mentions_from_message(body.message, characters)

        # 构建 character_lookup
        char_lookup = {c.id: c for c in characters}

    finally:
        db.close()

    # 获取全局 Orchestrator
    orch = get_orchestrator()

    # 规划 ResponsePlan
    plan = orch.plan(
        mode=mode,
        strategy=strategy,
        user_message=body.message,
        conversation_id=body.conversation_id,
        user_id=user_id,
        characters=characters,
        specified_character_id=body.character_id,
        mentioned_character_ids=mentioned_ids,
        drama_config=body.drama_config,
        smart_router_fn=_smart_router if strategy == SpeakerStrategy.SMART else None,
    )

    # 如果请求中指定了 generation_id，使用它（用于剧情模式的持续生成）
    if body.generation_id:
        plan.generation_id = body.generation_id

    # 定义角色生成器（闭包捕获 conversation 和 all_characters）
    async def character_generator(session, character):
        async for event in execute_character_generation(
            session, character,
            all_characters=characters,
            conversation=conv,
        ):
            yield event

    # 执行并返回 SSE 流
    async def event_stream():
        try:
            async for event in orch.execute(plan, character_generator, char_lookup):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except GenerationConflictError as e:
            yield f"data: {json.dumps({'type': 'generation_conflict', 'message': str(e)}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'generation_error', 'message': str(e)[:200]}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ============================================================
# 控制接口：停止/暂停/继续
# ============================================================

@router.post("/stop")
async def stop_generation(body: ControlRequest, current_user: dict = Depends(get_current_user)):
    """停止生成。"""
    orch = get_orchestrator()
    session = orch.stop(body.conversation_id, body.generation_id)
    if session:
        return {
            "status": "stopping",
            "generation_id": session.generation_id,
            "message": "正在停止生成...",
        }
    return {"status": "no_active_generation", "message": "当前没有正在进行的生成"}


@router.post("/pause")
async def pause_generation(body: ControlRequest, current_user: dict = Depends(get_current_user)):
    """暂停生成（剧情模式用）。"""
    orch = get_orchestrator()
    session = orch.pause(body.conversation_id)
    if session:
        return {
            "status": "paused",
            "generation_id": session.generation_id,
            "message": "已暂停",
        }
    return {"status": "no_active_generation", "message": "当前没有正在进行的生成"}


@router.post("/resume")
async def resume_generation(body: ControlRequest, current_user: dict = Depends(get_current_user)):
    """继续生成。"""
    orch = get_orchestrator()
    session = orch.resume(body.conversation_id)
    if session:
        return {
            "status": "running",
            "generation_id": session.generation_id,
            "message": "已继续",
        }
    return {"status": "no_active_generation", "message": "当前没有正在进行的生成"}


# ============================================================
# 状态查询接口
# ============================================================

@router.get("/status/{conversation_id}")
async def get_generation_status(conversation_id: int, current_user: dict = Depends(get_current_user)):
    """查询当前会话的生成状态。"""
    orch = get_orchestrator()
    session = orch.get_session(conversation_id)
    if session:
        return GenerationStatusResponse(
            conversation_id=conversation_id,
            generation_id=session.generation_id,
            status=session.status.value,
            current_character_id=session.current_character_id,
            current_speaker_index=session.current_speaker_index,
            mode=session.plan.mode.value,
            speakers=session.plan.speakers,
        )
    return GenerationStatusResponse(
        conversation_id=conversation_id,
        status="idle",
    )
