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

**Render demonstration:** The web service runs the API, worker, and recovery process together using `start.sh`, while
PostgreSQL and Redis-compatible Key Value run as separate hosted services. This combined-process setup is a free-tier
demonstration workaround, not the recommended production architecture.

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
  "failed_jobs": 0,
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

Provides request validation and the HTTP endpoints for health checks, webhook submissions, and transaction lookup.

### PostgreSQL and SQLAlchemy

Provide durable transaction storage and conditional updates for coordinating worker state transitions.

### Redis and RQ

Separate background processing from request handling so the API does not wait for the simulated processing delay.

### Processing tokens

Help prevent stale worker attempts from writing a completion result after another attempt has taken ownership of the
transaction.

### Recovery process

Reduces the risk of transactions remaining unscheduled or stuck after certain worker or queue failures.

### Docker and Docker Compose

Provide a reproducible local development environment with separate containers for the API, worker, recovery process,
PostgreSQL, and Redis.

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
- Running the API, worker, and recovery process in one web-service container is a temporary workaround; separate,
  supervised services are preferable for production.
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
- Run the API, worker, and recovery service as separately supervised services in production.
- Add integration tests for concurrent duplicate requests and real queue/database failure scenarios.
- Add structured logs, metrics, alerting, and deployment monitoring.
- Pin dependency versions for reproducible builds.
- Use durable queue storage and an appropriate backup strategy.