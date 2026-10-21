# Transaction Webhook Processing Service

A Python backend service that accepts transaction webhooks, acknowledges them quickly, and processes transactions
asynchronously. The service uses FastAPI, PostgreSQL, Redis, and RQ, with a recovery process for transactions that need
to be scheduled again.

## Live Deployment

- **Public API:** https://transaction-webhook-service-zwca.onrender.com
- **API documentation (Swagger UI):** https://transaction-webhook-service-zwca.onrender.com/docs
- **Health check:** https://transaction-webhook-service-zwca.onrender.com/
- **GitHub repository:** https://github.com/ShashwathDasa/transaction-webhook-service

The deployed service has been verified with a successful webhook submission, background job execution, and a transaction
status lookup returning `PROCESSED`.

> **Free-tier hosting notice:** The application is hosted on Render's free tier for demonstration and evaluation. The
> web service may spin down after inactivity, causing cold-start delays. The free PostgreSQL database expires 30 days
> after creation. Availability and data retention are therefore not guaranteed indefinitely. The deployment should not
> be
> used for production workloads.

## Features

- **Fast webhook acknowledgement:** Returns `202 Accepted` when a transaction webhook is accepted.
- **Persistent transaction state:** Stores transaction details, status, and timestamps in PostgreSQL.
- **Asynchronous processing:** Uses Redis and RQ to process transactions outside the API request path.
- **Configurable processing delay:** Simulates an external operation with a default delay of 30 seconds.
- **Duplicate transaction prevention:** Uses `transaction_id` to identify transactions uniquely and avoid creating
  duplicate records.
- **Processing ownership:** Uses conditional database updates and unique processing tokens to protect transaction state
  from stale worker attempts.
- **Recovery service:** Periodically identifies stale `PROCESSING` transactions and older `RECEIVED` transactions that
  may need to be scheduled again.
- **Input validation:** Uses Pydantic schemas to validate incoming webhook payloads.
- **Automated tests:** Covers health checks, request validation, webhook responses, idempotency, worker behavior, and
  recovery scenarios.
- **Containerized deployment:** Supports local Docker Compose and a Render deployment.

## Technology Stack

- Python 3.12
- FastAPI and Uvicorn
- PostgreSQL
- SQLAlchemy
- Redis and RQ
- Pydantic and Pydantic Settings
- Docker and Docker Compose
- Pytest
- Render

## Architecture

```text
                         Client
                           |
                           v
                    FastAPI Application
                      /           \
                     v             v
               PostgreSQL       Redis / RQ
              Transaction DB        |
                                    v
                               RQ Worker
                                    |
                                    v
                                PostgreSQL

                         Recovery Service
                                |
                                v
                    Finds eligible stale transactions
                    and schedules processing attempts
```

The API persists a transaction before enqueueing its background job. The RQ worker claims a transaction by conditionally
changing its status from `RECEIVED` to `PROCESSING`.

Each processing attempt receives a unique token. The worker updates the final transaction state only when its processing
token and current status still match the database record.

The recovery service periodically looks for stale transactions and attempts to schedule eligible work again.

### Local and deployed execution

**Local development:** Docker Compose runs the API, worker, recovery service, PostgreSQL, and Redis as separate
containers.

**Render deployment:** PostgreSQL and Redis-compatible Key Value run as hosted services. The application image uses
`start.sh`, which selects its processes with the `SERVICE_ROLE` environment variable:

| `SERVICE_ROLE`  | Processes started                                   |
|-----------------|-----------------------------------------------------|
| `api`           | FastAPI application                                 |
| `worker`        | `WORKER_COUNT` RQ workers and the recovery service  |
| `all` (default) | All of the above in one container                   |

Running the API and the background processes as separate Render services keeps the 30-second processing jobs from
competing with webhook requests for CPU, which helps the webhook respond within 500 ms under load. `start.sh` exits when
any of its processes dies, so Render restarts the service rather than leaving it partially running.

#### Deploy as separate services on Render

1. **Web Service** (Docker): set `SERVICE_ROLE=api`, plus `DATABASE_URL`, `REDIS_URL`, and `TRANSACTION_QUEUE_NAME`.
2. **Background Worker** (Docker, same repository): set `SERVICE_ROLE=worker`, `WORKER_COUNT`, `DATABASE_URL`,
   `REDIS_URL`, `TRANSACTION_QUEUE_NAME`, `PROCESSING_DELAY_SECONDS=30`, `RECOVERY_INTERVAL_SECONDS`, and
   `STALE_TRANSACTION_SECONDS`.

Both services must use the same database, Redis instance, and queue name. Use the internal connection URLs, with both
services in the same region as PostgreSQL and Key Value. Render Background Workers are not available on the free
instance type; `SERVICE_ROLE=all` runs everything in a single free web service at the cost of webhook latency under
load.

## Project Structure

```text
transaction-webhook-service/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── queue.py
│   ├── routes/
│   │   ├── health.py
│   │   └── transactions.py
│   └── services/
│       └── transaction_service.py
├── worker/
│   ├── tasks.py
│   └── recovery.py
├── tests/
│   ├── conftest.py
│   ├── test_health.py
│   ├── test_queue_status.py
│   ├── test_received_recovery.py
│   ├── test_recovery_enqueue.py
│   ├── test_transaction_idempotency.py
│   ├── test_webhook_response.py
│   ├── test_webhook_validation.py
│   ├── test_worker_idempotency.py
│   └── test_worker_recovery.py
├── Dockerfile
├── docker-compose.yml
├── start.sh
├── init_db.py
├── load_test.py
├── requirements.txt
├── .env.example
└── README.md
```

## Prerequisites

For local development:

- Docker Desktop with Docker Compose
- Git
- Python 3.12 or a compatible version for running tests locally

## Run Locally with Docker Compose

### 1. Clone the repository

```bash
git clone https://github.com/ShashwathDasa/transaction-webhook-service.git
cd transaction-webhook-service
```

### 2. Configure environment variables

Create a local environment file:

```bash
cp .env.example .env
```

Review the values in `.env`. The example configuration is intended for local development only.

Do not commit `.env` or publish database credentials, passwords, or connection URLs containing secrets. The repository's
`.gitignore` excludes environment files.

### 3. Start the services

```bash
docker compose --env-file .env up --build -d
```

Check their status:

```bash
docker compose --env-file .env ps
```

PostgreSQL and Redis should report healthy, and the API, worker, and recovery containers should be running.

The FastAPI application initializes missing database tables at startup. The separate `init_db.py` script is available
for explicit manual initialization if needed.

### 4. Check the health endpoint

```bash
curl -i http://localhost:8000/
```

Example response:

```json
{
  "status": "HEALTHY",
  "current_time": "2026-10-21T16:00:00+00:00"
}
```

The timestamp is illustrative and will vary.

### 5. Open the API documentation

Visit:

http://localhost:8000/docs

The Swagger UI lets you inspect endpoints and submit test requests interactively.

## API Reference

### 1. Health check

`GET /`

Returns the service health status and current UTC timestamp.

Example:

```bash
curl -i https://transaction-webhook-service-zwca.onrender.com/
```

### 2. Submit a transaction webhook

`POST /v1/webhooks/transactions`

#### Request body

```json
{
  "transaction_id": "txn_001",
  "source_account": "account_a",
  "destination_account": "account_b",
  "amount": 125.50,
  "currency": "INR"
}
```

#### Example request

```bash
curl -i -X POST \
  "https://transaction-webhook-service-zwca.onrender.com/v1/webhooks/transactions" \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "txn_001",
    "source_account": "account_a",
    "destination_account": "account_b",
    "amount": 125.50,
    "currency": "INR"
  }'
```

#### Successful response

The endpoint returns `202 Accepted` when the webhook is accepted.

```json
{
  "message": "Transaction webhook received",
  "transaction_id": "txn_001",
  "status": "RECEIVED"
}
```

If the transaction already exists, the existing transaction record is reused. The response may therefore show its
current status, including `PROCESSING` or `PROCESSED`.

If a transaction is saved but job scheduling fails, the endpoint returns `503 Service Unavailable`. The transaction
remains persisted so the recovery process can attempt to schedule it later.

### 3. Retrieve transaction status

`GET /v1/transactions/{transaction_id}`

Example:

```bash
curl -i \
  "https://transaction-webhook-service-zwca.onrender.com/v1/transactions/txn_001"
```

The response includes:

- `transaction_id`
- `source_account`
- `destination_account`
- `amount`
- `currency`
- `status`
- `created_at`
- `processed_at`

A missing transaction returns `404 Not Found`.

### 4. Queue status

`GET /v1/queue`

Reports the processing backlog. The queue is clear when `queued_jobs` is `0`.

Example:

```bash
curl -i https://transaction-webhook-service-zwca.onrender.com/v1/queue
```

```json
{
  "queue": "transactions",
  "queued_jobs": 12,
  "started_jobs": 2,
  "workers": 2,
  "busy_workers": 2
}
```

Returns `503 Service Unavailable` if Redis cannot be reached.

### Transaction lifecycle

| Status       | Meaning                                               |
|--------------|-------------------------------------------------------|
| `RECEIVED`   | The transaction is persisted and awaiting processing. |
| `PROCESSING` | A worker has claimed the transaction.                 |
| `PROCESSED`  | Processing completed successfully.                    |

## End-to-End Test

Submit a webhook using a unique transaction ID:

```bash
curl -i -X POST \
  "https://transaction-webhook-service-zwca.onrender.com/v1/webhooks/transactions" \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "deploy-test-001",
    "source_account": "account-001",
    "destination_account": "account-002",
    "amount": 250.00,
    "currency": "INR"
  }'
```

Wait approximately 35–45 seconds, then retrieve the transaction:

```bash
curl -i \
  "https://transaction-webhook-service-zwca.onrender.com/v1/transactions/deploy-test-001"
```

The expected final state is:

```json
{
  "transaction_id": "deploy-test-001",
  "status": "PROCESSED"
}
```

The actual response also includes the account details, amount, currency, and timestamps.

The deployed service has successfully processed a test transaction and returned its `PROCESSED` status.

### Duplicate webhook test

Submit the same webhook payload again with the same `transaction_id`.

The API should return `202 Accepted` and reuse the existing transaction. Verify the stored record and database state to
confirm that only one transaction exists for that ID.

### Load test

`load_test.py` sends concurrent webhooks and reports how many returned `202 Accepted` and how many took longer than
500 ms, along with average, p95, and maximum response times. It uses only the Python standard library.

```bash
# Local service (default: http://localhost:8000)
python load_test.py

# Another deployment
python load_test.py https://transaction-webhook-service-zwca.onrender.com
```

`LOAD_TEST_REQUESTS` (default `20`) and `LOAD_TEST_CONCURRENCY` (default `10`) change the number of webhooks and how many
are sent at once. The script calls the health check first so that a cold start is not counted as webhook latency.

Each request creates a real transaction. With the 30-second processing delay and two workers, 20 webhooks take about
five minutes to process, and transactions submitted afterwards wait behind them. The script prints the queue status at
the end; check `GET /v1/queue` until `queued_jobs` is `0` before running other tests. Measured times include the network
round trip from wherever the script runs.

## Background Processing and Recovery

### RQ worker

The worker processes transactions asynchronously. It attempts to claim a transaction only when the current status is
`RECEIVED`, then simulates the processing operation using the configured delay.

The worker's final database update checks the transaction's current state and processing token. This helps prevent an
outdated processing attempt from overwriting a newer attempt's result.

### Recovery service

The recovery service periodically:

- Identifies stale `PROCESSING` transactions.
- Resets eligible stale transactions so they can be attempted again.
- Finds older `RECEIVED` transactions that may not have been scheduled successfully.
- Attempts to enqueue eligible work.
- Logs scheduling failures so a failure affecting one transaction does not prevent the rest of the recovery cycle from
  continuing.

Relevant environment variables include:

| Variable                    |        Default | Purpose                                      |
|-----------------------------|---------------:|----------------------------------------------|
| `PROCESSING_DELAY_SECONDS`  |           `30` | Simulated processing delay                   |
| `RECOVERY_INTERVAL_SECONDS` |           `60` | Interval between recovery cycles             |
| `STALE_TRANSACTION_SECONDS` |          `120` | Age threshold for stale transaction recovery |
| `TRANSACTION_QUEUE_NAME`    | `transactions` | RQ queue name                                |

## Running Tests

The test suite uses a separate PostgreSQL database named `transactions_test`. Never point the test configuration at a
production database.

### 1. Configure the local environment

Ensure `.env` exists and the PostgreSQL service is running:

```bash
docker compose --env-file .env up -d postgres
```

### 2. Create the test database if necessary

```bash
docker compose --env-file .env exec postgres \
  psql -U postgres -d postgres \
  -c "CREATE DATABASE transactions_test;"
```

If PostgreSQL reports that the database already exists, continue.

The current test fixture uses this local connection URL:

```text
postgresql+psycopg://postgres:postgres@127.0.0.1:5435/transactions_test
```

If your local credentials or ports differ, update the test configuration in `tests/conftest.py` accordingly.

### 3. Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

### 4. Run the test suite

```bash
python3 -m pytest -q
```

The latest reported local run completed with 16 tests passing. Run the tests again after code changes to verify the
current state.

## Technical Decisions

### FastAPI

Provides Pydantic request validation, automatic OpenAPI documentation, and a small amount of code per endpoint. Invalid
webhook payloads are rejected with `422` before reaching the database.

### PostgreSQL and SQLAlchemy

PostgreSQL provides durable storage and the two features the design relies on: `INSERT ... ON CONFLICT` for idempotent
inserts and conditional `UPDATE ... RETURNING` statements for safely claiming work. SQLAlchemy keeps a pool of open
connections so concurrent webhooks do not each pay the cost of a new TLS connection to the database.

### Redis and RQ instead of in-process background tasks

FastAPI's `BackgroundTasks` run inside the API process, so a restart or redeploy during the 30-second delay would lose
the work. Jobs stored in Redis survive API restarts and are processed by separate worker processes. RQ was chosen over
Celery because it needs only Redis and very little configuration, which is sufficient for a single job type.

### Fast acknowledgement

The webhook does only two things before responding: one `INSERT ... RETURNING` into PostgreSQL and one enqueue into
Redis. The 30-second processing happens entirely in the worker, which keeps the response within the 500 ms target.

### Idempotency at three levels

- **Storage:** `transaction_id` is the primary key, and inserts use `ON CONFLICT DO NOTHING`, so duplicates never create
  a second record. Repeated webhooks still receive `202 Accepted`.
- **Scheduling:** only the request that created the record enqueues a job, and the job ID is derived from the
  transaction ID (`transaction-{transaction_id}`).
- **Processing:** a worker claims a transaction with a conditional `RECEIVED -> PROCESSING` update. If the same
  transaction is somehow queued twice, only one worker can claim it.

### Processing tokens

Each processing attempt stores a unique token with its claim and completes the transaction only if the token still
matches. If a slow attempt is recovered and retried, the outdated attempt cannot overwrite the newer one.

### Recovery process

Saving the transaction and enqueueing its job are separate operations, so either step can be interrupted. The recovery
process periodically re-enqueues `RECEIVED` transactions that were never scheduled and resets `PROCESSING` transactions
whose worker stopped, so transactions are not silently lost.

### Deployment

Docker Compose runs each component in its own container locally. On Render's free tier, `start.sh` runs the API,
workers, and recovery process in one container, and exits if any of them dies so Render restarts the service. The
`SERVICE_ROLE` setting allows the API and workers to be deployed as separate services when more resources are
available.

## Reliability Considerations and Limitations

The API commits the transaction to PostgreSQL before enqueueing the corresponding RQ job. Database persistence and queue
insertion are not a single atomic operation. The API reports scheduling failures, and the recovery process looks for
transactions that may need to be scheduled again. These mechanisms reduce the risk of stranded work, but they do not
provide an atomic delivery guarantee.

The processing token protects database state from stale worker attempts. If the simulated operation is replaced with a
real external side effect, the external system may also need an idempotency key or its own deduplication mechanism.

The deployed service has been verified for successful webhook acceptance, background processing, and transaction lookup.
The full range of failure scenarios—including real worker interruptions, Redis outages, recovery under sustained
failure, and concurrent requests—should be tested separately before describing the service as production-ready.

### Hosting limitations

The current Render deployment is intended for demonstration and evaluation:

- The free web service may spin down after inactivity, resulting in delayed responses while it starts again.
- The free PostgreSQL database expires 30 days after creation.
- Free Redis-compatible Key Value has limited resources and may not provide durable queue storage across restarts.
- With `SERVICE_ROLE=all`, the API, workers, and recovery process share one container's CPU, so webhook latency rises
  while jobs are running. Use separate `api` and `worker` services where possible.
- Public availability, latency under load, and long-term persistence are not guaranteed by this free-tier configuration.

Do not store important production data in this demonstration deployment.

## Environment Variables and Security

Use environment variables to configure database access, Redis, queue names, and processing intervals.

- Keep `.env` out of Git.
- Do not commit passwords, connection URLs containing credentials, or deployment secrets.
- Use internal/private database and Redis connections for hosted services whenever available.
- Use separate credentials and databases for testing and production.
- Avoid exposing PostgreSQL and Redis directly to the public internet.

## Stop Local Services

Stop the containers while preserving the local PostgreSQL volume:

```bash
docker compose --env-file .env down
```

To also delete the local database volume, use this command only if you intentionally want to remove its data:

```bash
docker compose --env-file .env down -v
```

## Future Improvements

Potential improvements include:

- Use database migrations rather than relying on `create_all()` for schema changes.
- Introduce a transactional outbox to coordinate transaction persistence and job scheduling more reliably.
- Add integration tests for concurrent duplicate requests and real queue/database failure scenarios.
- Add structured logs, metrics, alerting, and deployment monitoring.
- Pin dependency versions for reproducible builds.
- Use durable queue storage and an appropriate backup strategy.