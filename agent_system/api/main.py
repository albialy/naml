from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import tasks, sessions, auth, admin, settings
from ..core.connectors.groq_connector import GroqConnector
from ..core.connectors.openrouter_connector import OpenRouterConnector
import logging
from dotenv import load_dotenv

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
