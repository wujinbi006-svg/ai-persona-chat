from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List


# ===== Conversation =====

class ConversationCreate(BaseModel):
    title: Optional[str] = None


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    scene: Optional[str] = None
    scene_time: Optional[str] = None
    scene_context: Optional[str] = None


class ConversationOut(BaseModel):
    id: int
    title: str
    persona: str
    scene: str = ""
    scene_time: str = ""
    scene_context: str = ""
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ===== Character =====

class CharacterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    persona: str = ""
    avatar: Optional[str] = None


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    persona: Optional[str] = None
    avatar: Optional[str] = None
    sort_order: Optional[int] = None


class CharacterOut(BaseModel):
    id: int
    conversation_id: int
    name: str
    persona: str
    avatar: Optional[str] = None
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CharacterReorder(BaseModel):
    sort_order: int


# ===== Memory =====

class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=1)
    memory_type: str = Field("fact", pattern="^(user|character|relationship|event|preference|fact)$")
    importance: int = Field(3, ge=1, le=5)
    character_id: Optional[int] = None


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    memory_type: Optional[str] = Field(None, pattern="^(user|character|relationship|event|preference|fact)$")
    importance: Optional[int] = Field(None, ge=1, le=5)
    is_active: Optional[bool] = None


class MemoryOut(BaseModel):
    id: int
    conversation_id: Optional[int] = None
    character_id: Optional[int] = None
    content: str
    memory_type: str
    importance: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime

    model_config = {"from_attributes": True}


# ===== Message =====

class MessageOut(BaseModel):
    id: int
    conversation_id: int
    character_id: Optional[int] = None
    character_name: Optional[str] = None
    role: str
    content: str
    image_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ===== Chat =====

class ChatRequest(BaseModel):
    conversation_id: int
    message: str = Field(..., min_length=1)
    character_id: Optional[int] = None
    mode: Optional[str] = "manual"  # manual/smart
    mentioned_character_ids: Optional[List[int]] = None  # @角色解析后的ID列表，按出现顺序


class ReplyAllRequest(BaseModel):
    conversation_id: int
    message: Optional[str] = None


class DiscussionRequest(BaseModel):
    conversation_id: int
    character_ids: List[int]
    rounds: int = Field(5, ge=1, le=20)
    message: Optional[str] = None


class SmartRouteRequest(BaseModel):
    conversation_id: int
    message: str


# ===== Drama Mode =====

class DramaStartRequest(BaseModel):
    conversation_id: int
    character_ids: List[int]
    rounds: int = Field(3, ge=1, le=20)
    interval: float = Field(1.0, ge=0, le=10)  # 秒
    scene: Optional[str] = None
    scene_time: Optional[str] = None
    scene_context: Optional[str] = None


class DramaUserMessage(BaseModel):
    conversation_id: int
    message: str
