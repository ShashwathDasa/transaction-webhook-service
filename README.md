# Transaction Webhook Service

A Python backend service that accepts transaction webhooks, acknowledges requests quickly, and processes transactions
asynchronously. Built with FastAPI, PostgreSQL, Redis, and RQ.

## Features

- **Fast webhook acknowledgement:** Returns `202 Accepted` after accepting and persisting a transaction.
- **Persistent storage:** Stores transaction details, status, and timestamps in PostgreSQL.
- **Asynchronous processing:** Uses Redis and RQ to process transactions in the background with a 30-second delay.
- **Idempotency:** Uses `transaction_id` as the primary key to prevent duplicate transaction records.
- **Processing ownership:** Uses unique processing tokens to prevent an outdated worker attempt from overwriting a newer
  attempt's state.
- **Stale-job recovery:** Includes a function to reset transactions that remain in `PROCESSING` beyond a configurable
  threshold.
- **Input validation:** Validates webhook payloads using Pydantic.
- **Containerized setup:** Runs the API, worker, PostgreSQL, and Redis using Docker Compose.
- **Automated tests:** Covers health checks, input validation, webhook responses, idempotency, and worker recovery
  behavior.

## Tech Stack

- Python 3.12
- FastAPI and Uvicorn
- PostgreSQL and SQLAlchemy
- Redis and RQ
- Pydantic and Pydantic Settings
- Docker and Docker Compose
- Pytest and HTTPX

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
│   └── services/
├── worker/
│   └── tasks.py
├── tests/
│   ├── conftest.py
│   ├── test_health.py
│   ├── test_transaction_idempotency.py
│   ├── test_webhook_response.py
│   ├── test_webhook_validation.py
│   ├── test_worker_idempotency.py
│   └── test_worker_recovery.py
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
- Python 3.12 or compatible Python version for running tests locally

## Setup and Run

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd transaction-webhook-service
```

Replace the repository URL with the public GitHub repository URL.

### 2. Configure environment variables

Create a local environment file from the example:

```bash
cp .env.example .env
```

Review `.env` before starting the application. Ensure the PostgreSQL username, password, database name, and connection
URLs are consistent.

The Docker Compose configuration uses these ports:

| Service    | Host port | Container port |
|------------|----------:|---------------:|
| API        |      8000 |           8000 |
| PostgreSQL |      5435 |           5432 |
| Redis      |      6379 |           6379 |

The PostgreSQL and Redis service names are used for connections between containers.

### 3. Start the services

```bash
docker compose --env-file .env up --build -d
```

Check the services:

```bash
docker compose --env-file .env ps
```

PostgreSQL and Redis should become healthy, and the API and worker should be running.

### 4. Initialize the database

The application tables can be created using:

```bash
docker compose --env-file .env exec api python init_db.py
```

This command is intended for initial setup. It uses SQLAlchemy metadata to create missing tables.

### 5. Verify the health endpoint

```bash
curl -i http://localhost:8000/
```

Expected response:

```json
{
  "status": "HEALTHY",
  "current_time": "2026-10-21T16:00:00+00:00"
}
```

The timestamp is an example; the actual value is generated at request time.

## API Endpoints

### 1. Health Check

**`GET /`**

Returns the service health status and current timestamp.

### 2. Submit a Transaction Webhook

**`POST /v1/webhooks/transactions`**

Request body:

```json
{
  "transaction_id": "txn_001",
  "source_account": "account_a",
  "destination_account": "account_b",
  "amount": 125.50,
  "currency": "INR"
}
```

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

Expected response: `202 Accepted`.

```json
{
  "message": "Transaction webhook received",
  "transaction_id": "txn_001",
  "status": "RECEIVED"
}
```

The API persists the transaction before returning and enqueues background processing through RQ.

Submitting the same `transaction_id` does not create a second transaction record.

### 3. Retrieve Transaction Status

**`GET /v1/transactions/{transaction_id}`**

Example:

```bash
curl -s http://localhost:8000/v1/transactions/txn_001
```

The response includes transaction details, processing status, creation timestamp, and processing timestamp.

The processing states used by the service include:

- `RECEIVED`
- `PROCESSING`
- `PROCESSED`

The `processed_at` field is populated when processing completes.

## Background Processing

The worker processes transactions asynchronously and includes a 30-second delay to simulate an external API call.

The worker attempts to claim a transaction by conditionally changing its state from `RECEIVED` to `PROCESSING`. A unique
processing token is assigned to each attempt. The final database update succeeds only if the transaction is still
`PROCESSING` and the token matches the current attempt.

This protects transaction state when an old worker attempt overlaps with a newer attempt.

## Stale-Job Recovery

The `recover_stale_transactions` function resets transactions that have remained in `PROCESSING` beyond a configurable
threshold.

**Current limitation:** The recovery function is implemented and tested, but periodic recovery is not automatically
scheduled in the current Docker Compose configuration. It must be invoked or scheduled separately.

## Running Tests

The automated tests use a separate PostgreSQL test database. They should not run against production data.

### 1. Ensure PostgreSQL is running

Start the local services:

```bash
docker compose --env-file .env up -d postgres
```

### 2. Create the test database

If the test database does not already exist, create it:

```bash
docker compose --env-file .env exec postgres \
  psql -U postgres -d postgres \
  -c "CREATE DATABASE transactions_test;"
```

If the database already exists, PostgreSQL will report that it exists; you do not need to recreate it.

The current test fixture connects to:

```text
postgresql+psycopg://postgres:postgres@127.0.0.1:5435/transactions_test
```

If you use different local credentials or ports, update `tests/conftest.py` accordingly.

### 3. Install dependencies

Create and activate a virtual environment if needed, then run:

```bash
python -m pip install -r requirements.txt
```

### 4. Run the tests

From the project root:

```bash
python -m pytest -q
```

The current test suite has passed all 10 tests in the development environment.

## Technical Choices

### FastAPI

FastAPI provides request validation, clear endpoint definitions, and an efficient way to build the webhook API.

### PostgreSQL

PostgreSQL provides durable storage and enforces uniqueness through the transaction primary key. The service uses
conditional database updates to coordinate processing state.

### Redis and RQ

Redis and RQ allow background processing to run separately from the request-handling API, so the API does not wait for
the simulated 30-second operation.

### Processing tokens

Unique processing tokens help prevent stale worker attempts from overwriting the database state of a newer attempt.

### Docker Compose

Docker Compose provides a repeatable local environment for running the API, worker, database, and queue.

## Reliability Considerations and Limitations

The service implements persistent transaction records, duplicate prevention, conditional processing claims, and
stale-processing recovery logic.

However, PostgreSQL persistence and Redis job enqueueing are not one atomic operation. If the transaction is committed
to PostgreSQL but enqueueing fails, the transaction can remain unprocessed unless a retry or recovery path successfully
schedules it.

A transactional outbox or equivalent durable scheduling mechanism would strengthen delivery guarantees. The current
recovery function is not automatically scheduled.

The service has been validated locally using Docker Compose and automated tests. Public deployment and production
failure-recovery behavior must be verified separately.

## Stopping the Services

```bash
docker compose --env-file .env down
```

This stops the containers while preserving the named PostgreSQL volume.

To delete the persisted local database volume as well, use the following only when you intentionally want to remove that
data:

```bash
docker compose --env-file .env down -v
```

## Deployment

The application is intended to be deployed with a publicly accessible API endpoint. A deployment must run the API,
background worker, PostgreSQL, and Redis with correctly configured connection URLs.

The public endpoint and deployment instructions should be added here after deployment has been completed and verified.
