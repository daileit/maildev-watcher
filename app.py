from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import jsonlog
import uvicorn
import config as env_config


app_config = env_config.Config(group="APP")

logger = jsonlog.setup_logger("app")
app = FastAPI()

# FastAPI routes
@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=int(app_config.get("APP_PORT")))