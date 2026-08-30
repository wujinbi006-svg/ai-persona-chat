from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from ..database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), nullable=True, index=True)
    title = Column(String(200), default="新对话")
    persona = Column(Text, default="")
    # 基础叙事系统：场景信息
    scene = Column(String(500), default="")  # 地点
    scene_time = Column(String(100), default="")  # 时间
    scene_context = Column(Text, default="")  # 背景/天气/环境
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    characters = relationship("Character", back_populates="conversation", cascade="all, delete-orphan", order_by="Character.sort_order, Character.id")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id")
    memories = relationship("Memory", back_populates="conversation", cascade="all, delete-orphan")


class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    user_id = Column(String(36), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    persona = Column(Text, nullable=False, default="")
    avatar = Column(String(500), nullable=True)
    sort_order = Column(Integer, default=0)  # 角色排序
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="characters")
    messages = relationship("Message", back_populates="character")
    memories = relationship("Memory", back_populates="character")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    user_id = Column(String(36), nullable=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    image_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Phase 3: 数据一致性字段
    generation_id = Column(String(64), nullable=True, index=True)  # 所属生成会话
    sequence_number = Column(Integer, nullable=True)  # 生成内序列号（1,2,3...）
    parent_message_id = Column(Integer, nullable=True)  # 触发这条回复的用户消息 ID
    message_type = Column(String(20), default="text")  # text/image/system_event

    conversation = relationship("Conversation", back_populates="messages")
    character = relationship("Character", back_populates="messages")


class GenerationSession(Base):
    """Phase 3: 生成会话持久化表。

    记录每一次 AI 生成任务的完整生命周期，用于：
    - 跨请求的生成状态追踪
    - 生成唯一性保证（同一 conversation 同时只能有一个 active session）
    - 剧情模式的暂停/继续/停止
    - 消息顺序恢复
    """
    __tablename__ = "generation_sessions"

    id = Column(Integer, primary_key=True, index=True)
    generation_id = Column(String(64), unique=True, index=True, nullable=False)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    user_id = Column(String(36), nullable=True, index=True)

    mode = Column(String(20), default="normal")  # normal/group/drama
    strategy = Column(String(20), default="specific")  # specific/mention/smart
    status = Column(String(20), default="idle")  # idle/running/paused/stopping/stopped/completed/error

    speakers = Column(Text, default="[]")  # JSON: 角色 ID 列表
    current_speaker_index = Column(Integer, default=0)
    current_speaker_id = Column(Integer, nullable=True)
    sequence_number = Column(Integer, default=0)  # 已生成的消息数

    user_message = Column(Text, default="")
    error_message = Column(Text, nullable=True)

    # 控制标志
    stop_requested = Column(Boolean, default=False)
    pause_requested = Column(Boolean, default=False)

    # 剧情模式专用
    drama_config = Column(Text, nullable=True)  # JSON
    max_duration_seconds = Column(Integer, default=1800)  # 最大运行时间 30 分钟
    max_generations = Column(Integer, default=100)  # 最大连续生成次数

    started_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)

    conversation = relationship("Conversation")


class Fact(Base):
    """Phase 4: Canonical Facts（规范事实表）。

    与 Memory 区分：
    - Memory: 偏好、关系、事件等长期信息
    - Fact: 已确认的客观事实（如"案件纸条时间为18:45"）
    - Hypothesis: 角色的推测，不能成为 Fact

    Fact 状态：confirmed / uncertain / conflicted / superseded
    """
    __tablename__ = "facts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), nullable=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=True)  # 提出该事实的角色

    subject = Column(String(200), nullable=False)  # 事实主题，如"纸条时间"
    content = Column(Text, nullable=False)  # 事实内容
    fact_type = Column(String(30), default="fact")  # fact/hypothesis/assumption
    status = Column(String(20), default="confirmed")  # confirmed/uncertain/conflicted/superseded
    confidence = Column(Integer, default=100)  # 0-100 置信度

    source_message_id = Column(Integer, nullable=True)  # 来源消息 ID
    superseded_by = Column(Integer, nullable=True)  # 被哪个新事实取代

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    conversation = relationship("Conversation")
    character = relationship("Character")


class Memory(Base):
    """长期记忆表。"""
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), nullable=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=True)
    content = Column(Text, nullable=False)
    memory_type = Column(String(20), default="fact")  # user/character/relationship/event/preference/fact
    importance = Column(Integer, default=3)  # 1-5
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="memories")
    character = relationship("Character", back_populates="memories")
