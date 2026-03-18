from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import jsonlog
import uvicorn
import config as env_config
import init as app_init


app_config = env_config.Config(group="APP")
logger = jsonlog.setup_logger("app")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Run startup checks and schema migrations before accepting requests."""
    app_init.initialize()
    yield


app = FastAPI(lifespan=lifespan)


# FastAPI routes
@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=int(app_config.get("APP_PORT")))