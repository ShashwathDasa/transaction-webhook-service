from unittest.mock import Mock

from worker import recovery


def test_enqueues_received_transaction_when_no_job_exists(monkeypatch):
    """A missing queue job should be enqueued for recovery."""
    queue = Mock()
    queue.fetch_job.return_value = None
    monkeypatch.setattr(recovery, "transaction_queue", queue)

    result = recovery.enqueue_if_not_active("received_test_001")

    assert result is True
    queue.enqueue.assert_called_once()
    assert queue.enqueue.call_args.kwargs["job_id"] == "transaction-received_test_001"


def test_does_not_enqueue_when_job_is_already_active(monkeypatch):
    """An active job should not be scheduled a second time."""
    queue = Mock()
    job = Mock()
    job.get_status.return_value = "queued"
    queue.fetch_job.return_value = job
    monkeypatch.setattr(recovery, "transaction_queue", queue)

    result = recovery.enqueue_if_not_active("received_test_002")

    assert result is False
    queue.enqueue.assert_not_called()


def test_enqueue_can_retry_after_temporary_failure(monkeypatch):
    """A later recovery attempt can enqueue after a temporary failure."""
    queue = Mock()
    queue.fetch_job.return_value = None
    queue.enqueue.side_effect = [ConnectionError("Redis temporarily unavailable"), Mock()]

    monkeypatch.setattr(recovery, "transaction_queue", queue)

    # First attempt: Redis is unavailable.
    try:
        recovery.enqueue_if_not_active("received_retry_test")
        assert False, "Expected the first enqueue attempt to fail"
    except ConnectionError:
        pass

    # Second attempt: Redis is available again.
    result = recovery.enqueue_if_not_active("received_retry_test")

    assert result is True
    assert queue.enqueue.call_count == 2


def test_recovery_continues_after_enqueue_failure(monkeypatch):
    """A failed recovery cycle must not stop subsequent cycles."""
    queue = Mock()
    queue.fetch_job.return_value = None
    queue.enqueue.side_effect = [ConnectionError("Redis temporarily unavailable"), Mock()]
    monkeypatch.setattr(recovery, "transaction_queue", queue)

    monkeypatch.setattr(recovery, "recover_stale_transaction_ids", lambda _: [])
    monkeypatch.setattr(recovery, "get_stale_received_transaction_ids", lambda _: ["received_retry_test"])
    monkeypatch.setattr(recovery.settings, "stale_transaction_seconds", 120)
    monkeypatch.setattr(recovery.settings, "recovery_interval_seconds", 0)

    sleep_calls = 0

    def stop_after_second_cycle(_):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(recovery.time, "sleep", stop_after_second_cycle)

    try:
        recovery.run_recovery()
    except KeyboardInterrupt:
        pass

    assert queue.enqueue.call_count == 2
    assert sleep_calls == 2


def test_recovery_requeues_when_original_job_is_started(monkeypatch):
    """A started RQ job must not block recovery of a RECEIVED transaction."""
    queue = Mock()
    job = Mock()
    job.get_status.return_value = "started"
    queue.fetch_job.return_value = job
    monkeypatch.setattr(recovery, "transaction_queue", queue)

    result = recovery.enqueue_if_not_active("received_stale_test")

    assert result is True
    queue.enqueue.assert_called_once()
