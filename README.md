# Event-Driven E-Commerce Flash Sale Engine

Runnable starter implementation for an inventory-safe flash-sale API using FastAPI, PostgreSQL, Redis, Celery, RabbitMQ, and Docker Compose.

## Start locally with Docker

```powershell
Copy-Item .env.example .env
docker compose up --build
```

The API is available at <http://localhost:8000>; interactive API docs are at <http://localhost:8000/docs>. The initial schema is created on API startup for this starter. Use database migrations before deploying schema changes to production.

The API allows browser requests from `localhost`, `127.0.0.1`, and `[::1]` development origins. For a deployed web UI, set `CORS_ALLOWED_ORIGINS` to a comma-separated list of exact trusted origins (scheme and host, such as `https://dashboard.example.com`) before starting Compose. After changing backend code or CORS settings, recreate the API with `docker compose up --build -d api`.

## API flow

Create a product:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/products `
  -ContentType "application/json" `
  -Body '{"name":"Flash Sale Headphones","price":"49.99","stock":20}'
```

Place an order (replace `product_id` as needed):

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/orders `
  -ContentType "application/json" `
  -Body '{"product_id":1,"quantity":2}'
```

The order endpoint locks the selected product row with PostgreSQL `SELECT ... FOR UPDATE`, checks and decrements stock in the same transaction, then queues notification and invoice tasks. Insufficient stock returns HTTP 409. Notifications are logged by the worker, and invoice JSON is written to the shared `invoices` volume.

## Rate limiting

Requests under `/api/` pass through an atomic Redis sorted-set sliding window keyed by client IP. Defaults are 100 requests per 60 seconds and can be changed with `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW_SECONDS`. `/health` remains available without rate limiting. If Redis is unavailable, API requests fail closed with HTTP 503.

## Load test

Install the development dependencies (including Locust) in your active virtual environment with `python -m pip install -r requirements-dev.txt`. Do not run `python locustfile.py`; Locust loads that file as a test plan. For a benchmark, set `RATE_LIMIT_REQUESTS=200000` in `.env` before starting the stack, create product `1` with a large stock amount, then run:

```powershell
docker compose up --build -d
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/products `
  -ContentType "application/json" `
  -Body '{"name":"Load Test Product","price":"1.00","stock":100000}'
python -m locust -f locustfile.py --host http://localhost:8000 --headless -u 500 -r 100 --run-time 2m --only-summary
```

If this is not a fresh database, use the existing product ID or clear/recreate the test data rather than creating a duplicate. Locust exercises health checks, product reads, and concurrent order attempts; expected out-of-stock responses are not reported as failures. This generates traffic, but does not guarantee 500 requests/second or under-50ms latency. Those outcomes depend on hardware, Docker resources, client placement, and configuration. Check Locust's measured request rate and latency percentiles to verify the target on your environment.

## Important next steps

- Add authentication/authorization for product administration and order ownership.
- Replace startup `create_all` with Alembic migrations.
- Add a transactional outbox or retry/reconciliation mechanism for durable task delivery; order commits currently succeed even if queue submission fails, and the failure is logged.
- Add integration tests against PostgreSQL and Redis, plus worker retry/error handling.
