import json
import logging
import os
from pathlib import Path

from ecommerce_flash_sale.app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="ecommerce_flash_sale.app.tasks.notify_order")
def notify_order(order_id: int, product_id: int, quantity: int) -> dict[str, int | str]:
    logger.info(
        "Order notification: order_id=%s product_id=%s quantity=%s",
        order_id,
        product_id,
        quantity,
    )
    return {"status": "logged", "order_id": order_id}


@celery_app.task(name="ecommerce_flash_sale.app.tasks.generate_invoice")
def generate_invoice(
    order_id: int, total_amount: str, currency: str
) -> dict[str, int | str]:
    output_dir = Path(os.getenv("INVOICE_OUTPUT_DIR", "./invoices"))
    output_dir.mkdir(parents=True, exist_ok=True)
    invoice_path = output_dir / f"order-{order_id}.json"
    invoice_path.write_text(
        json.dumps(
            {
                "order_id": order_id,
                "total_amount": total_amount,
                "currency": currency,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("Generated invoice: %s", invoice_path)
    return {"status": "generated", "order_id": order_id}
