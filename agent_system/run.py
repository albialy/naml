import uvicorn
from dotenv import load_dotenv
import os

if __name__ == "__main__":
    # Load .env
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    load_dotenv(dotenv_path=env_path)
    
    # Run uvicorn on port 3000 to comply with environment constraints
    # Development mode (reload=True) can be enabled if running outside a restricted container
    print("Starting server on port 3000 / جاري بدء تشغيل الخادم على المنفذ 3000")
    uvicorn.run("api.main:app", host="0.0.0.0", port=3000, reload=True)
