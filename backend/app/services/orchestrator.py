"""
Chat Core 2.0 - Conversation Orchestrator（聊天内核）

统一调度所有 AI 生成任务，解决：
- 同一 conversation 并发生成导致的重复回复/乱序
- 多条独立执行路径（stream/reply-all/discussion/drama）
- 停止不彻底（前端停止监听但后端继续生成）
- 生成状态不可追踪

核心概念：
- ResponsePlan：一次用户动作产生的唯一响应计划
- GenerationSession：一次生成任务的完整生命周期
- ConversationLock：会话级生成锁，同一 conversation 同时只能有一个 active session
- ConversationOrchestrator：统一调度入口
"""
import asyncio
import uuid
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, Callable, Awaitable


# ============================================================
# 枚举定义
# ============================================================

class ChatMode(str, Enum):
    """聊天模式（产品概念层）"""
    NORMAL = "normal"      # 普通聊天：我说一句，某个角色回答
    GROUP = "group"        # 群聊：我说一句，多个角色依次接话
    DRAMA = "drama"        # 剧情：进入正在发生的场景，角色持续演下去


class SpeakerStrategy(str, Enum):
    """发言策略（调度层，不和模式平行）"""
    SPECIFIC = "specific"      # 指定角色
    MENTION = "mention"        # @角色
    SMART = "smart"            # 智能选择


class GenerationStatus(str, Enum):
    """生成会话状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR = "error"


# ============================================================
# ResponsePlan：一次用户动作产生的唯一响应计划
# ============================================================

@dataclass
class ResponsePlan:
    """
    响应计划。一条用户消息只能产生一个 ResponsePlan。

    示例：
    - 普通+指定角色：{mode: normal, speakers: [1]}
    - 普通+@两人：{mode: normal, speakers: [1, 2]}
    - 普通+智能：{mode: normal, speakers: [3]}（由 router 决定）
    - 群聊：{mode: group, speakers: [1, 2, 3]}
    - 剧情：{mode: drama, speakers: [1, 2, 3], drama_config: {...}}
    """
    mode: ChatMode
    speakers: List[int] = field(default_factory=list)  # character_id 列表，按发言顺序
    strategy: SpeakerStrategy = SpeakerStrategy.SPECIFIC
    user_message: str = ""
    conversation_id: int = 0
    user_id: str = ""
    generation_id: str = field(default_factory=lambda: f"gen_{uuid.uuid4().hex[:12]}")
    drama_config: Optional[Dict[str, Any]] = None  # 剧情模式专用配置
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "speakers": self.speakers,
            "strategy": self.strategy.value,
            "user_message": self.user_message,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "generation_id": self.generation_id,
            "drama_config": self.drama_config,
            "metadata": self.metadata,
        }


# ============================================================
# GenerationSession：一次生成任务的完整生命周期
# ============================================================

@dataclass
class GenerationSession:
    """
    生成会话。跟踪一次 AI 生成任务的完整状态。

    一个 conversation 同时只能有一个 status in (RUNNING, PAUSED, STOPPING) 的 session。
    """
    generation_id: str
    conversation_id: int
    user_id: str
    plan: ResponsePlan
    status: GenerationStatus = GenerationStatus.IDLE
    current_speaker_index: int = 0
    current_character_id: Optional[int] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_message: Optional[str] = None
    sequence_counter: int = 0  # 消息序列号，保证顺序
    # 内部控制
    _stop_event: Optional[asyncio.Event] = None
    _pause_event: Optional[asyncio.Event] = None

    def __post_init__(self):
        if self._stop_event is None:
            self._stop_event = asyncio.Event()
        if self._pause_event is None:
            self._pause_event = asyncio.Event()
            self._pause_event.set()  # 默认不暂停

    @property
    def is_active(self) -> bool:
        """是否处于活跃状态（running/paused/stopping）"""
        return self.status in (
            GenerationStatus.RUNNING,
            GenerationStatus.PAUSED,
            GenerationStatus.STOPPING,
        )

    @property
    def is_stopped(self) -> bool:
        return self.status in (GenerationStatus.STOPPED, GenerationStatus.STOPPING)

    @property
    def should_stop(self) -> bool:
        return self._stop_event.is_set() if self._stop_event else False

    def start(self):
        self.status = GenerationStatus.RUNNING
        self.started_at = time.time()

    def pause(self):
        if self.status == GenerationStatus.RUNNING:
            self.status = GenerationStatus.PAUSED
            if self._pause_event:
                self._pause_event.clear()

    def resume(self):
        if self.status == GenerationStatus.PAUSED:
            self.status = GenerationStatus.RUNNING
            if self._pause_event:
                self._pause_event.set()

    def request_stop(self):
        """请求停止。设置 stop event，生成循环会检测到并优雅停止。"""
        self.status = GenerationStatus.STOPPING
        if self._stop_event:
            self._stop_event.set()
        if self._pause_event:
            self._pause_event.set()  # 解除暂停，让停止检查能执行

    def complete(self):
        self.status = GenerationStatus.COMPLETED
        self.completed_at = time.time()

    def fail(self, error_message: str):
        self.status = GenerationStatus.ERROR
        self.error_message = error_message
        self.completed_at = time.time()

    def mark_stopped(self):
        self.status = GenerationStatus.STOPPED
        self.completed_at = time.time()

    def next_sequence(self) -> int:
        """获取下一个消息序列号，保证递增。"""
        self.sequence_counter += 1
        return self.sequence_counter

    async def wait_if_paused(self):
        """如果处于暂停状态，等待恢复。"""
        if self._pause_event and self.status == GenerationStatus.PAUSED:
            await self._pause_event.wait()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generation_id": self.generation_id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "status": self.status.value,
            "current_speaker_index": self.current_speaker_index,
            "current_character_id": self.current_character_id,
            "mode": self.plan.mode.value,
            "speakers": self.plan.speakers,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
            "sequence_counter": self.sequence_counter,
        }


# ============================================================
# ConversationLock：会话级生成锁
# ============================================================

class ConversationLock:
    """
    会话级生成锁。

    保证同一个 conversation_id 同时只能有一个 active generation session。
    基于内存的 asyncio.Lock + session 注册表。

    注意：这是单进程内存锁。Render 免费实例是单进程，足够用。
    如果未来多实例部署，需要换成 Redis 锁。
    """

    def __init__(self):
        self._locks: Dict[int, asyncio.Lock] = {}
        self._sessions: Dict[int, GenerationSession] = {}  # conversation_id -> active session
        self._global_lock = asyncio.Lock()

    async def _get_lock(self, conversation_id: int) -> asyncio.Lock:
        async with self._global_lock:
            if conversation_id not in self._locks:
                self._locks[conversation_id] = asyncio.Lock()
            return self._locks[conversation_id]

    def get_active_session(self, conversation_id: int) -> Optional[GenerationSession]:
        """获取当前活跃的生成会话。"""
        session = self._sessions.get(conversation_id)
        if session and session.is_active:
            return session
        return None

    async def acquire(self, conversation_id: int, plan: ResponsePlan) -> GenerationSession:
        """
        尝试获取会话锁并创建生成会话。

        如果已有 active session，抛出异常（不排队，直接拒绝，让用户看到"正在回复"）。
        """
        lock = await self._get_lock(conversation_id)

        # 先检查是否已有活跃 session
        existing = self.get_active_session(conversation_id)
        if existing:
            raise GenerationConflictError(
                f"会话 {conversation_id} 正在生成中（generation_id={existing.generation_id}），请稍候。",
                existing_session=existing,
            )

        # 获取锁（由于前面已检查 active session，这里应该能立即获取）
        await lock.acquire()

        session = GenerationSession(
            generation_id=plan.generation_id,
            conversation_id=conversation_id,
            user_id=plan.user_id,
            plan=plan,
        )
        self._sessions[conversation_id] = session
        session._lock = lock  # 绑定锁，释放时用
        return session

    def release(self, conversation_id: int):
        """释放会话锁。"""
        session = self._sessions.get(conversation_id)
        if session:
            lock = getattr(session, '_lock', None)
            if lock and lock.locked():
                lock.release()
        # 清理 session 引用（但不删除，方便查询历史）
        # 实际 session 对象由调用方持有

    def stop_session(self, conversation_id: int, generation_id: Optional[str] = None) -> Optional[GenerationSession]:
        """
        停止指定会话的生成。

        如果指定了 generation_id，只停止匹配的 session。
        """
        session = self.get_active_session(conversation_id)
        if session:
            if generation_id and session.generation_id != generation_id:
                return None  # 不是当前 session，不停止
            session.request_stop()
            return session
        return None

    def pause_session(self, conversation_id: int) -> Optional[GenerationSession]:
        session = self.get_active_session(conversation_id)
        if session and session.status == GenerationStatus.RUNNING:
            session.pause()
            return session
        return None

    def resume_session(self, conversation_id: int) -> Optional[GenerationSession]:
        session = self.get_active_session(conversation_id)
        if session and session.status == GenerationStatus.PAUSED:
            session.resume()
            return session
        return None


# ============================================================
# 异常定义
# ============================================================

class GenerationConflictError(Exception):
    """生成冲突：同一 conversation 已有活跃生成任务。"""
    def __init__(self, message: str, existing_session: Optional[GenerationSession] = None):
        super().__init__(message)
        self.existing_session = existing_session


class OrchestratorError(Exception):
    """调度器错误。"""
    pass


# ============================================================
# ConversationOrchestrator：统一调度入口
# ============================================================

class ConversationOrchestrator:
    """
    聊天内核统一调度器。

    所有用户动作（发送、@、指定角色、群聊、剧情、插话、停止、暂停、继续）
    都必须经过这个调度器，禁止任何组件绕过它直接调用 AI API。

    使用方式：
        orchestrator = ConversationOrchestrator()

        # 1. 规划
        plan = orchestrator.plan(
            mode=ChatMode.NORMAL,
            strategy=SpeakerStrategy.MENTION,
            user_message="@小雅 你好",
            conversation_id=1,
            user_id="user123",
            characters=[...],
        )

        # 2. 执行（获取锁 + 创建 session + 执行生成器）
        async for event in orchestrator.execute(plan, character_generator):
            # 处理 SSE 事件
            pass

        # 3. 控制
        orchestrator.stop(conversation_id=1)
        orchestrator.pause(conversation_id=1)
        orchestrator.resume(conversation_id=1)
    """

    def __init__(self):
        self.lock_manager = ConversationLock()
        self._sessions_history: Dict[str, GenerationSession] = {}  # generation_id -> session

    # ----------------------------------------------------------
    # 规划阶段：根据用户动作生成 ResponsePlan
    # ----------------------------------------------------------

    def plan(
        self,
        mode: ChatMode,
        user_message: str,
        conversation_id: int,
        user_id: str,
        characters: List[Any],
        strategy: SpeakerStrategy = SpeakerStrategy.SPECIFIC,
        specified_character_id: Optional[int] = None,
        mentioned_character_ids: Optional[List[int]] = None,
        drama_config: Optional[Dict[str, Any]] = None,
        smart_router_fn: Optional[Callable] = None,
    ) -> ResponsePlan:
        """
        根据用户动作生成唯一的 ResponsePlan。

        这是"一条用户消息只能产生一个 ResponsePlan"的核心保证。
        """
        speakers = []

        if strategy == SpeakerStrategy.SPECIFIC and specified_character_id:
            speakers = [specified_character_id]

        elif strategy == SpeakerStrategy.MENTION and mentioned_character_ids:
            speakers = mentioned_character_ids

        elif strategy == SpeakerStrategy.SMART:
            # 智能路由：调用外部 router 函数决定谁该说话
            if smart_router_fn:
                result = smart_router_fn(user_message, characters)
                if isinstance(result, list):
                    speakers = result
                elif isinstance(result, int):
                    speakers = [result]
            # 如果智能路由失败，回退到第一个角色
            if not speakers and characters:
                speakers = [characters[0].id]

        elif mode == ChatMode.GROUP:
            # 群聊：所有角色按 sort_order 依次发言
            speakers = [c.id for c in characters]

        elif mode == ChatMode.DRAMA:
            # 剧情：指定参与角色，持续推进
            if drama_config and "character_ids" in drama_config:
                speakers = drama_config["character_ids"]
            else:
                speakers = [c.id for c in characters]

        # 验证 speaker 有效性
        valid_ids = {c.id for c in characters}
        speakers = [sid for sid in speakers if sid in valid_ids]

        if not speakers and characters:
            speakers = [characters[0].id]

        plan = ResponsePlan(
            mode=mode,
            speakers=speakers,
            strategy=strategy,
            user_message=user_message,
            conversation_id=conversation_id,
            user_id=user_id,
            drama_config=drama_config,
        )
        return plan

    # ----------------------------------------------------------
    # 执行阶段：获取锁 + 创建 session + 执行生成
    # ----------------------------------------------------------

    async def execute(
        self,
        plan: ResponsePlan,
        character_generator: Callable[[GenerationSession, Any], Awaitable[Any]],
        character_lookup: Optional[Dict[int, Any]] = None,
    ):
        """
        执行 ResponsePlan，产出 SSE 事件流。

        Args:
            plan: 响应计划
            character_generator: 异步生成器函数，接收 (session, character)，yield 事件 dict
            character_lookup: character_id -> character 对象的映射

        Yields:
            dict: SSE 事件（统一格式，包含 generation_id）
        """
        # 1. 获取会话锁（如果冲突会抛 GenerationConflictError）
        session = await self.lock_manager.acquire(plan.conversation_id, plan)
        self._sessions_history[session.generation_id] = session

        try:
            session.start()

            # 统一事件包装：给所有事件加上 generation_id
            async def wrap_event(event: dict) -> dict:
                if "generation_id" not in event:
                    event["generation_id"] = session.generation_id
                return event

            # generation_started 事件
            yield await wrap_event({
                "type": "generation_started",
                "conversation_id": plan.conversation_id,
                "mode": plan.mode.value,
                "speakers": plan.speakers,
                "strategy": plan.strategy.value,
            })

            # 2. 按计划执行每个 speaker
            for idx, char_id in enumerate(plan.speakers):
                # 检查停止
                if session.should_stop:
                    break

                # 等待暂停恢复
                await session.wait_if_paused()
                if session.should_stop:
                    break

                session.current_speaker_index = idx
                session.current_character_id = char_id

                # 查找 character 对象
                character = None
                if character_lookup and char_id in character_lookup:
                    character = character_lookup[char_id]

                if character is None:
                    # 跳过无效角色
                    continue

                # character_started 事件
                yield await wrap_event({
                    "type": "character_started",
                    "character_id": char_id,
                    "character_name": getattr(character, "name", ""),
                    "speaker_index": idx,
                    "sequence": session.next_sequence(),
                })

                # 执行角色生成器
                try:
                    async for event in character_generator(session, character):
                        if session.should_stop:
                            break
                        yield await wrap_event(event)
                except Exception as e:
                    yield await wrap_event({
                        "type": "generation_error",
                        "character_id": char_id,
                        "message": str(e)[:200],
                    })
                    # 单个角色失败不中断整个计划（剧情模式除外）
                    if plan.mode == ChatMode.DRAMA:
                        session.fail(str(e))
                        break

                # character_completed 事件
                yield await wrap_event({
                    "type": "character_completed",
                    "character_id": char_id,
                    "character_name": getattr(character, "name", ""),
                    "speaker_index": idx,
                })

            # 3. 完成
            if session.should_stop:
                session.mark_stopped()
                yield await wrap_event({
                    "type": "generation_stopped",
                    "reason": "user_requested",
                })
            elif session.status == GenerationStatus.ERROR:
                yield await wrap_event({
                    "type": "generation_error",
                    "message": session.error_message or "未知错误",
                })
            else:
                session.complete()
                yield await wrap_event({
                    "type": "generation_completed",
                    "total_speakers": len(plan.speakers),
                })

        except GenerationConflictError:
            raise
        except Exception as e:
            session.fail(str(e))
            yield {
                "type": "generation_error",
                "generation_id": session.generation_id,
                "message": str(e)[:200],
            }
        finally:
            # 释放锁
            self.lock_manager.release(plan.conversation_id)

    # ----------------------------------------------------------
    # 控制接口：停止/暂停/继续
    # ----------------------------------------------------------

    def stop(self, conversation_id: int, generation_id: Optional[str] = None) -> Optional[GenerationSession]:
        """停止指定会话的生成。"""
        return self.lock_manager.stop_session(conversation_id, generation_id)

    def pause(self, conversation_id: int) -> Optional[GenerationSession]:
        """暂停指定会话的生成（剧情模式用）。"""
        return self.lock_manager.pause_session(conversation_id)

    def resume(self, conversation_id: int) -> Optional[GenerationSession]:
        """恢复指定会话的生成。"""
        return self.lock_manager.resume_session(conversation_id)

    def get_session(self, conversation_id: int) -> Optional[GenerationSession]:
        """获取当前活跃的生成会话。"""
        return self.lock_manager.get_active_session(conversation_id)

    def get_session_by_id(self, generation_id: str) -> Optional[GenerationSession]:
        """通过 generation_id 获取会话。"""
        return self._sessions_history.get(generation_id)


# ============================================================
# 全局单例
# ============================================================

# 全局调度器实例，整个后端共享
_orchestrator: Optional[ConversationOrchestrator] = None


def get_orchestrator() -> ConversationOrchestrator:
    """获取全局调度器单例。"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ConversationOrchestrator()
    return _orchestrator
