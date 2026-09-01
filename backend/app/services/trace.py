"""
Chat Core 2.0 - Performance Trace Instrumentation

记录一次聊天请求的完整链路时间点 T0~T16，用于精确定位性能瓶颈。

时间点定义：
  T0  = 用户点击发送（前端）
  T1  = 前端 POST /api/chat/v2/generate 发出
  T2  = 后端收到请求
  T3  = Supabase Auth 验证完成
  T4  = Conversation / Character 查询完成
  T5  = Memory 检索开始
  T6  = Memory 检索完成
  T7  = ResponsePlan 开始
  T8  = ResponsePlan 完成
  T9  = GenerationSession 创建完成
  T10 = LLM 请求发出
  T11 = LLM HTTP connection 建立
  T12 = LLM streaming 开始
  T13 = 第一个 token 到达后端
  T14 = 第一个 SSE event 到达浏览器（前端）
  T15 = React/UI 显示第一个 token（前端）
  T16 = 完整回复结束

所有后端时间点使用 time.perf_counter()（高精度单调时钟）。
前端时间点由前端 performance.now() 记录，通过请求头或 SSE 事件回传。
"""
import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


@dataclass
class SpeakerTrace:
    """单个角色的生成 trace（用于 @多人/群聊的逐角色分析）。"""
    character_id: int
    character_name: str
    speaker_index: int
    # 该角色的 LLM 调用时间点（相对于请求 T2）
    llm_request_sent: Optional[float] = None      # T10 per-speaker
    llm_connection: Optional[float] = None         # T11 per-speaker
    llm_streaming_start: Optional[float] = None    # T12 per-speaker
    first_token_backend: Optional[float] = None    # T13 per-speaker
    generation_complete: Optional[float] = None    # 该角色生成完成
    token_count: int = 0
    error: Optional[str] = None


@dataclass
class RequestTrace:
    """一次聊天请求的完整性能 trace。"""
    trace_id: str = field(default_factory=lambda: f"trace_{uuid.uuid4().hex[:12]}")

    # ---- 前端时间点（由前端通过请求头 X-Trace-T0 / X-Trace-T1 传入）----
    t0_user_click: Optional[float] = None
    t1_post_sent: Optional[float] = None

    # ---- 后端时间点（time.perf_counter() 绝对值）----
    t2_backend_received: Optional[float] = None
    t3_auth_done: Optional[float] = None
    t4_db_query_done: Optional[float] = None
    t5_memory_start: Optional[float] = None
    t6_memory_done: Optional[float] = None
    t7_plan_start: Optional[float] = None
    t8_plan_done: Optional[float] = None
    t9_session_created: Optional[float] = None
    t10_llm_request_sent: Optional[float] = None
    t11_llm_connection: Optional[float] = None
    t12_llm_streaming_start: Optional[float] = None
    t13_first_token_backend: Optional[float] = None
    t16_complete: Optional[float] = None

    # ---- 逐角色 trace（@多人/群聊）----
    speaker_traces: List[SpeakerTrace] = field(default_factory=list)
    _current_speaker: Optional[SpeakerTrace] = None

    # ---- 元数据 ----
    mode: str = ""
    strategy: str = ""
    conversation_id: int = 0
    user_id: str = ""
    llm_request_count: int = 0  # 实际发出的 LLM 请求次数（检测重复请求）
    retry_count: int = 0
    cold_start: bool = False  # 是否为 Render 冷启动后的第一个请求

    def mark(self, name: str):
        """标记一个时间点。name 应为 t2_backend_received 等属性名。"""
        ts = time.perf_counter()
        if hasattr(self, name):
            setattr(self, name, ts)
        else:
            logger.warning(f"[Trace] Unknown trace point: {name}")

    def mark_speaker_start(self, character_id: int, character_name: str, speaker_index: int):
        """标记一个角色开始生成。"""
        st = SpeakerTrace(
            character_id=character_id,
            character_name=character_name,
            speaker_index=speaker_index,
        )
        self.speaker_traces.append(st)
        self._current_speaker = st

    def mark_speaker_point(self, name: str):
        """标记当前角色的时间点。"""
        if self._current_speaker and hasattr(self._current_speaker, name):
            setattr(self._current_speaker, name, time.perf_counter())

    def mark_speaker_complete(self, token_count: int = 0, error: Optional[str] = None):
        """标记当前角色生成完成。"""
        if self._current_speaker:
            self._current_speaker.generation_complete = time.perf_counter()
            self._current_speaker.token_count = token_count
            self._current_speaker.error = error
            self._current_speaker = None

    def increment_llm_request(self):
        """记录一次 LLM 请求发出（用于检测重复请求）。"""
        self.llm_request_count += 1

    def increment_retry(self):
        """记录一次 retry。"""
        self.retry_count += 1

    def _ms(self, val: Optional[float], base: Optional[float]) -> Optional[float]:
        """转换为相对于 base 的毫秒数。"""
        if val is None or base is None:
            return None
        return round((val - base) * 1000, 2)

    def to_dict(self) -> Dict[str, Any]:
        """输出完整 trace 数据，所有时间点转换为相对于 T2 的毫秒数。"""
        base = self.t2_backend_received
        result = {
            "trace_id": self.trace_id,
            "mode": self.mode,
            "strategy": self.strategy,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "cold_start": self.cold_start,
            "llm_request_count": self.llm_request_count,
            "retry_count": self.retry_count,
            # 前端时间点（如果有，转为相对于 T2 的估计值）
            "t0_user_click_ms": self._ms(self.t0_user_click, base) if self.t0_user_click else None,
            "t1_post_sent_ms": self._ms(self.t1_post_sent, base) if self.t1_post_sent else None,
            # 后端时间点（相对于 T2 的毫秒数）
            "t2_backend_received_ms": 0.0,
            "t3_auth_done_ms": self._ms(self.t3_auth_done, base),
            "t4_db_query_done_ms": self._ms(self.t4_db_query_done, base),
            "t5_memory_start_ms": self._ms(self.t5_memory_start, base),
            "t6_memory_done_ms": self._ms(self.t6_memory_done, base),
            "t7_plan_start_ms": self._ms(self.t7_plan_start, base),
            "t8_plan_done_ms": self._ms(self.t8_plan_done, base),
            "t9_session_created_ms": self._ms(self.t9_session_created, base),
            "t10_llm_request_sent_ms": self._ms(self.t10_llm_request_sent, base),
            "t11_llm_connection_ms": self._ms(self.t11_llm_connection, base),
            "t12_llm_streaming_start_ms": self._ms(self.t12_llm_streaming_start, base),
            "t13_first_token_backend_ms": self._ms(self.t13_first_token_backend, base),
            "t16_complete_ms": self._ms(self.t16_complete, base),
            # 关键耗时区间（毫秒）
            "durations": self._compute_durations(),
            # 逐角色 trace
            "speaker_traces": [
                {
                    "character_id": st.character_id,
                    "character_name": st.character_name,
                    "speaker_index": st.speaker_index,
                    "llm_request_sent_ms": self._ms(st.llm_request_sent, base),
                    "llm_connection_ms": self._ms(st.llm_connection, base),
                    "llm_streaming_start_ms": self._ms(st.llm_streaming_start, base),
                    "first_token_backend_ms": self._ms(st.first_token_backend, base),
                    "generation_complete_ms": self._ms(st.generation_complete, base),
                    "token_count": st.token_count,
                    "error": st.error,
                    "ttft_ms": self._ms(st.first_token_backend, st.llm_request_sent),
                    "generation_duration_ms": self._ms(st.generation_complete, st.llm_request_sent),
                }
                for st in self.speaker_traces
            ],
        }
        return result

    def _compute_durations(self) -> Dict[str, Optional[float]]:
        """计算各阶段耗时（毫秒）。"""
        def diff(a: Optional[float], b: Optional[float]) -> Optional[float]:
            if a is None or b is None:
                return None
            return round((a - b) * 1000, 2)

        return {
            # 前端→后端
            "frontend_to_backend_ms": diff(self.t2_backend_received, self.t1_post_sent) if self.t1_post_sent else None,
            # Auth
            "auth_ms": diff(self.t3_auth_done, self.t2_backend_received),
            # DB 查询
            "db_query_ms": diff(self.t4_db_query_done, self.t3_auth_done),
            # Memory 检索
            "memory_retrieval_ms": diff(self.t6_memory_done, self.t5_memory_start),
            # ResponsePlan
            "response_plan_ms": diff(self.t8_plan_done, self.t7_plan_start),
            # GenerationSession 创建
            "session_creation_ms": diff(self.t9_session_created, self.t8_plan_done),
            # LLM 连接建立
            "llm_connection_ms": diff(self.t11_llm_connection, self.t10_llm_request_sent),
            # LLM TTFT（请求发出→首 token）
            "llm_ttft_ms": diff(self.t13_first_token_backend, self.t10_llm_request_sent),
            # LLM 完整生成（首 token→完成）
            "llm_generation_ms": diff(self.t16_complete, self.t13_first_token_backend),
            # 总后端耗时
            "total_backend_ms": diff(self.t16_complete, self.t2_backend_received),
            # 首 token 总耗时（T2→T13）
            "time_to_first_token_ms": diff(self.t13_first_token_backend, self.t2_backend_received),
        }

    def log_summary(self):
        """输出 trace 摘要到日志。"""
        d = self._compute_durations()
        logger.info(
            f"[Trace] {self.trace_id} mode={self.mode} strategy={self.strategy} "
            f"conv={self.conversation_id} "
            f"TTFT={d.get('time_to_first_token_ms')}ms "
            f"LLM_TTFT={d.get('llm_ttft_ms')}ms "
            f"Auth={d.get('auth_ms')}ms "
            f"DB={d.get('db_query_ms')}ms "
            f"Memory={d.get('memory_retrieval_ms')}ms "
            f"Plan={d.get('response_plan_ms')}ms "
            f"LLM_conn={d.get('llm_connection_ms')}ms "
            f"Total={d.get('total_backend_ms')}ms "
            f"LLM_reqs={self.llm_request_count} "
            f"Speakers={len(self.speaker_traces)}"
        )


# 全局冷启动检测：记录进程启动时间
_PROCESS_START_TIME = time.perf_counter()
_FIRST_REQUEST_HANDLED = False


def is_cold_start() -> bool:
    """检测是否为 Render 冷启动后的第一个请求。"""
    global _FIRST_REQUEST_HANDLED
    if not _FIRST_REQUEST_HANDLED:
        _FIRST_REQUEST_HANDLED = True
        # 如果进程启动后超过 30 秒才收到第一个请求，认为是冷启动
        elapsed = time.perf_counter() - _PROCESS_START_TIME
        return elapsed > 5.0  # 正常热启动应该在几秒内有请求
    return False
