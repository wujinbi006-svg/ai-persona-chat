from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .migrations import run_migrations
from .routers import conversations, chat, characters
from .config import settings

Base.metadata.create_all(bind=engine)
run_migrations()

app = FastAPI(title="AI 人格聊天平台", version="3.0.0")

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

app.include_router(conversations.router)
app.include_router(characters.router)
app.include_router(chat.router)


@app.get("/health")
def health_root():
    return {"status": "ok", "mode": "supabase" if settings.USE_SUPABASE else "local"}

@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "supabase" if settings.USE_SUPABASE else "local"}
