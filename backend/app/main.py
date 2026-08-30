from pathlib import Path
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

# CORS
if settings.USE_SUPABASE and settings.FRONTEND_URL:
    allow_origins = [settings.FRONTEND_URL]
else:
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
