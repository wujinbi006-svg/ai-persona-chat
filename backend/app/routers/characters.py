from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..schemas.conversation import CharacterCreate, CharacterUpdate, CharacterOut
from ..services import conversation_service as svc
from ..services.auth import get_current_user

router = APIRouter(prefix="/api", tags=["characters"])


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
    char = svc.update_character(db, char_id, user_id=current_user["id"], name=body.name, persona=body.persona, avatar=body.avatar)
    if not char:
        raise HTTPException(status_code=404, detail="角色不存在")
    return char


@router.delete("/characters/{char_id}")
def delete_character(char_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    ok = svc.delete_character(db, char_id, user_id=current_user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="角色不存在")
    return {"ok": True}
