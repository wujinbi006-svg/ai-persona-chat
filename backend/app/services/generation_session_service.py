"""
Phase 3: GenerationSession 持久化服务。

提供数据库级别的生成会话管理，与内存中的 ConversationLock 配合：
- 内存锁：快速拒绝并发请求（单进程内）
- 数据库持久化：跨请求追踪状态、剧情模式暂停/继续、崩溃恢复

核心保证：同一个 conversation 同一时间最多一个 active generation。
"""
import json
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from ..models.conversation import GenerationSession as GenerationSessionModel
from ..services.orchestrator import GenerationSession as MemorySession, GenerationStatus


ACTIVE_STATUSES = ["running", "paused", "stopping"]


def get_active_session(db: Session, conversation_id: int) -> Optional[GenerationSessionModel]:
    """获取当前会话的活跃生成会话（如果有）。"""
    return (
        db.query(GenerationSessionModel)
        .filter(
            GenerationSessionModel.conversation_id == conversation_id,
            GenerationSessionModel.status.in_(ACTIVE_STATUSES),
        )
        .order_by(GenerationSessionModel.id.desc())
        .first()
    )


def create_session(
    db: Session,
    generation_id: str,
    conversation_id: int,
    user_id: str,
    mode: str = "normal",
    strategy: str = "specific",
    speakers: Optional[List[int]] = None,
    user_message: str = "",
    drama_config: Optional[dict] = None,
) -> GenerationSessionModel:
    """创建新的生成会话。

    调用前应先检查 get_active_session，确保没有活跃会话。
    """
    session = GenerationSessionModel(
        generation_id=generation_id,
        conversation_id=conversation_id,
        user_id=user_id,
        mode=mode,
        strategy=strategy,
        status="idle",
        speakers=json.dumps(speakers or []),
        user_message=user_message,
        drama_config=json.dumps(drama_config) if drama_config else None,
        started_at=datetime.utcnow(),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def update_session_status(
    db: Session,
    generation_id: str,
    status: str,
    error_message: Optional[str] = None,
) -> Optional[GenerationSessionModel]:
    """更新生成会话状态。"""
    session = (
        db.query(GenerationSessionModel)
        .filter(GenerationSessionModel.generation_id == generation_id)
        .first()
    )
    if not session:
        return None

    session.status = status
    session.updated_at = datetime.utcnow()

    if status in ["stopped", "completed", "error"]:
        session.ended_at = datetime.utcnow()
        session.stop_requested = False
        session.pause_requested = False

    if error_message:
        session.error_message = error_message

    db.commit()
    db.refresh(session)
    return session


def update_session_progress(
    db: Session,
    generation_id: str,
    current_speaker_index: Optional[int] = None,
    current_speaker_id: Optional[int] = None,
    sequence_number: Optional[int] = None,
) -> Optional[GenerationSessionModel]:
    """更新生成会话进度（当前发言者、序列号）。"""
    session = (
        db.query(GenerationSessionModel)
        .filter(GenerationSessionModel.generation_id == generation_id)
        .first()
    )
    if not session:
        return None

    if current_speaker_index is not None:
        session.current_speaker_index = current_speaker_index
    if current_speaker_id is not None:
        session.current_speaker_id = current_speaker_id
    if sequence_number is not None:
        session.sequence_number = sequence_number

    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return session


def request_stop(db: Session, generation_id: str) -> bool:
    """请求停止生成会话。"""
    session = (
        db.query(GenerationSessionModel)
        .filter(GenerationSessionModel.generation_id == generation_id)
        .first()
    )
    if not session or session.status not in ACTIVE_STATUSES:
        return False

    session.stop_requested = True
    session.status = "stopping"
    session.updated_at = datetime.utcnow()
    db.commit()
    return True


def request_pause(db: Session, generation_id: str) -> bool:
    """请求暂停生成会话（剧情模式用）。"""
    session = (
        db.query(GenerationSessionModel)
        .filter(GenerationSessionModel.generation_id == generation_id)
        .first()
    )
    if not session or session.status != "running":
        return False

    session.pause_requested = True
    session.status = "paused"
    session.updated_at = datetime.utcnow()
    db.commit()
    return True


def request_resume(db: Session, generation_id: str) -> bool:
    """请求继续生成会话。"""
    session = (
        db.query(GenerationSessionModel)
        .filter(GenerationSessionModel.generation_id == generation_id)
        .first()
    )
    if not session or session.status != "paused":
        return False

    session.pause_requested = False
    session.status = "running"
    session.updated_at = datetime.utcnow()
    db.commit()
    return True


def get_session(db: Session, generation_id: str) -> Optional[GenerationSessionModel]:
    """通过 generation_id 获取会话。"""
    return (
        db.query(GenerationSessionModel)
        .filter(GenerationSessionModel.generation_id == generation_id)
        .first()
    )


def is_stop_requested(db: Session, generation_id: str) -> bool:
    """检查是否请求了停止。"""
    session = get_session(db, generation_id)
    if not session:
        return False
    return session.stop_requested or session.status in ["stopping", "stopped"]


def is_pause_requested(db: Session, generation_id: str) -> bool:
    """检查是否请求了暂停。"""
    session = get_session(db, generation_id)
    if not session:
        return False
    return session.pause_requested or session.status == "paused"


def cleanup_stale_sessions(db: Session, max_age_minutes: int = 60) -> int:
    """清理超时的活跃会话（崩溃恢复用）。

    将超过 max_age_minutes 仍处于 active 状态的会话标记为 error。
    """
    cutoff = datetime.utcnow()
    from datetime import timedelta
    cutoff = cutoff - timedelta(minutes=max_age_minutes)

    stale = (
        db.query(GenerationSessionModel)
        .filter(
            GenerationSessionModel.status.in_(ACTIVE_STATUSES),
            GenerationSessionModel.updated_at < cutoff,
        )
        .all()
    )

    for session in stale:
        session.status = "error"
        session.error_message = "Session timed out (stale cleanup)"
        session.ended_at = datetime.utcnow()

    if stale:
        db.commit()

    return len(stale)


def sync_memory_session_to_db(
    db: Session,
    memory_session: MemorySession,
) -> Optional[GenerationSessionModel]:
    """将内存中的 GenerationSession 状态同步到数据库。"""
    db_session = get_session(db, memory_session.generation_id)
    if not db_session:
        return None

    db_session.status = memory_session.status.value
    db_session.current_speaker_index = memory_session.current_speaker_index
    db_session.current_speaker_id = memory_session.current_character_id
    db_session.sequence_number = memory_session.sequence_counter
    db_session.stop_requested = memory_session.should_stop
    db_session.updated_at = datetime.utcnow()

    if memory_session.status in [GenerationStatus.STOPPED, GenerationStatus.COMPLETED, GenerationStatus.ERROR]:
        db_session.ended_at = datetime.utcnow()
        if memory_session.error_message:
            db_session.error_message = memory_session.error_message

    db.commit()
    db.refresh(db_session)
    return db_session
