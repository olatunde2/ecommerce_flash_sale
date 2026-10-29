import logging
import os
from contextlib import asynccontextmanager
from decimal import Decimal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.cors import CORSMiddleware

from ecommerce_flash_sale.app.rate_limit import enforce_rate_limit
from ecommerce_flash_sale.app.config import Settings
from ecommerce_flash_sale.app.database import create_database, get_session
from ecommerce_flash_sale.app.models import Base, Order, Product
from ecommerce_flash_sale.app.schemas import (
    OrderCreate,
    OrderResponse,
    ProductCreate,
    ProductResponse,
)
from ecommerce_flash_sale.app.celery_app import celery_app

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    engine, session_factory = create_database(settings)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = redis

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        await redis.ping()
        yield
    finally:
        await redis.aclose()
        await engine.dispose()


app = FastAPI(title="Flash Sale API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_requests(request: Request, call_next):
    rejection = await enforce_rate_limit(request)
    if rejection is not None:
        return rejection
    return await call_next(request)


@app.get("/health")
async def health(request: Request):
    try:
        await request.app.state.redis.ping()
    except Exception as exc:
        logger.exception("Health check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A required service is unavailable",
        ) from exc
    return {"status": "ok"}


@app.post(
    "/api/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_product(
    product_data: ProductCreate,
    session: AsyncSession = Depends(get_session),
):
    product = Product(**product_data.model_dump())
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


@app.get("/api/products/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    session: AsyncSession = Depends(get_session),
):
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.post(
    "/api/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    order_data: OrderCreate,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Product).where(Product.id == order_data.product_id).with_for_update()
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.stock < order_data.quantity:
        raise HTTPException(status_code=409, detail="Insufficient stock")

    product.stock -= order_data.quantity
    order = Order(
        product_id=product.id,
        quantity=order_data.quantity,
        total_amount=product.price * order_data.quantity,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)

    try:
        celery_app.send_task(
            "ecommerce_flash_sale.app.tasks.notify_order",
            args=[order.id, order.product_id, order.quantity],
            task_id=uuid4().hex,
        )
        celery_app.send_task(
            "ecommerce_flash_sale.app.tasks.generate_invoice",
            args=[
                order.id,
                str(order.total_amount),
                "USD",
            ],
            task_id=uuid4().hex,
        )
    except Exception:
        logger.exception(
            "Order %s was committed, but one or more background tasks could not be queued",
            order.id,
        )

    return order
