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
from ..services import generation_session_service as gs_svc
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

        # Phase 3: 数据库级生成唯一性检查
        active_session = gs_svc.get_active_session(db, body.conversation_id)
        if active_session:
            raise HTTPException(
                status_code=409,
                detail=f"当前会话正在生成中（generation_id={active_session.generation_id}），请稍候。",
            )

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

    # Phase 3: 创建持久化 GenerationSession
    db_session = SessionLocal()
    try:
        # 先保存用户消息（如果有），并标记 generation_id 和 sequence_number=1
        parent_message_id = None
        if body.message.strip():
            user_msg = svc.add_message(
                db_session, body.conversation_id, user_id, "user", body.message.strip(),
                generation_id=plan.generation_id,
                sequence_number=1,
                message_type="text",
            )
            parent_message_id = user_msg.id

        # 创建生成会话记录
        gs_svc.create_session(
            db_session,
            generation_id=plan.generation_id,
            conversation_id=body.conversation_id,
            user_id=user_id,
            mode=mode.value,
            strategy=strategy.value,
            speakers=plan.speakers,
            user_message=body.message,
            drama_config=body.drama_config,
        )
        gs_svc.update_session_status(db_session, plan.generation_id, "running")
    finally:
        db_session.close()

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
        final_status = "completed"
        final_error = None
        try:
            async for event in orch.execute(plan, character_generator, char_lookup):
                # Phase 3: 同步关键状态到数据库
                if event.get("type") == "character_started":
                    db_upd = SessionLocal()
                    try:
                        gs_svc.update_session_progress(
                            db_upd, plan.generation_id,
                            current_speaker_index=event.get("speaker_index"),
                            current_speaker_id=event.get("character_id"),
                        )
                    finally:
                        db_upd.close()
                elif event.get("type") == "generation_stopped":
                    final_status = "stopped"
                elif event.get("type") == "generation_error":
                    final_status = "error"
                    final_error = event.get("message")
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except GenerationConflictError as e:
            final_status = "error"
            final_error = str(e)
            yield f"data: {json.dumps({'type': 'generation_conflict', 'message': str(e)}, ensure_ascii=False)}\n\n"
        except Exception as e:
            final_status = "error"
            final_error = str(e)[:200]
            yield f"data: {json.dumps({'type': 'generation_error', 'message': str(e)[:200]}, ensure_ascii=False)}\n\n"
        finally:
            # Phase 3: 更新最终状态到数据库
            db_final = SessionLocal()
            try:
                gs_svc.update_session_status(
                    db_final, plan.generation_id, final_status,
                    error_message=final_error,
                )
            finally:
                db_final.close()

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


# ============================================================
# Phase 5: 剧情模式（持续运行状态机）
# ============================================================

class DramaStartRequest(BaseModel):
    """剧情模式开始请求（不再用固定轮数，持续运行直到暂停/停止）。"""
    conversation_id: int
    character_ids: List[int]
    scene: Optional[str] = None
    scene_time: Optional[str] = None
    scene_context: Optional[str] = None
    interval: int = 3  # 角色间等待秒数
    max_duration_seconds: int = 1800  # 最大运行时间 30 分钟（服务器级保护）
    max_generations: int = 100  # 最大连续生成次数（服务器级保护）
    initial_message: Optional[str] = None  # 剧情开场消息


class DramaInterjectRequest(BaseModel):
    """剧情模式用户插话请求。"""
    conversation_id: int
    generation_id: str
    message: str


@router.post("/drama/start")
async def drama_start(body: DramaStartRequest, current_user: dict = Depends(get_current_user)):
    """
    开始剧情模式（持续运行）。

    剧情模式不再使用固定轮数，而是持续运行直到：
    - 用户暂停
    - 用户停止
    - 达到最大运行时间
    - 达到最大生成次数

    返回 SSE 事件流。
    """
    import asyncio as _asyncio
    user_id = current_user["id"]

    if not check_rate_limit(user_id):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    # 获取会话和角色
    db = SessionLocal()
    try:
        conv = svc.get_conversation(db, body.conversation_id, user_id=user_id)
        if not conv:
            raise HTTPException(status_code=404, detail="会话不存在")

        characters = svc.list_characters(db, body.conversation_id, user_id=user_id)
        if not characters:
            raise HTTPException(status_code=400, detail="请先添加 AI 角色")

        # 过滤有效角色
        valid_chars = [c for c in characters if c.id in body.character_ids]
        if not valid_chars:
            raise HTTPException(status_code=400, detail="指定的角色不存在")

        # 按 sort_order 排序
        valid_chars.sort(key=lambda c: (c.sort_order, c.id))

        # 更新场景
        if body.scene or body.scene_time or body.scene_context:
            svc.update_conversation(db, body.conversation_id, {
                "scene": body.scene or "",
                "scene_time": body.scene_time or "",
                "scene_context": body.scene_context or "",
            })

        # 数据库级生成唯一性检查
        active_session = gs_svc.get_active_session(db, body.conversation_id)
        if active_session:
            raise HTTPException(
                status_code=409,
                detail=f"当前会话正在生成中（generation_id={active_session.generation_id}），请稍候。",
            )

        char_lookup = {c.id: c for c in valid_chars}

    finally:
        db.close()

    # 获取全局 Orchestrator
    orch = get_orchestrator()

    # 规划剧情模式 ResponsePlan
    plan = orch.plan(
        mode=ChatMode.DRAMA,
        strategy=SpeakerStrategy.SPECIFIC,
        user_message=body.initial_message or "",
        conversation_id=body.conversation_id,
        user_id=user_id,
        characters=valid_chars,
        specified_character_id=valid_chars[0].id,
        drama_config={
            "character_ids": [c.id for c in valid_chars],
            "interval": body.interval,
            "max_duration_seconds": body.max_duration_seconds,
            "max_generations": body.max_generations,
        },
    )

    # 创建持久化 GenerationSession
    db_session = SessionLocal()
    try:
        # 保存开场消息（如果有）
        if body.initial_message and body.initial_message.strip():
            svc.add_message(
                db_session, body.conversation_id, user_id, "user",
                body.initial_message.strip(),
                generation_id=plan.generation_id,
                sequence_number=1,
            )

        gs_svc.create_session(
            db_session,
            generation_id=plan.generation_id,
            conversation_id=body.conversation_id,
            user_id=user_id,
            mode="drama",
            strategy="specific",
            speakers=[c.id for c in valid_chars],
            user_message=body.initial_message or "",
            drama_config={
                "interval": body.interval,
                "max_duration_seconds": body.max_duration_seconds,
                "max_generations": body.max_generations,
            },
        )
        gs_svc.update_session_status(db_session, plan.generation_id, "running")
    finally:
        db_session.close()

    # 剧情模式持续运行生成器
    async def drama_character_generator(session, character):
        async for event in execute_character_generation(
            session, character,
            all_characters=valid_chars,
            conversation=conv,
        ):
            yield event

    async def drama_event_stream():
        start_time = _asyncio.get_event_loop().time()
        generation_count = 0
        final_status = "completed"
        final_error = None

        try:
            # 剧情开始事件
            yield f"data: {json.dumps({'type': 'drama_started', 'generation_id': plan.generation_id, 'characters': [c.name for c in valid_chars], 'interval': body.interval}, ensure_ascii=False)}\n\n"

            # 持续运行循环
            while True:
                # 检查停止
                if orch.get_session(body.conversation_id) and orch.get_session(body.conversation_id).should_stop:
                    final_status = "stopped"
                    break

                # 检查服务器级保护
                elapsed = _asyncio.get_event_loop().time() - start_time
                if elapsed > body.max_duration_seconds:
                    final_status = "stopped"
                    final_error = "剧情达到最大运行时间，已自动暂停"
                    yield f"data: {json.dumps({'type': 'drama_limit_reached', 'reason': 'max_duration', 'message': final_error}, ensure_ascii=False)}\n\n"
                    break

                if generation_count >= body.max_generations:
                    final_status = "stopped"
                    final_error = "剧情达到最大生成次数，已自动暂停"
                    yield f"data: {json.dumps({'type': 'drama_limit_reached', 'reason': 'max_generations', 'message': final_error}, ensure_ascii=False)}\n\n"
                    break

                # 按顺序执行每个角色
                for char_idx, character in enumerate(valid_chars):
                    # 检查停止
                    current_session = orch.get_session(body.conversation_id)
                    if current_session and current_session.should_stop:
                        final_status = "stopped"
                        break

                    # 等待暂停恢复
                    if current_session and current_session.status.value == "paused":
                        yield f"data: {json.dumps({'type': 'drama_paused', 'generation_id': plan.generation_id}, ensure_ascii=False)}\n\n"
                        # 等待恢复或停止
                        while current_session and current_session.status.value == "paused":
                            await _asyncio.sleep(0.5)
                            current_session = orch.get_session(body.conversation_id)
                            if current_session and current_session.should_stop:
                                final_status = "stopped"
                                break
                        if final_status == "stopped":
                            break
                        yield f"data: {json.dumps({'type': 'drama_resumed', 'generation_id': plan.generation_id}, ensure_ascii=False)}\n\n"

                    generation_count += 1

                    # 执行角色生成（复用 Orchestrator 的执行逻辑）
                    char_session = GenerationSession(
                        generation_id=plan.generation_id,
                        conversation_id=body.conversation_id,
                        user_id=user_id,
                        plan=plan,
                    )
                    char_session.start()
                    char_session.current_speaker_index = char_idx
                    char_session.current_character_id = character.id

                    async for event in drama_character_generator(char_session, character):
                        event["generation_id"] = plan.generation_id
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                    # 角色间等待
                    if body.interval > 0 and char_idx < len(valid_chars) - 1:
                        await _asyncio.sleep(body.interval)

                if final_status == "stopped":
                    break

                # 一轮结束后短暂等待
                await _asyncio.sleep(0.5)

        except Exception as e:
            final_status = "error"
            final_error = str(e)[:200]
            yield f"data: {json.dumps({'type': 'generation_error', 'message': final_error}, ensure_ascii=False)}\n\n"
        finally:
            # 更新最终状态
            db_final = SessionLocal()
            try:
                gs_svc.update_session_status(
                    db_final, plan.generation_id, final_status,
                    error_message=final_error,
                )
            finally:
                db_final.close()

            yield f"data: {json.dumps({'type': 'drama_ended', 'generation_id': plan.generation_id, 'status': final_status, 'generations': generation_count}, ensure_ascii=False)}\n\n"

    return StreamingResponse(drama_event_stream(), media_type="text/event-stream")


@router.post("/drama/interject")
async def drama_interject(body: DramaInterjectRequest, current_user: dict = Depends(get_current_user)):
    """
    剧情模式用户插话。

    暂停当前剧情，保存用户消息，然后继续剧情。
    """
    user_id = current_user["id"]

    db = SessionLocal()
    try:
        # 保存用户消息
        svc.add_message(
            db, body.conversation_id, user_id, "user", body.message.strip(),
            generation_id=body.generation_id,
        )

        # 更新 generation session 进度
        gs_svc.update_session_status(db, body.generation_id, "running")
    finally:
        db.close()

    return {
        "status": "interjected",
        "generation_id": body.generation_id,
        "message": "用户消息已插入，剧情继续",
    }
