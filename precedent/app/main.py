# precedent/app/main.py
from fastapi import FastAPI
from .api import router as ai_router

def create_app() -> FastAPI:
    app = FastAPI(title="precedent API")

    @app.get("/health")
    def health():
        return {"ok": True}

    app.include_router(ai_router)  # /ai/...
    return app

# 단독 실행 지원
app = create_app()
