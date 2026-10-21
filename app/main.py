from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.models import Transaction  # Ensures the model is registered
from app.routes.health import router as health_router
from app.routes.transactions import router as transactions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Transaction Webhook Processing Service",
    description="An asynchronous transaction processing API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(transactions_router, prefix="/v1")
