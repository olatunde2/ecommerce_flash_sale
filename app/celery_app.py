from celery import Celery

from ecommerce_flash_sale.app.config import Settings

settings = Settings()
celery_app = Celery(
    "flash_sale",
    broker=settings.celery_broker_url,
    include=["ecommerce_flash_sale.app.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
)
