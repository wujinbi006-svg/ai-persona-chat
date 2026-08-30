from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..schemas.conversation import (
    CharacterCreate, CharacterUpdate, CharacterOut,
    MemoryCreate, MemoryUpdate, MemoryOut,
)
from ..services import conversation_service as svc
from ..services import memory_service as mem_svc
from ..services.auth import get_current_user

router = APIRouter(prefix="/api", tags=["characters"])


# ===== Character CRUD =====

@router.get("/conversations/{conv_id}/characters", response_model=List[CharacterOut])
def list_characters(conv_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    conv = svc.get_conversation(db, conv_id, user_id=current_user["id"])
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    return svc.list_characters(db, conv_id, user_id=current_user["id"])


@router.post("/conversations/{conv_id}/characters", response_model=CharacterOut)
def create_character(conv_id: int, body: CharacterCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    conv = svc.get_conversation(db, conv_id, user_id=current_user["id"])
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    return svc.create_character(db, conv_id, user_id=current_user["id"], name=body.name, persona=body.persona, avatar=body.avatar)


@router.patch("/characters/{char_id}", response_model=CharacterOut)
def update_character(char_id: int, body: CharacterUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    char = svc.update_character(
        db, char_id, user_id=current_user["id"],
        name=body.name, persona=body.persona, avatar=body.avatar,
        sort_order=body.sort_order,
    )
    if not char:
        raise HTTPException(status_code=404, detail="角色不存在")
    return char


@router.delete("/characters/{char_id}")
def delete_character(char_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    ok = svc.delete_character(db, char_id, user_id=current_user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="角色不存在")
    return {"ok": True}


@router.post("/characters/{char_id}/reorder", response_model=CharacterOut)
def reorder_character(char_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """上移/下移角色。需要 direction 参数。"""
    from fastapi import Request
    # 简化：通过 query param
    raise HTTPException(status_code=400, detail="请使用 /characters/{id}/move?direction=up|down")


@router.post("/characters/{char_id}/move", response_model=CharacterOut)
def move_character(char_id: int, direction: str = "up", db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """上移/下移角色。direction: up 或 down"""
    if direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="direction 必须是 up 或 down")
    char = svc.reorder_character(db, char_id, current_user["id"], direction)
    if not char:
        raise HTTPException(status_code=404, detail="角色不存在")
    return char


# ===== Memory CRUD =====

@router.get("/characters/{char_id}/memories", response_model=List[MemoryOut])
def list_character_memories(char_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """获取角色的记忆列表。"""
    char = svc.get_character(db, char_id, user_id=current_user["id"])
    if not char:
        raise HTTPException(status_code=404, detail="角色不存在")
    return mem_svc.list_memories(
        db, current_user["id"],
        conversation_id=char.conversation_id,
        character_id=char_id,
    )


@router.post("/characters/{char_id}/memories", response_model=MemoryOut)
def create_character_memory(char_id: int, body: MemoryCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """为角色添加记忆。"""
    char = svc.get_character(db, char_id, user_id=current_user["id"])
    if not char:
        raise HTTPException(status_code=404, detail="角色不存在")
    return mem_svc.create_memory(
        db, current_user["id"], char.conversation_id,
        content=body.content,
        memory_type=body.memory_type,
        importance=body.importance,
        character_id=char_id,
    )


@router.get("/conversations/{conv_id}/memories", response_model=List[MemoryOut])
def list_conversation_memories(conv_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """获取会话的所有记忆（包括角色私有和共享）。"""
    conv = svc.get_conversation(db, conv_id, user_id=current_user["id"])
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    return mem_svc.list_memories(db, current_user["id"], conversation_id=conv_id)


@router.put("/memories/{memory_id}", response_model=MemoryOut)
def update_memory(memory_id: int, body: MemoryUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """更新记忆。"""
    mem = mem_svc.update_memory(
        db, memory_id, current_user["id"],
        content=body.content,
        memory_type=body.memory_type,
        importance=body.importance,
        is_active=body.is_active,
    )
    if not mem:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return mem


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """删除记忆。"""
    ok = mem_svc.delete_memory(db, memory_id, current_user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"ok": True}
