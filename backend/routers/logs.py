"""SSE endpoint — streams live application logs to the frontend."""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend import log_stream

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/stream")
async def stream_logs():
    return StreamingResponse(
        log_stream.log_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
