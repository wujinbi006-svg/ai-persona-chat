"""
流式聊天路由（多角色 + 多用户 + @角色 + 智能发言 + 戏剧模式版）。
支持图片生成：用户明确要求图片时，文字回复后自动生成角色图片。
"""
import json
import re
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..schemas.conversation import (
    ChatRequest, ReplyAllRequest, DiscussionRequest,
    DramaStartRequest, DramaUserMessage,
)
from ..services import conversation_service as svc
from ..services import memory_service as mem_svc
from ..services import router_service as router_svc
from ..services.context_service import build_context
from ..services.llm_client import chat_stream, LLMError
from ..services.stop_flags import set_stop, is_stopped, clear_stop
from ..services.auth import get_current_user, check_rate_limit
from ..services.image_service import detect_image_request, build_image_prompt, build_fallback_image_prompt, generate_image, ImageGenerationError

router = APIRouter(prefix="/api/chat", tags=["chat"])

# 戏剧模式状态：{conversation_id: {"paused": bool, "stopped": bool}}
_drama_state = {}


def _get_latest_user_message(history):
    """从历史消息中获取最近一条用户消息。"""
    for msg in reversed(history):
        if msg.role == "user":
            return msg.content
    return ""


def _parse_mentions(message: str, characters) -> list:
    """
    解析消息中的 @角色 提及。
    返回按出现顺序排列的 character_id 列表。
    同时返回去除 @标记 后的纯文本。
    """
    mentioned_ids = []
    cleaned = message
    for char in characters:
        # 匹配 @角色名（支持中英文名字）
        pattern = rf'@{re.escape(char.name)}'
        matches = list(re.finditer(pattern, message))
        for m in matches:
            mentioned_ids.append((m.start(), char.id))
    # 按出现位置排序
    mentioned_ids.sort(key=lambda x: x[0])
    ordered_ids = [cid for _, cid in mentioned_ids]

    # 去除 @标记
    for char in characters:
        cleaned = re.sub(rf'@{re.escape(char.name)}', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return ordered_ids, cleaned


def _stream_character_response(db, conversation_id, character, all_characters, user_id, conversation=None):
    """生成单个角色的流式回复。如果用户要求图片，文字回复后生成图片。"""
    history = svc.get_messages(db, conversation_id, user_id=user_id)
    latest_user_msg = _get_latest_user_message(history)
    wants_image = detect_image_request(latest_user_msg)

    # 检索相关记忆
    memories = mem_svc.retrieve_relevant_memories(
        db, user_id, conversation_id,
        character_id=character.id,
        query_text=latest_user_msg,
    )
    memory_ids = [m.id for m in memories]

    async def gen():
        messages = build_context(
            character, history, all_characters,
            conversation=conversation,
            memories=memories,
        )
        full_content = ""
        try:
            async for chunk in chat_stream(messages):
                full_content += chunk
                yield f"data: {json.dumps({
                    'type': 'content',
                    'character_id': character.id,
                    'character_name': character.name,
                    'text': chunk,
                }, ensure_ascii=False)}\n\n"

            # 标记记忆已使用
            if memory_ids:
                db_mark = SessionLocal()
                try:
                    mem_svc.mark_memories_used(db_mark, memory_ids)
                finally:
                    db_mark.close()

            if full_content.strip():
                db2 = SessionLocal()
                try:
                    svc.add_message(db2, conversation_id, user_id, "assistant", full_content, character_id=character.id)
                finally:
                    db2.close()

            # ===== 图片生成：用户明确要求时才触发 =====
            if wants_image:
                yield f"data: {json.dumps({
                    'type': 'image_start',
                    'character_id': character.id,
                    'character_name': character.name,
                }, ensure_ascii=False)}\n\n"

                try:
                    db3 = SessionLocal()
                    try:
                        latest_history = svc.get_messages(db3, conversation_id, user_id=user_id)
                    finally:
                        db3.close()

                    image_prompt = build_image_prompt(character, latest_history, latest_user_msg)
                    fallback_prompt = build_fallback_image_prompt(character)
                    image_url = await generate_image(image_prompt, fallback_prompt=fallback_prompt)

                    db4 = SessionLocal()
                    try:
                        img_msg = svc.add_message(
                            db4, conversation_id, user_id, "assistant",
                            content="", character_id=character.id, image_url=image_url,
                        )
                        msg_id = img_msg.id
                    finally:
                        db4.close()

                    yield f"data: {json.dumps({
                        'type': 'image_done',
                        'character_id': character.id,
                        'character_name': character.name,
                        'image_url': image_url,
                        'message_id': msg_id,
                    }, ensure_ascii=False)}\n\n"

                except ImageGenerationError as e:
                    yield f"data: {json.dumps({
                        'type': 'image_error',
                        'character_id': character.id,
                        'character_name': character.name,
                        'message': e.message,
                    }, ensure_ascii=False)}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({
                        'type': 'image_error',
                        'character_id': character.id,
                        'character_name': character.name,
                        'message': f'图片生成失败：{str(e)[:200]}',
                    }, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({
                'type': 'character_done',
                'character_id': character.id,
                'character_name': character.name,
            }, ensure_ascii=False)}\n\n"

            # 批量记忆提取（每N条消息触发一次，异步不阻塞）
            db_extract = SessionLocal()
            try:
                if mem_svc.should_extract(db_extract, conversation_id, user_id):
                    all_msgs = svc.get_messages(db_extract, conversation_id, user_id=user_id)
                    all_chars = svc.list_characters(db_extract, conversation_id, user_id=user_id)
                    await mem_svc.extract_memories_from_batch(
                        db_extract, user_id, conversation_id, all_msgs, all_chars
                    )
            except Exception:
                pass
            finally:
                db_extract.close()

        except LLMError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': e.message}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'生成失败：{str(e)[:200]}'}, ensure_ascii=False)}\n\n"

    return gen()


@router.post("/stream")
async def chat_stream_endpoint(body: ChatRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]

    if not check_rate_limit(user_id):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    db = SessionLocal()
    try:
        conv = svc.get_conversation(db, body.conversation_id, user_id=user_id)
        if not conv:
            return StreamingResponse(
                iter([f"data: {json.dumps({'type': 'error', 'message': '会话不存在'})}\n\n"]),
                media_type="text/event-stream",
            )

        all_characters = svc.list_characters(db, body.conversation_id, user_id=user_id)

        # 解析 @角色
        mentioned_ids, cleaned_message = _parse_mentions(body.message, all_characters)
        actual_message = cleaned_message or body.message

        # 保存用户消息（使用原始消息，保留@标记）
        svc.add_message(db, body.conversation_id, user_id, "user", body.message)

        # 第一条用户消息生成标题
        all_msgs = svc.get_messages(db, body.conversation_id, user_id=user_id)
        user_count = sum(1 for m in all_msgs if m.role == "user")
        if user_count == 1:
            svc.update_conversation(db, body.conversation_id, user_id=user_id, title=svc.generate_title_from_message(actual_message))

        # 确定要回复的角色列表
        reply_characters = []

        # 优先级1：@角色（按出现顺序）
        if mentioned_ids:
            char_map = {c.id: c for c in all_characters}
            reply_characters = [char_map[cid] for cid in mentioned_ids if cid in char_map]

        # 优先级2：智能模式
        elif body.mode == "smart" and all_characters:
            smart_ids = await router_svc.route_speaker(
                db, body.conversation_id, user_id, actual_message, all_characters, all_msgs
            )
            char_map = {c.id: c for c in all_characters}
            reply_characters = [char_map[cid] for cid in smart_ids if cid in char_map]
            if not reply_characters and all_characters:
                reply_characters = [all_characters[0]]

        # 优先级3：手动指定角色
        elif body.character_id:
            character = svc.get_character(db, body.character_id, user_id=user_id)
            if character:
                reply_characters = [character]

        # 不指定角色且无@ → 只保存消息
        if not reply_characters:
            async def just_done():
                yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(just_done(), media_type="text/event-stream")

        async def event_gen():
            for char in reply_characters:
                yield f"data: {json.dumps({
                    'type': 'character_start',
                    'character_id': char.id,
                    'character_name': char.name,
                }, ensure_ascii=False)}\n\n"
                db2 = SessionLocal()
                try:
                    conv2 = svc.get_conversation(db2, body.conversation_id, user_id=user_id)
                    latest_chars = svc.list_characters(db2, body.conversation_id, user_id=user_id)
                    async for line in _stream_character_response(db2, body.conversation_id, char, latest_chars, user_id, conversation=conv2):
                        yield line
                finally:
                    db2.close()
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    finally:
        db.close()


@router.post("/reply-all")
async def reply_all_endpoint(body: ReplyAllRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    if not check_rate_limit(user_id):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    db = SessionLocal()
    try:
        conv = svc.get_conversation(db, body.conversation_id, user_id=user_id)
        if not conv:
            return StreamingResponse(
                iter([f"data: {json.dumps({'type': 'error', 'message': '会话不存在'})}\n\n"]),
                media_type="text/event-stream",
            )

        if body.message:
            svc.add_message(db, body.conversation_id, user_id, "user", body.message)

        all_characters = svc.list_characters(db, body.conversation_id, user_id=user_id)
        if not all_characters:
            async def no_chars():
                yield f"data: {json.dumps({'type': 'error', 'message': '当前会话没有角色'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(no_chars(), media_type="text/event-stream")

        clear_stop(body.conversation_id)

        async def event_gen():
            for char in all_characters:
                if is_stopped(body.conversation_id):
                    break
                yield f"data: {json.dumps({
                    'type': 'character_start', 'character_id': char.id, 'character_name': char.name,
                }, ensure_ascii=False)}\n\n"
                db2 = SessionLocal()
                try:
                    conv2 = svc.get_conversation(db2, body.conversation_id, user_id=user_id)
                    latest_chars = svc.list_characters(db2, body.conversation_id, user_id=user_id)
                    async for line in _stream_character_response(db2, body.conversation_id, char, latest_chars, user_id, conversation=conv2):
                        yield line
                        if is_stopped(body.conversation_id):
                            break
                finally:
                    db2.close()
                if is_stopped(body.conversation_id):
                    break
            clear_stop(body.conversation_id)
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_gen(), media_type="text/event-stream")
    finally:
        db.close()


@router.post("/discussion")
async def discussion_endpoint(body: DiscussionRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    if not check_rate_limit(user_id):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    db = SessionLocal()
    try:
        conv = svc.get_conversation(db, body.conversation_id, user_id=user_id)
        if not conv:
            return StreamingResponse(
                iter([f"data: {json.dumps({'type': 'error', 'message': '会话不存在'})}\n\n"]),
                media_type="text/event-stream",
            )

        if body.message:
            svc.add_message(db, body.conversation_id, user_id, "user", body.message)

        all_characters = svc.list_characters(db, body.conversation_id, user_id=user_id)
        char_map = {c.id: c for c in all_characters}
        selected = [char_map[cid] for cid in body.character_ids if cid in char_map]
        if not selected:
            async def no_sel():
                yield f"data: {json.dumps({'type': 'error', 'message': '未选择有效角色'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(no_sel(), media_type="text/event-stream")

        clear_stop(body.conversation_id)

        async def event_gen():
            for round_num in range(body.rounds):
                if is_stopped(body.conversation_id):
                    break
                for char in selected:
                    if is_stopped(body.conversation_id):
                        break
                    yield f"data: {json.dumps({
                        'type': 'character_start', 'character_id': char.id, 'character_name': char.name, 'round': round_num + 1,
                    }, ensure_ascii=False)}\n\n"
                    db2 = SessionLocal()
                    try:
                        conv2 = svc.get_conversation(db2, body.conversation_id, user_id=user_id)
                        latest_chars = svc.list_characters(db2, body.conversation_id, user_id=user_id)
                        async for line in _stream_character_response(db2, body.conversation_id, char, latest_chars, user_id, conversation=conv2):
                            yield line
                            if is_stopped(body.conversation_id):
                                break
                    finally:
                        db2.close()
                if is_stopped(body.conversation_id):
                    break
            clear_stop(body.conversation_id)
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_gen(), media_type="text/event-stream")
    finally:
        db.close()


# ===== 戏剧模式 =====

@router.post("/drama/stream")
async def drama_stream_endpoint(body: DramaStartRequest, current_user: dict = Depends(get_current_user)):
    """
    戏剧模式 SSE 端点。
    角色A → 等待 → 角色B → 等待 → ...
    支持暂停/继续/停止，支持用户插话。
    """
    user_id = current_user["id"]
    if not check_rate_limit(user_id):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    db = SessionLocal()
    try:
        conv = svc.get_conversation(db, body.conversation_id, user_id=user_id)
        if not conv:
            return StreamingResponse(
                iter([f"data: {json.dumps({'type': 'error', 'message': '会话不存在'})}\n\n"]),
                media_type="text/event-stream",
            )

        # 设置场景
        if body.scene is not None or body.scene_time is not None or body.scene_context is not None:
            svc.update_conversation(
                db, body.conversation_id, user_id=user_id,
                scene=body.scene, scene_time=body.scene_time, scene_context=body.scene_context,
            )
            db.refresh(conv)

        all_characters = svc.list_characters(db, body.conversation_id, user_id=user_id)
        char_map = {c.id: c for c in all_characters}
        selected = [char_map[cid] for cid in body.character_ids if cid in char_map]
        if not selected:
            async def no_sel():
                yield f"data: {json.dumps({'type': 'error', 'message': '未选择有效角色'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(no_sel(), media_type="text/event-stream")

        # 初始化戏剧状态
        _drama_state[body.conversation_id] = {"paused": False, "stopped": False}
        clear_stop(body.conversation_id)

        interval = max(0, min(10, body.interval))
        total_rounds = max(1, min(20, body.rounds))

        async def event_gen():
            yield f"data: {json.dumps({'type': 'drama_start', 'rounds': total_rounds, 'interval': interval}, ensure_ascii=False)}\n\n"

            for round_num in range(total_rounds):
                if _drama_state.get(body.conversation_id, {}).get("stopped"):
                    break
                if is_stopped(body.conversation_id):
                    break

                yield f"data: {json.dumps({'type': 'round_start', 'round': round_num + 1}, ensure_ascii=False)}\n\n"

                for char in selected:
                    # 检查暂停
                    while _drama_state.get(body.conversation_id, {}).get("paused"):
                        if _drama_state.get(body.conversation_id, {}).get("stopped"):
                            break
                        yield f"data: {json.dumps({'type': 'drama_paused'}, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0.5)

                    if _drama_state.get(body.conversation_id, {}).get("stopped"):
                        break
                    if is_stopped(body.conversation_id):
                        break

                    yield f"data: {json.dumps({
                        'type': 'character_start',
                        'character_id': char.id,
                        'character_name': char.name,
                        'round': round_num + 1,
                    }, ensure_ascii=False)}\n\n"

                    db2 = SessionLocal()
                    try:
                        conv2 = svc.get_conversation(db2, body.conversation_id, user_id=user_id)
                        latest_chars = svc.list_characters(db2, body.conversation_id, user_id=user_id)
                        async for line in _stream_character_response(db2, body.conversation_id, char, latest_chars, user_id, conversation=conv2):
                            yield line
                            if _drama_state.get(body.conversation_id, {}).get("stopped"):
                                break
                            if is_stopped(body.conversation_id):
                                break
                    finally:
                        db2.close()

                    # 角色间等待
                    if interval > 0 and char != selected[-1]:
                        await asyncio.sleep(interval)

                yield f"data: {json.dumps({'type': 'round_done', 'round': round_num + 1}, ensure_ascii=False)}\n\n"

            _drama_state.pop(body.conversation_id, None)
            clear_stop(body.conversation_id)
            yield f"data: {json.dumps({'type': 'drama_done'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_gen(), media_type="text/event-stream")
    finally:
        db.close()


@router.post("/drama/pause")
async def drama_pause_endpoint(current_user: dict = Depends(get_current_user)):
    """暂停戏剧模式。"""
    # 从请求体获取 conversation_id
    from fastapi import Request
    # 简化：暂停所有进行中的戏剧
    for cid in _drama_state:
        _drama_state[cid]["paused"] = True
    return {"ok": True, "paused": True}


@router.post("/drama/resume")
async def drama_resume_endpoint(current_user: dict = Depends(get_current_user)):
    """继续戏剧模式。"""
    for cid in _drama_state:
        _drama_state[cid]["paused"] = False
    return {"ok": True, "resumed": True}


@router.post("/drama/stop")
async def drama_stop_endpoint(current_user: dict = Depends(get_current_user)):
    """停止戏剧模式。"""
    for cid in _drama_state:
        _drama_state[cid]["stopped"] = True
        _drama_state[cid]["paused"] = False
    set_stop(0, True)  # 全局停止
    return {"ok": True, "stopped": True}


@router.post("/drama/interject")
async def drama_interject_endpoint(body: DramaUserMessage, current_user: dict = Depends(get_current_user)):
    """
    用户插话：在戏剧进行中插入用户消息。
    消息保存后，戏剧继续时会包含这条新消息。
    """
    user_id = current_user["id"]
    db = SessionLocal()
    try:
        conv = svc.get_conversation(db, body.conversation_id, user_id=user_id)
        if not conv:
            raise HTTPException(status_code=404, detail="会话不存在")
        svc.add_message(db, body.conversation_id, user_id, "user", body.message)
        return {"ok": True, "message": body.message}
    finally:
        db.close()


@router.post("/stop")
async def stop_endpoint(current_user: dict = Depends(get_current_user)):
    from ..services.stop_flags import _stop_flags, _lock
    with _lock:
        for k in _stop_flags:
            _stop_flags[k] = True
    # 同时停止戏剧
    for cid in _drama_state:
        _drama_state[cid]["stopped"] = True
    return {"ok": True}
