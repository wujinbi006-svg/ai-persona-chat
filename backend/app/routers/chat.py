"""
流式聊天路由（多角色 + 多用户版）。
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..schemas.conversation import ChatRequest, ReplyAllRequest, DiscussionRequest
from ..services import conversation_service as svc
from ..services.context_service import build_context
from ..services.llm_client import chat_stream, LLMError
from ..services.stop_flags import set_stop, is_stopped, clear_stop
from ..services.auth import get_current_user, check_rate_limit

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _stream_character_response(db, conversation_id, character, all_characters, user_id):
    """生成单个角色的流式回复。"""
    history = svc.get_messages(db, conversation_id, user_id=user_id)

    async def gen():
        messages = build_context(character, history, all_characters)
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
            if full_content.strip():
                db2 = SessionLocal()
                try:
                    svc.add_message(db2, conversation_id, user_id, "assistant", full_content, character_id=character.id)
                finally:
                    db2.close()
            yield f"data: {json.dumps({
                'type': 'character_done',
                'character_id': character.id,
                'character_name': character.name,
            }, ensure_ascii=False)}\n\n"
        except LLMError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': e.message}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'生成失败：{str(e)[:200]}'}, ensure_ascii=False)}\n\n"

    return gen()


@router.post("/stream")
async def chat_stream_endpoint(body: ChatRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]

    # 限流
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

        # 保存用户消息
        svc.add_message(db, body.conversation_id, user_id, "user", body.message)

        # 第一条用户消息生成标题
        all_msgs = svc.get_messages(db, body.conversation_id, user_id=user_id)
        user_count = sum(1 for m in all_msgs if m.role == "user")
        if user_count == 1:
            svc.update_conversation(db, body.conversation_id, user_id=user_id, title=svc.generate_title_from_message(body.message))

        # 不指定角色 → 只保存消息
        if not body.character_id:
            async def just_done():
                yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(just_done(), media_type="text/event-stream")

        # 指定角色 → 流式生成
        character = svc.get_character(db, body.character_id, user_id=user_id)
        if not character:
            async def char_error():
                yield f"data: {json.dumps({'type': 'error', 'message': '角色不存在'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(char_error(), media_type="text/event-stream")

        all_characters = svc.list_characters(db, body.conversation_id, user_id=user_id)

        async def event_gen():
            yield f"data: {json.dumps({
                'type': 'character_start',
                'character_id': character.id,
                'character_name': character.name,
            }, ensure_ascii=False)}\n\n"
            async for line in _stream_character_response(db, body.conversation_id, character, all_characters, user_id):
                yield line
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
                    latest_chars = svc.list_characters(db2, body.conversation_id, user_id=user_id)
                    async for line in _stream_character_response(db2, body.conversation_id, char, latest_chars, user_id):
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
                        latest_chars = svc.list_characters(db2, body.conversation_id, user_id=user_id)
                        async for line in _stream_character_response(db2, body.conversation_id, char, latest_chars, user_id):
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


@router.post("/stop")
async def stop_endpoint(current_user: dict = Depends(get_current_user)):
    from ..services.stop_flags import _stop_flags, _lock
    with _lock:
        for k in _stop_flags:
            _stop_flags[k] = True
    return {"ok": True}
