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

    conversation = relationship("Conversation", back_populates="messages")
    character = relationship("Character", back_populates="messages")


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
