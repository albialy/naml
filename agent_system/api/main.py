from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from agent_system.api.routes import tasks, sessions, auth, admin, settings
from agent_system.core.connectors.groq_connector import GroqConnector
from agent_system.core.connectors.openrouter_connector import OpenRouterConnector
import logging
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(title="Multi-Agent AI Orchestration")

# CORS middleware for localhost:3000 and any origin needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(settings.router)
app.include_router(tasks.router)
app.include_router(sessions.router)

@app.on_event("startup")
async def startup_event():
    logger.info("Validating API connections... / التحقق من اتصالات واجهة برمجة التطبيقات...")
    groq = GroqConnector()
    if groq.validate_connection():
        logger.info("Groq connection successful / تم الاتصال بـ Groq بنجاح")
    else:
        logger.warning("Groq connection failed / فشل الاتصال بـ Groq")
        
    openrouter = OpenRouterConnector()
    if openrouter.validate_connection():
        logger.info("OpenRouter connection successful / تم الاتصال بـ OpenRouter بنجاح")
    else:
        logger.warning("OpenRouter connection failed / فشل الاتصال بـ OpenRouter")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "System is running / النظام يعمل"}

# Serve React build (must be AFTER all API routes)
DIST_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "dist")
if os.path.exists(DIST_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        # API routes already handled above; serve index.html for everything else
        index_path = os.path.join(DIST_DIR, "index.html")
        return FileResponse(index_path)
