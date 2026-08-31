"""
Chat Core 2.0 - Generation Executor（生成执行器）

把现有的角色回复生成逻辑包装成 Orchestrator 需要的 character_generator 格式。
这是旧代码和新内核之间的适配器层。
"""
import asyncio
import json
from typing import AsyncGenerator, Dict, Any
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..services import conversation_service as svc
from ..services import memory_service as mem_svc
from ..services import fact_service as fact_svc
from ..services.context_service import build_context
from ..services.llm_client import chat_stream, LLMError
from ..services.image_service import (
    detect_image_request, build_image_prompt,
    build_fallback_image_prompt, generate_image, ImageGenerationError,
)
from .orchestrator import GenerationSession


# 后台记忆提取任务跟踪（防止任务被 GC）
_background_memory_tasks = set()


def _get_latest_user_message(history):
    """从历史消息中获取最近一条用户消息。"""
    for msg in reversed(history):
        if msg.role == "user":
            return msg.content
    return ""


async def _stream_with_cancel(chat_stream_agen, session: GenerationSession):
    """
    RC-2: 真正的 Stop - 包装 chat_stream，支持在 should_stop 时立即取消。

    使用 asyncio.Queue + producer task 实现：
    - producer task 从 chat_stream 读取 chunk，放入队列
    - consumer 从队列读取 chunk，同时定期检查 should_stop
    - 当 should_stop 为 true 时，取消 producer task，立即停止

    保持流式输出：chunk 一到达就 yield，不会等待全部完成。
    正确处理 asyncio.CancelledError，释放 HTTP 连接。
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    _DONE = object()

    async def _producer():
        try:
            async for chunk in chat_stream_agen:
                await queue.put(chunk)
                # 检查 should_stop，如果是则停止读取
                if session.should_stop:
                    break
        except asyncio.CancelledError:
            # 被取消，正常退出
            pass
        except Exception:
            # 生产者异常，放入队列让消费者处理
            pass
        finally:
            try:
                await queue.put(_DONE)
            except Exception:
                pass

    producer_task = asyncio.create_task(_producer())

    try:
        while True:
            # 等待下一个 chunk，同时定期检查 should_stop
            get_task = asyncio.create_task(queue.get())
            done, pending = await asyncio.wait(
                [get_task],
                timeout=0.05,  # 50ms 检查一次 should_stop
                return_when=asyncio.FIRST_COMPLETED,
            )

            # 检查 should_stop，如果是则取消所有任务并返回
            if session.should_stop:
                producer_task.cancel()
                get_task.cancel()
                try:
                    await producer_task
                except asyncio.CancelledError:
                    pass
                return

            if get_task in done:
                chunk = get_task.result()
                if chunk is _DONE:
                    break
                yield chunk
            else:
                # 超时，取消 get_task，继续循环
                get_task.cancel()
    finally:
        # 确保 producer task 被取消
        if not producer_task.done():
            producer_task.cancel()
            try:
                await producer_task
            except asyncio.CancelledError:
                pass


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

        # 检索 Canonical Facts（已确认事实 + 假设 + 冲突事实）
        # 事实与假设分离：hypothesis 不会自动成为 confirmed fact
        try:
            facts = fact_svc.get_facts(
                db, user_id, conversation_id=conversation_id,
                status_filter=["confirmed", "uncertain", "conflicted"],
            )
        except Exception:
            # Facts 查询失败不影响主流程
            facts = []

        # 构建上下文（按优先级：Persona → Canonical Facts → Memories → Scene → History）
        messages = build_context(
            character, history, all_characters or [],
            conversation=conversation,
            memories=memories,
            facts=facts,
        )

        full_content = ""
        try:
            # RC-2: 真正的 Stop - 使用 _stream_with_cancel 包装 chat_stream
            # 当 session.should_stop 为 true 时，立即取消当前 LLM streaming task
            # 不再是"等当前 chunk 到达后停止"，而是真正取消正在执行的 HTTP stream
            async for chunk in _stream_with_cancel(chat_stream(messages), session):
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

            # ===== Phase 4: 异步记忆提取（后台任务，不阻塞 SSE）=====
            # 记忆提取在后台异步执行，不等待完成，不阻塞 SSE 流结束
            # Phase 9 + 遗留问题4: 生产审计 + 可观测性
            # - 独立数据库会话，不影响主流程事务
            # - 全异常捕获，失败不影响聊天成功
            # - 详细日志：started / completed / failed，带 conversation_id
            # - Render 重启时任务消失是可接受的（主聊天已完成，记忆提取是 best-effort）
            import logging
            _logger = logging.getLogger(__name__)

            async def _extract_memories_background():
                _logger.info(f"[Memory] 后台记忆提取开始 (conversation={conversation_id}, character={character.name})")
                try:
                    db_bg = SessionLocal()
                    try:
                        if mem_svc.should_extract(db_bg, conversation_id, user_id):
                            all_msgs = svc.get_messages(db_bg, conversation_id, user_id=user_id)
                            all_chars = svc.list_characters(db_bg, conversation_id, user_id=user_id)
                            await mem_svc.extract_memories_from_batch(
                                db_bg, user_id, conversation_id, all_msgs, all_chars
                            )
                            _logger.info(f"[Memory] 后台记忆提取完成 (conversation={conversation_id}, messages={len(all_msgs)})")
                        else:
                            _logger.info(f"[Memory] 后台记忆提取跳过（未达到提取阈值） (conversation={conversation_id})")
                    finally:
                        db_bg.close()
                except Exception as e:
                    # 遗留问题4: 后台记忆提取失败不影响主流程，但记录详细日志便于追踪
                    _logger.warning(
                        f"[Memory] 后台记忆提取失败 (conversation={conversation_id}): {str(e)[:200]}",
                        exc_info=True,
                    )

            # 启动后台任务，不等待
            bg_task = asyncio.create_task(_extract_memories_background())
            _background_memory_tasks.add(bg_task)
            bg_task.add_done_callback(_background_memory_tasks.discard)

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
