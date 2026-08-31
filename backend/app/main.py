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

# CORS - RC-3 测试阶段允许所有来源，确保 Staging 和 Production 都能访问
# 测试完成后可以改回严格模式
allow_origins = ["*"]

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
