from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
import jsonlog
import uvicorn
import config as env_config
import init as app_init
import background_tasks
from database import DatabaseClient


app_config = env_config.Config(group="APP")
logger = jsonlog.setup_logger("app")


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
        db = DatabaseClient()
        
        where_clauses = ["1=1"]
        params = []
        
        if mailid:
            where_clauses.append("`mailid` LIKE %s")
            params.append(f"%{mailid}%")
        
        if sender:
            where_clauses.append("`from` LIKE %s")
            params.append(f"%{sender}%")
        
        if receiver:
            where_clauses.append("`to` LIKE %s")
            params.append(f"%{receiver}%")
        
        where_sql = " AND ".join(where_clauses)
        
        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM `mw_metadata` WHERE {where_sql}"
        total = db.fetch_value(count_query, params) or 0
        
        # Get paginated metadata (lightweight)
        metadata_query = f"""
            SELECT `id`, `mailid`, `from`, `to`, `timestamp`, `subject`
            FROM `mw_metadata`
            WHERE {where_sql}
            ORDER BY `timestamp` DESC
            LIMIT %s OFFSET %s
        """
        params_with_pagination = params + [limit, offset]
        metadata_rows = db.execute_query(metadata_query, params_with_pagination)
        
        # Build lightweight email list
        emails = []
        for row in metadata_rows:
            email = {
                "id": row.get("id"),
                "mailid": row.get("mailid"),
                "from": row.get("from") or "",
                "to": row.get("to") or "",
                "timestamp": row.get("timestamp").isoformat() if row.get("timestamp") else None,
                "subject": row.get("subject") or "",
            }
            emails.append(email)
        
        return {
            "success": True,
            "data": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "count": len(emails),
                "emails": emails,
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Error fetching emails: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/emails/{mailid}", response_model=Dict[str, Any])
async def get_email_by_id(mailid: str):
    """
    Fetch a single email by mailid with full metadata and raw content.
    """
    try:
        db = DatabaseClient()
        
        metadata = db.fetch_one(
            """
            SELECT `id`, `mailid`, `from`, `to`, `timestamp`, `subject`,
                   `extracted_code`
            FROM `mw_metadata`
            WHERE `mailid` = %s
            LIMIT 1
            """,
            (mailid,),
        )
        
        if not metadata:
            raise HTTPException(status_code=404, detail=f"Email {mailid} not found")
        
        raw_content = db.fetch_one(
            "SELECT `raw_header`, `raw_body` FROM `mw_raw_content` WHERE `mailid` = %s LIMIT 1",
            (mailid,),
        )
        
        email = {
            "id": metadata.get("id"),
            "mailid": metadata.get("mailid"),
            "from": metadata.get("from") or "",
            "to": metadata.get("to") or "",
            "timestamp": metadata.get("timestamp").isoformat() if metadata.get("timestamp") else None,
            "subject": metadata.get("subject") or "",
            "extracted_code": metadata.get("extracted_code") or "",
            "raw": {
                "headers": raw_content.get("raw_header") if raw_content else "",
                "body": raw_content.get("raw_body") if raw_content else "",
            },
        }
        
        return {
            "success": True,
            "data": email,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Error fetching email {mailid}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=int(app_config.get("APP_PORT")))