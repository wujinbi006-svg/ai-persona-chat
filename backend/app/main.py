from pathlib import Path
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .database import engine, Base
from .migrations import run_migrations
from .routers import conversations, chat, characters, chat_v2
from .config import settings
from .services.llm_client import close_shared_client


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await close_shared_client()

Base.metadata.create_all(bind=engine)
run_migrations()

app = FastAPI(title="AI 人格聊天平台", version="3.1.0", lifespan=lifespan)

# Production Closure: Release Version 标识
# 从环境变量获取版本号、commit hash、环境信息
APP_VERSION = os.getenv("APP_VERSION", "Chat Core 2.0")
APP_COMMIT = os.getenv("RENDER_GIT_COMMIT") or os.getenv("APP_COMMIT") or "unknown"
APP_ENVIRONMENT = os.getenv("APP_ENVIRONMENT", "production")
BUILD_TIME = os.getenv("BUILD_TIME") or os.getenv("RENDER_GIT_COMMIT", "")

# CORS - Production Closure: 优先通过 FRONTEND_URL 环境变量管理
# 生产环境只允许正式前端，不再硬编码多个 Staging URL
if settings.FRONTEND_URL:
    allow_origins = [settings.FRONTEND_URL]
else:
    # 默认使用生产前端
    allow_origins = ["https://ai-persona-chat-mu.vercel.app"]
print(f"[CORS] Allowed origins: {allow_origins} (environment={APP_ENVIRONMENT})")

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

# Production Closure: Release Version 接口
# 返回版本号、commit hash、环境信息，用于排查部署版本问题
@app.get("/api/version")
def version():
    return {
        "service": "ai-persona-backend",
        "version": APP_VERSION,
        "commit": APP_COMMIT,
        "environment": APP_ENVIRONMENT,
        "build_time": BUILD_TIME,
        "app_name": "AI 人格聊天平台",
        "chat_core": "2.0",
    }
