"""
认证服务。
- Supabase 模式：验证 JWT token，获取当前用户
- 本地模式：返回默认用户，不需要认证
"""
from typing import Optional, Dict
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import time
import threading

from ..config import settings

security = HTTPBearer(auto_error=False)

# 本地模式默认用户
LOCAL_USER = {"id": "local-user", "email": "local@dev.local", "display_name": "本地用户"}

# 简单内存限流：{user_id: [(timestamp, count), ...]}
_rate_limit_store: Dict[str, list] = {}
_rate_lock = threading.Lock()


def verify_supabase_jwt(token: str) -> Optional[dict]:
    """验证 Supabase JWT，返回用户信息。失败返回 None。"""
    try:
        # Supabase JWT 的 payload 在第二段，base64url 编码
        import base64
        import json
        parts = token.split(".")
        if len(parts) != 3:
            return None
        # 补 padding
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        # 检查过期
        if payload.get("exp", 0) < time.time():
            return None
        # Supabase JWT 中 sub 是用户 ID
        user_id = payload.get("sub")
        if not user_id:
            return None
        email = payload.get("email", "")
        return {"id": user_id, "email": email, "display_name": email.split("@")[0] if email else "用户"}
    except Exception:
        return None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """
    获取当前用户。
    - 本地模式：返回默认用户
    - Supabase 模式：从 Authorization header 验证 JWT
    """
    if not settings.USE_SUPABASE:
        return LOCAL_USER

    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="未登录")

    token = credentials.credentials
    user = verify_supabase_jwt(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")

    return user


def check_rate_limit(user_id: str) -> bool:
    """检查用户是否超过限流。返回 True 表示允许，False 表示超限。"""
    now = time.time()
    window = 60  # 60秒窗口
    with _rate_lock:
        if user_id not in _rate_limit_store:
            _rate_limit_store[user_id] = []
        # 清理过期记录
        _rate_limit_store[user_id] = [
            t for t in _rate_limit_store[user_id] if now - t < window
        ]
        if len(_rate_limit_store[user_id]) >= settings.RATE_LIMIT_PER_MINUTE:
            return False
        _rate_limit_store[user_id].append(now)
        return True
