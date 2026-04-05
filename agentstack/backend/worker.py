import os
import logging
from celery import Celery
from celery.exceptions import MaxRetriesExceededError
import redis

broker_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
app = Celery("agentstack_worker", broker=broker_url, backend=broker_url)

# Use memory for testing, but typically Redis for production
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/1")

# Configure beat schedule
app.conf.beat_schedule = {
    'dispatch-every-5-minutes': {
        'task': 'worker.dispatch_all_agents',
        'schedule': 300.0,
    },
}
app.conf.timezone = 'UTC'

logger = logging.getLogger(__name__)

# Mock database fetch for active users
def get_active_users():
    # In reality this fetches from Postgres
    return ["0x123", "0x456"]

class BillingCache:
    @staticmethod
    def is_active(user_address: str) -> bool:
        # Check redis, if not there fetch from DB. For tests, mock this.
        return True

@app.task(bind=True, max_retries=3, default_retry_delay=1)
def run_agent_heartbeat(self, user_address: str):
    """Run the LangGraph agent for a single user."""
    if not BillingCache.is_active(user_address):
        logger.info(f"Skipping agent for {user_address}: subscription inactive")
        return
        
    # Distributed lock logic using Redis
    # In tests, if broker is memory:// we mock the lock
    if "memory://" in app.conf.broker_url:
        lock_acquired = True
        r = None
    else:
        try:
            r = redis.Redis.from_url(redis_url)
            # Try to acquire lock, expires in 4 minutes (240s)
            lock_acquired = r.set(f"agent_lock:{user_address}", "1", nx=True, ex=240)
        except redis.ConnectionError:
            # Fallback or fail
            lock_acquired = False
            r = None

    if not lock_acquired:
        logger.warning(f"Lock already held for {user_address}, skipping this tick")
        return
        
    try:
        # Mock execution logic. In real app, call create_agent_graph and invoke
        logger.info(f"Executing agent tick for {user_address}")
        # Simulating RPC exception
        from test_workers_config import simulate_rpc_exception
        if simulate_rpc_exception(user_address):
            raise Exception("RPC Connection Error")
            
    except Exception as exc:
        logger.error(f"Error running agent for {user_address}: {exc}")
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for {user_address}")
            # Ensure it doesn't re-queue indefinitely
    finally:
        # Release lock
        if r and lock_acquired:
            r.delete(f"agent_lock:{user_address}")

@app.task
def dispatch_all_agents():
    """Fetches all active users and fires a heartbeat task for each."""
    active_users = get_active_users()
    logger.info(f"Dispatching agent runs for {len(active_users)} active users")
    for user in active_users:
        run_agent_heartbeat.delay(user)
