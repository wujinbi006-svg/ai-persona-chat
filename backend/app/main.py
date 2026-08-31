from pathlib import Path
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .database import engine, Base
from .migrations import run_migrations
from .routers import conversations, chat, characters, chat_v2
from .config import settings

Base.metadata.create_all(bind=engine)
run_migrations()

app = FastAPI(title="AI 人格聊天平台", version="3.1.0")

# RC-3: Release Version 标识
# 从环境变量获取版本号、commit hash、环境信息
APP_VERSION = os.getenv("APP_VERSION", "Chat Core 2.0 RC-3")
APP_COMMIT = os.getenv("APP_COMMIT", "staging")
APP_ENVIRONMENT = os.getenv("APP_ENVIRONMENT", "staging")

# CORS - RC-3 最终验收：收紧为精确域名，不允许 *
# 同时允许生产前端和当前 Staging 前端
allow_origins = [
    "https://ai-persona-chat-mu.vercel.app",  # 生产前端
    "https://ai-persona-chat-qkito1k5p-ai-persona-team.vercel.app",  # 当前 Staging 前端
    "https://ai-persona-chat-lm2nlumr7-ai-persona-team.vercel.app",  # 旧 Staging 前端（兼容）
]
# 如果环境变量配置了 FRONTEND_URL，也加入
if settings.FRONTEND_URL and settings.FRONTEND_URL not in allow_origins:
    allow_origins.append(settings.FRONTEND_URL)
print(f"[CORS] Allowed origins: {allow_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件：生成的图片
_image_dir = Path(settings.IMAGE_OUTPUT_DIR)
if not _image_dir.is_absolute():
    _image_dir = Path(__file__).resolve().parent.parent / _image_dir
_image_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/images", StaticFiles(directory=str(_image_dir)), name="generated_images")

app.include_router(conversations.router)
app.include_router(characters.router)
app.include_router(chat.router)
app.include_router(chat_v2.router)


@app.get("/health")
def health_root():
    return {"status": "ok", "mode": "supabase" if settings.USE_SUPABASE else "local"}

@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "supabase" if settings.USE_SUPABASE else "local"}

# RC-3: Release Version 接口
# 返回版本号、commit hash、环境信息，用于排查部署版本问题
@app.get("/api/version")
def version():
    return {
        "version": APP_VERSION,
        "commit": APP_COMMIT,
        "environment": APP_ENVIRONMENT,
        "app_name": "AI 人格聊天平台",
        "chat_core": "2.0",
    }
