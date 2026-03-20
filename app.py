from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
import jsonlog
import uvicorn
import config as env_config
import init as app_init
import background_tasks
from email_processor import EmailProcessor


app_config = env_config.Config(group="APP")
logger = jsonlog.setup_logger("app")
processor = EmailProcessor()


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Run startup checks and schema migrations before accepting requests."""
    app_init.initialize()
    await background_tasks.start_background_tasks()
    try:
        yield
    finally:
        await background_tasks.stop_background_tasks()


app = FastAPI(lifespan=lifespan)


# FastAPI routes
@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/api/emails", response_model=Dict[str, Any])
async def get_emails(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    mailid: Optional[str] = None,
    sender: Optional[str] = None,
    receiver: Optional[str] = None,
):
    """
    List emails with minimal metadata (lightweight).
    
    Supports filtering by mailid, sender, and receiver.
    Returns paginated results with basic email info.
    Use GET /api/emails/{mailid} to fetch full email details.
    """
    try:
        return await processor.get_emails_list(
            limit=limit,
            offset=offset,
            mailid=mailid,
            sender=sender,
            receiver=receiver,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Error fetching emails: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/emails/{mailid}", response_model=Dict[str, Any])
async def get_email_by_id(mailid: str):
    """
    Fetch a single email by mailid with full metadata and raw content.
    """
    try:
        result = await processor.get_email_by_mailid(mailid)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error"))
        return result
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Error fetching email {mailid}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=int(app_config.get("APP_PORT")))