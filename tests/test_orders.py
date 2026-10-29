from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from ecommerce_flash_sale.app.main import create_order
from ecommerce_flash_sale.app.models import Product
from ecommerce_flash_sale.app.schemas import OrderCreate


class FakeResult:
    def __init__(self, product: Product):
        self.product = product

    def scalar_one_or_none(self):
        return self.product


class FakeSession:
    def __init__(self, product: Product):
        self.product = product
        self.statement = None
        self.added = []
        self.committed = False

    async def execute(self, statement):
        self.statement = statement
        return FakeResult(self.product)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True

    async def refresh(self, value):
        value.id = 42


@pytest.mark.asyncio
async def test_order_decrements_stock_and_uses_row_lock(monkeypatch):
    product = Product(id=1, name="Headphones", price=Decimal("12.50"), stock=3)
    session = FakeSession(product)
    queued_tasks = []
    monkeypatch.setattr(
        "ecommerce_flash_sale.app.main.celery_app.send_task",
        lambda *args, **kwargs: queued_tasks.append((args, kwargs)),
    )

    order = await create_order(
        OrderCreate(product_id=1, quantity=2),
        session,
    )

    assert product.stock == 1
    assert order.total_amount == Decimal("25.00")
    assert session.committed
    assert len(queued_tasks) == 2
    sql = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql


@pytest.mark.asyncio
async def test_order_rejects_insufficient_stock_without_commit(monkeypatch):
    product = Product(id=1, name="Headphones", price=Decimal("12.50"), stock=1)
    session = FakeSession(product)
    monkeypatch.setattr(
        "ecommerce_flash_sale.app.main.celery_app.send_task",
        lambda *args, **kwargs: pytest.fail("No task should be queued"),
    )

    with pytest.raises(HTTPException) as exception:
        await create_order(OrderCreate(product_id=1, quantity=2), session)

    assert exception.value.status_code == 409
    assert product.stock == 1
    assert not session.committed
