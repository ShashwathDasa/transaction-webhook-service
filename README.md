# Transaction Webhook Service

A Python backend service that accepts transaction webhooks, acknowledges them with `202 Accepted`, and processes
transactions asynchronously. The service uses FastAPI, PostgreSQL, Redis, and RQ, with a separate recovery process for
transactions that need to be scheduled again.

> **Deployment status:** The application has been run locally with Docker Compose. Add the public GitHub repository URL
> and verified public API URL below after publishing and deploying the service.

- **Repository:** TODO — add public GitHub URL
- **Public API:** TODO — add verified deployment URL

## Features

- **Fast acknowledgement:** The webhook endpoint returns `202 Accepted` after the transaction is persisted and its
  background job is scheduled.
- **Persistent transaction state:** PostgreSQL stores transaction details, processing status, and timestamps.
- **Asynchronous processing:** Redis and RQ run transaction processing outside the API request path. Processing includes
  a configurable 30-second delay to simulate an external operation.
- **Duplicate prevention:** `transaction_id` identifies a transaction uniquely, so repeated webhook requests do not
  create duplicate transaction records.
- **Processing ownership:** Conditional database updates and a unique processing token help prevent an outdated worker
  attempt from overwriting the state produced by a newer attempt.
- **Recovery process:** A dedicated service periodically looks for stale `PROCESSING` transactions and old `RECEIVED`
  transactions that may need to be scheduled again.
- **Input validation:** Pydantic validates webhook request payloads.
- **Automated tests:** Tests cover health checks, validation, webhook responses, transaction idempotency, worker
  idempotency, and recovery behavior.

## Tech Stack

- Python 3.12 (Docker image)
- FastAPI and Uvicorn
- PostgreSQL and SQLAlchemy
- Redis and RQ
- Pydantic and Pydantic Settings
- Docker and Docker Compose
- Pytest

## Architecture

```text
Client
  |
  v
FastAPI API
  |-- persist transaction --> PostgreSQL
  |-- enqueue job ----------> Redis / RQ
                                  |
                                  v
                              RQ Worker
                                  |
                                  v
                              PostgreSQL

Recovery Service ---> finds stale RECEIVED / PROCESSING transactions
       |              and schedules eligible work through Redis / RQ
       +------------------------------------------------------------>
```

The API persists the transaction before enqueueing its RQ job. The worker atomically claims a transaction by changing
its status from `RECEIVED` to `PROCESSING`. Each processing attempt gets a unique token, and the worker completes the
transaction only if that token still matches the database record.

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
│   ├── test_transaction_idempotency.py
│   ├── test_webhook_response.py
│   ├── test_webhook_validation.py
│   ├── test_worker_idempotency.py
│   ├── test_worker_recovery.py
│   ├── test_received_recovery.py
│   └── test_recovery_enqueue.py
├── Dockerfile
├── docker-compose.yml
├── init_db.py
├── requirements.txt
├── .env.example
└── README.md
```

## Prerequisites

- Docker Desktop with Docker Compose
- Git
- Python 3.12 or a compatible Python version to run tests locally

## Run Locally with Docker Compose

### 1. Clone the repository

```bash
git clone <PUBLIC_GITHUB_REPOSITORY_URL>
cd transaction-webhook-service
```

Replace the placeholder with the repository URL after publishing it.

### 2. Configure environment variables

```bash
cp .env.example .env
```

Review `.env` before starting. The example file is for local development only; do not use its credentials in a public
deployment. Keep `.env` out of version control.

The default local ports are:

| Service    | Host port | Container port |
|------------|----------:|---------------:|
| API        |      8000 |           8000 |
| PostgreSQL |      5435 |           5432 |
| Redis      |      6379 |           6379 |

### 3. Start the services

```bash
docker compose --env-file .env up --build -d
```

Create the database tables:

```bash
docker compose --env-file .env exec api python init_db.py
```

Check service status:

```bash
docker compose --env-file .env ps
```

PostgreSQL and Redis should report as healthy. The API, worker, and recovery service should be running.

### 4. Check the health endpoint

```bash
curl -i http://localhost:8000/
```

Example response (the timestamp will vary):

```json
{
  "status": "HEALTHY",
  "current_time": "2026-10-21T16:00:00+00:00"
}
```

## API Endpoints

### Health check

`GET /`

Returns the service health status and current UTC timestamp.

### Submit a transaction webhook

`POST /v1/webhooks/transactions`

Example request:

```bash
curl -i -X POST http://localhost:8000/v1/webhooks/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "txn_001",
    "source_account": "account_a",
    "destination_account": "account_b",
    "amount": 125.50,
    "currency": "INR"
  }'
```

The endpoint returns `202 Accepted` when the transaction has been saved and its job scheduled. Example response:

```json
{
  "message": "Transaction webhook received",
  "transaction_id": "txn_001",
  "status": "RECEIVED"
}
```

If the transaction is saved but job scheduling fails, the endpoint returns `503 Service Unavailable`; the response
indicates that the transaction was saved and that scheduling should be retried. A repeated `transaction_id` reuses the
existing transaction record rather than creating a second one.

### Retrieve transaction status

`GET /v1/transactions/{transaction_id}`

Example:

```bash
curl -i http://localhost:8000/v1/transactions/txn_001
```

The response contains the transaction ID, source and destination accounts, amount, currency, status, creation timestamp,
and processing completion timestamp. A missing transaction returns `404 Not Found`.

The transaction lifecycle includes these statuses:

- `RECEIVED` — transaction persisted and awaiting processing
- `PROCESSING` — a worker has claimed the transaction
- `PROCESSED` — processing completed

## Background Processing and Recovery

The RQ worker simulates an external operation using the configured processing delay (30 seconds by default). It first
atomically claims a transaction only if its current status is `RECEIVED`. The worker's final update checks both the
`PROCESSING` status and the processing token for that attempt.

The recovery service runs separately and periodically:

- Resets stale `PROCESSING` transactions so they can be attempted again.
- Finds older `RECEIVED` transactions that may not have been successfully scheduled.
- Attempts to enqueue eligible transactions while checking the status of existing RQ jobs.

Relevant settings are configurable through environment variables, including `PROCESSING_DELAY_SECONDS`,
`RECOVERY_INTERVAL_SECONDS`, and `STALE_TRANSACTION_SECONDS`.

## Running Tests

The tests use a separate PostgreSQL database named `transactions_test`. Do not point the test configuration at a
production database.

### 1. Start PostgreSQL

```bash
docker compose --env-file .env up -d postgres
```

### 2. Create the test database if it does not already exist

```bash
docker compose --env-file .env exec postgres \
  psql -U postgres -d postgres \
  -c "CREATE DATABASE transactions_test;"
```

If PostgreSQL reports that the database already exists, you can continue. The test fixture currently connects to:

```text
postgresql+psycopg://postgres:postgres@127.0.0.1:5435/transactions_test
```

If you change local credentials or ports, update the connection URL in `tests/conftest.py` accordingly.

### 3. Install dependencies in your local Python environment

```bash
python3 -m pip install -r requirements.txt
```

### 4. Run the suite

```bash
python3 -m pytest -q
```

The latest reported local run completed with **16 tests passing**. Run the suite again after changes to confirm the
current result.

## Technical Choices

### FastAPI

Provides request validation and a concise API implementation for webhook submission, health checks, and transaction
lookup.

### PostgreSQL and SQLAlchemy

Provide persistent transaction storage, a unique transaction identifier, and conditional updates for coordinating worker
state transitions.

### Redis and RQ

Separate background processing from request handling so the API does not wait for the simulated 30-second operation to
finish.

### Processing tokens

Help prevent a stale worker attempt from writing a completion result after another attempt has taken ownership of the
transaction.

### Docker Compose

Runs the API, worker, recovery process, PostgreSQL, and Redis in a repeatable local environment.

## Reliability Considerations and Limitations

The transaction is committed to PostgreSQL before the API enqueues the corresponding RQ job. PostgreSQL persistence and
Redis enqueueing are not a single atomic operation. The API reports a scheduling failure if enqueueing fails, and the
recovery service periodically looks for transactions that may need to be scheduled again. These mechanisms reduce the
risk of stranded work, but they are not equivalent to an atomic delivery guarantee.

The processing token protects database state from stale worker attempts. If the simulated operation is replaced by a
real external side effect, that external system may also need its own idempotency key or deduplication mechanism; a
database token alone cannot undo an external side effect.

The application has been run locally with Docker Compose and the automated test suite. Public deployment, latency under
load, and behavior during real Redis or worker outages should be verified separately before describing the service as
production-ready.

## Stop the Services

```bash
docker compose --env-file .env down
```

This stops the containers and preserves the named PostgreSQL volume.

To also delete the local database volume, use the following only if you intentionally want to remove its data:

```bash
docker compose --env-file .env down -v
```

## Deployment

**Public API URL:** TODO — add the verified deployed endpoint.

After deployment, document the hosting platform, required environment variables, and any public testing instructions
here. Do not publish database credentials, Redis URLs containing secrets, or other private configuration values.
