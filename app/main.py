from datetime import datetime, timezone

from fastapi import FastAPI

from app.routes.transactions import router as transactions_router

app = FastAPI(
    title="Transaction Webhook Processing Service",
    description="An asynchronous transaction processing API",
    version="1.0.0",
)


@app.get("/")
def health_check():
    return {"status": "HEALTHY", "current_time": datetime.now(timezone.utc).isoformat()}


app.include_router(transactions_router, prefix="/v1")
