from fastapi import FastAPI

from app.routes.health import router as health_router
from app.routes.transactions import router as transactions_router

app = FastAPI(
    title="Transaction Webhook Processing Service",
    description="An asynchronous transaction processing API",
    version="1.0.0",
)

app.include_router(health_router)
app.include_router(transactions_router, prefix="/v1")
