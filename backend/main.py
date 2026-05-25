"""LLM Wiki — FastAPI application entry point."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.config import settings, hardware_summary
from backend import log_stream
from backend.routers import files, chat, logs
from backend.services import search, watcher, llm, embeddings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings.raw_dir.mkdir(parents=True, exist_ok=True)
    settings.wiki_dir.mkdir(parents=True, exist_ok=True)
    (settings.wiki_dir / "sources").mkdir(exist_ok=True)
    (settings.wiki_dir / "entities").mkdir(exist_ok=True)
    (settings.wiki_dir / "concepts").mkdir(exist_ok=True)

    loop = asyncio.get_event_loop()
    log_stream.install(loop)
    search.rebuild_index()
    watcher.start(loop)
    logger.info("Hardware: %s", hardware_summary())
    logger.info("LLM Wiki started on http://%s:%s", settings.host, settings.port)
    # Pre-load models in background — eliminates cold-start TTFT on first query
    asyncio.create_task(llm.warmup_chat_model())
    asyncio.create_task(embeddings.warmup_embed_model())
    yield
    # Shutdown
    watcher.stop()


app = FastAPI(title="LLM Wiki", lifespan=lifespan)

app.include_router(files.router)
app.include_router(files.folders_router)
app.include_router(chat.router)
app.include_router(logs.router)

# Serve frontend at root
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
