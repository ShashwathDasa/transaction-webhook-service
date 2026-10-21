"""Configure the Redis connection and transaction processing queue."""

from redis import Redis
from rq import Queue

from app.config import settings

redis_connection = Redis.from_url(settings.redis_url)

transaction_queue = Queue(settings.transaction_queue_name, connection=redis_connection)
