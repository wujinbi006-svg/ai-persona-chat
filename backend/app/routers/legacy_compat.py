"""
遗留问题2: 旧接口兼容适配器。

将旧接口（/stream、/reply-all、/discussion、/drama/stream）的请求
转换为 ConversationOrchestrator 的统一执行。

旧接口可以保留，但内部必须调用 Orchestrator，不能再独立运行一套逻辑。
这样旧客户端和新客户端最终都使用同一个聊天内核。
"""
import json
import asyncio
from typing import AsyncGenerator, Dict, Any, Optional, List
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..services import conversation_service as svc
from ..services.orchestrator import (
    ConversationOrchestrator, ResponsePlan, GenerationSession,
    ChatMode, SpeakerStrategy,
)
from ..services.generation_executor import execute_character_generation
from ..services.generation_session_service import (
    create_session, update_session_status, get_active_session,
)


# 全局 Orchestrator 实例
_orchestrator = ConversationOrchestrator()


def _get_orchestrator() -> ConversationOrchestrator:
    """获取全局 Orchestrator 实例。"""
    return _orchestrator


async def run_legacy_through_orchestrator(
    db: Session,
    conversation_id: int,
    user_id: str,
    message: str,
    mode: str = "normal",
    strategy: str = "specific",
    character_ids: Optional[List[int]] = None,
    mentioned_ids: Optional[List[int]] = None,
    drama_config: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[str, None]:
    """
    通用兼容适配器：将旧接口请求通过 Orchestrator 统一执行。

    参数:
        db: 数据库会话
        conversation_id: 会话 ID
        user_id: 用户 ID
        message: 用户消息
        mode: 模式（normal/group/drama）
        strategy: 策略（specific/mention/smart）
        character_ids: 指定角色 ID 列表（specific 模式）
        mentioned_ids: @角色 ID 列表（mention 模式）
        drama_config: 剧情模式配置

    生成:
        SSE 事件字符串（兼容旧接口格式）
    """
    orch = _get_orchestrator()

    # 检查是否已有活跃的生成会话（后端 ConversationLock）
    active = orch.get_session(conversation_id)
    if active and active.is_active:
        yield f"data: {json.dumps({'type': 'error', 'message': '当前正在回复，请稍候'}, ensure_ascii=False)}\n\n"
        return

    # 数据库级检查（Phase 8 唯一索引）
    db_active = get_active_session(db, conversation_id)
    if db_active:
        yield f"data: {json.dumps({'type': 'error', 'message': '当前正在回复，请稍候（数据库级锁）'}, ensure_ascii=False)}\n\n"
        return

    # 保存用户消息
    svc.add_message(db, conversation_id, user_id, "user", message)

    # 第一条用户消息生成标题
    all_msgs = svc.get_messages(db, conversation_id, user_id=user_id)
    user_count = sum(1 for m in all_msgs if m.role == "user")
    if user_count == 1:
        svc.update_conversation(
            db, conversation_id, user_id=user_id,
            title=svc.generate_title_from_message(message),
        )

    # 获取所有角色
    all_characters = svc.list_characters(db, conversation_id, user_id=user_id)

    # 确定要回复的角色列表
    reply_character_ids = []

    if strategy == "mention" and mentioned_ids:
        reply_character_ids = mentioned_ids
    elif strategy == "smart":
        # 智能模式：使用 router 服务
        from ..services.router_service import route_speaker
        smart_ids = await route_speaker(db, conversation_id, user_id, message, all_characters, all_msgs)
        reply_character_ids = smart_ids if smart_ids else [all_characters[0].id] if all_characters else []
    elif character_ids:
        reply_character_ids = character_ids
    elif mode == "group":
        reply_character_ids = [c.id for c in all_characters]

    if not reply_character_ids:
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        return

    # 创建 ResponsePlan
    plan = ResponsePlan(
        conversation_id=conversation_id,
        user_id=user_id,
        mode=ChatMode(mode) if mode in [m.value for m in ChatMode] else ChatMode.NORMAL,
        strategy=SpeakerStrategy(strategy) if strategy in [s.value for s in SpeakerStrategy] else SpeakerStrategy.SPECIFIC,
        speakers=reply_character_ids,
        user_message=message,
    )

    # 创建 GenerationSession（内存）
    session = GenerationSession(
        generation_id=plan.generation_id,
        conversation_id=conversation_id,
        user_id=user_id,
        plan=plan,
    )
    orch.register_session(session)
    session.start()

    # 创建数据库级 GenerationSession（Phase 3 持久化）
    try:
        create_session(
            db, plan.generation_id, conversation_id, user_id,
            mode=mode, strategy=strategy,
            speakers=reply_character_ids,
            user_message=message,
            drama_config=drama_config,
        )
    except Exception:
        # 数据库创建失败不影响内存执行（降级）
        pass

    # 执行生成（复用 Orchestrator 的执行逻辑）
    try:
        async for event in orch.execute_plan(plan, execute_character_generation):
            # 转换为旧接口兼容的 SSE 格式
            event_type = event.get("type", "")

            if event_type == "generation_started":
                yield f"data: {json.dumps({'type': 'start', 'generation_id': plan.generation_id}, ensure_ascii=False)}\n\n"
            elif event_type == "character_started":
                yield f"data: {json.dumps({
                    'type': 'character_start',
                    'character_id': event.get('character_id'),
                    'character_name': event.get('character_name'),
                }, ensure_ascii=False)}\n\n"
            elif event_type == "content":
                yield f"data: {json.dumps({
                    'type': 'content',
                    'character_id': event.get('character_id'),
                    'character_name': event.get('character_name'),
                    'text': event.get('text', ''),
                }, ensure_ascii=False)}\n\n"
            elif event_type == "character_completed":
                yield f"data: {json.dumps({
                    'type': 'character_done',
                    'character_id': event.get('character_id'),
                    'character_name': event.get('character_name'),
                    'message_id': event.get('message_id'),
                }, ensure_ascii=False)}\n\n"
            elif event_type == "image_started":
                yield f"data: {json.dumps({
                    'type': 'image_start',
                    'character_id': event.get('character_id'),
                    'character_name': event.get('character_name'),
                }, ensure_ascii=False)}\n\n"
            elif event_type == "image_completed":
                yield f"data: {json.dumps({
                    'type': 'image_done',
                    'character_id': event.get('character_id'),
                    'character_name': event.get('character_name'),
                    'image_url': event.get('image_url'),
                    'message_id': event.get('message_id'),
                }, ensure_ascii=False)}\n\n"
            elif event_type == "image_failed":
                yield f"data: {json.dumps({
                    'type': 'image_error',
                    'character_id': event.get('character_id'),
                    'character_name': event.get('character_name'),
                    'message': event.get('message', ''),
                }, ensure_ascii=False)}\n\n"
            elif event_type == "generation_error":
                yield f"data: {json.dumps({
                    'type': 'error',
                    'message': event.get('message', '生成失败'),
                }, ensure_ascii=False)}\n\n"
            elif event_type == "generation_completed":
                yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        # 更新数据库状态为 completed
        try:
            update_session_status(db, plan.generation_id, "completed")
        except Exception:
            pass

    except asyncio.CancelledError:
        # 用户取消（Stop）
        session.stop()
        try:
            update_session_status(db, plan.generation_id, "stopped")
        except Exception:
            pass
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        raise
    except Exception as e:
        session.fail(str(e)[:200])
        try:
            update_session_status(db, plan.generation_id, "error", error_message=str(e)[:200])
        except Exception:
            pass
        yield f"data: {json.dumps({'type': 'error', 'message': f'生成失败：{str(e)[:200]}'}, ensure_ascii=False)}\n\n"
    finally:
        # 清理内存会话
        orch.unregister_session(conversation_id)


def parse_mentions(message: str, all_characters: List[Any]) -> tuple:
    """
    解析 @角色。

    返回: (mentioned_ids, cleaned_message)
    """
    mentioned_ids = []
    cleaned_message = message
    for char in all_characters:
        pattern = f"@{char.name}"
        if pattern in message:
            mentioned_ids.append(char.id)
            cleaned_message = cleaned_message.replace(pattern, "").strip()
    return mentioned_ids, cleaned_message
