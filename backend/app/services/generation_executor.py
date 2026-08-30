"""
Chat Core 2.0 - Generation Executor（生成执行器）

把现有的角色回复生成逻辑包装成 Orchestrator 需要的 character_generator 格式。
这是旧代码和新内核之间的适配器层。
"""
import json
from typing import AsyncGenerator, Dict, Any
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..services import conversation_service as svc
from ..services import memory_service as mem_svc
from ..services.context_service import build_context
from ..services.llm_client import chat_stream, LLMError
from ..services.image_service import (
    detect_image_request, build_image_prompt,
    build_fallback_image_prompt, generate_image, ImageGenerationError,
)
from .orchestrator import GenerationSession


def _get_latest_user_message(history):
    """从历史消息中获取最近一条用户消息。"""
    for msg in reversed(history):
        if msg.role == "user":
            return msg.content
    return ""


async def execute_character_generation(
    session: GenerationSession,
    character,
    all_characters=None,
    conversation=None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    执行单个角色的生成，产出 Orchestrator 格式的事件。

    这是旧的 _stream_character_response 的适配版本，输出统一事件格式。

    事件类型：
    - content: 流式文本块
    - image_start: 开始生成图片
    - image_done: 图片生成完成
    - image_error: 图片生成失败
    - error: 生成错误
    """
    db = SessionLocal()
    try:
        conversation_id = session.conversation_id
        user_id = session.user_id

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

        # 构建上下文
        messages = build_context(
            character, history, all_characters or [],
            conversation=conversation,
            memories=memories,
        )

        full_content = ""
        try:
            # 流式生成文本
            async for chunk in chat_stream(messages):
                # 检查是否被停止
                if session.should_stop:
                    break

                full_content += chunk
                yield {
                    "type": "content",
                    "character_id": character.id,
                    "character_name": character.name,
                    "text": chunk,
                }

            # 如果被停止，不保存不完整的回复
            if session.should_stop:
                return

            # 标记记忆已使用
            if memory_ids:
                db_mark = SessionLocal()
                try:
                    mem_svc.mark_memories_used(db_mark, memory_ids)
                finally:
                    db_mark.close()

            # 保存文本回复（Phase 3: 写入 generation_id 和 sequence_number）
            if full_content.strip():
                db2 = SessionLocal()
                try:
                    seq = session.next_sequence()
                    svc.add_message(
                        db2, conversation_id, user_id, "assistant",
                        full_content, character_id=character.id,
                        generation_id=session.generation_id,
                        sequence_number=seq,
                        message_type="text",
                    )
                finally:
                    db2.close()

            # ===== 图片生成 =====
            if wants_image and not session.should_stop:
                yield {
                    "type": "image_start",
                    "character_id": character.id,
                    "character_name": character.name,
                }

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
                        seq = session.next_sequence()
                        img_msg = svc.add_message(
                            db4, conversation_id, user_id, "assistant",
                            content="", character_id=character.id, image_url=image_url,
                            generation_id=session.generation_id,
                            sequence_number=seq,
                            message_type="image",
                        )
                        msg_id = img_msg.id
                    finally:
                        db4.close()

                    yield {
                        "type": "image_done",
                        "character_id": character.id,
                        "character_name": character.name,
                        "image_url": image_url,
                        "message_id": msg_id,
                    }

                except ImageGenerationError as e:
                    yield {
                        "type": "image_error",
                        "character_id": character.id,
                        "character_name": character.name,
                        "message": e.message,
                    }
                except Exception as e:
                    yield {
                        "type": "image_error",
                        "character_id": character.id,
                        "character_name": character.name,
                        "message": f"图片生成失败：{str(e)[:200]}",
                    }

            # ===== 异步记忆提取（后台任务，不阻塞 SSE）=====
            # 注意：这里不直接调用，而是在 Orchestrator 完成后由后台 worker 处理
            # Phase 4 会实现真正的异步记忆提取

        except LLMError as e:
            yield {
                "type": "error",
                "character_id": character.id,
                "character_name": character.name,
                "message": e.message,
            }
        except Exception as e:
            yield {
                "type": "error",
                "character_id": character.id,
                "character_name": character.name,
                "message": f"生成失败：{str(e)[:200]}",
            }
    finally:
        db.close()
