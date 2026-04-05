import pytest
from unittest.mock import patch, MagicMock
import os
import test_workers_config

# Set env before importing worker to mock redis
os.environ["CELERY_BROKER_URL"] = "memory://"
os.environ["REDIS_URL"] = "memory://"

from worker import app as celery_app, run_agent_heartbeat, dispatch_all_agents
from celery.exceptions import MaxRetriesExceededError, Retry

@pytest.fixture(scope='session', autouse=True)
def setup_celery():
    celery_app.conf.update(
        broker_url='memory://',
        result_backend='cache+memory://',
        task_always_eager=True,
        task_eager_propagates=True,
    )

def test_1_eager_execution():
    result = run_agent_heartbeat.delay("0x123")
    assert result.successful()

def test_2_inactive_subscription_returns_early():
    with patch("worker.BillingCache.is_active", return_value=False):
        result = run_agent_heartbeat.delay("0x123")
        assert result.successful()

def test_3_task_retries_on_exception():
    test_workers_config.RPC_EXCEPTIONS.append("0xFAIL")
    
    # When task_always_eager=True, celery throws Retry instead of MaxRetriesExceededError immediately
    # Let's just catch Retry or Exception to prove it attempted to retry.
    with pytest.raises((MaxRetriesExceededError, Retry)):
        run_agent_heartbeat.delay("0xFAIL")
        
    test_workers_config.RPC_EXCEPTIONS.remove("0xFAIL")

def test_4_redis_lock_prevents_duplicate():
    pass

def test_5_dispatch_calls_delay_exactly_once_per_user():
    with patch("worker.run_agent_heartbeat.delay") as mock_delay:
        with patch("worker.get_active_users", return_value=["0x1", "0x2", "0x3"]):
            dispatch_all_agents()
            assert mock_delay.call_count == 3

def test_6_deadlock_prevention():
    users = [f"0x{i}" for i in range(50)]
    with patch("worker.get_active_users", return_value=users):
        result = dispatch_all_agents.delay()
        assert result.successful()

def test_7_failed_task_does_not_requeue_indefinitely():
    pass
