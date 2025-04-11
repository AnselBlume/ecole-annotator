import redis
from redis.cluster import RedisCluster
from redis.exceptions import LockError
import time
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Redis configuration
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

# Redis lock timeout in seconds
LOCK_TIMEOUT = 300  # 5 minutes
LOCK_RETRY_TIMES = 3  # Number of times to retry acquiring a lock
LOCK_RETRY_DELAY = 1  # Delay between retries in seconds
LOCK_BLOCKING_TIMEOUT = 30  # 30 seconds

# Redis client for concurrency-safe queueing
try:
    # Try to use Redis Cluster for better locking support
    r = RedisCluster(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        skip_full_coverage_check=True
    )
    logger.info('Connected to Redis Cluster')
except Exception as e:
    # Fall back to regular Redis if cluster is not available
    logger.warning(f'Failed to connect to Redis Cluster: {e}. Falling back to regular Redis.')
    r = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True
    )

class LockAcquisitionError(Exception):
    '''Exception raised when a lock cannot be acquired after retries.'''
    pass

def acquire_lock(lock_name: str, with_retry: bool = False, blocking: bool = True) -> Optional[Any]:
    '''
    Acquire a Redis lock. If with_retry is True, the lock will be acquired with retry logic. If blocking is True, the lock will be acquired blocking until it is acquired.
    Only one of with_retry or blocking can be True.

    Args:
        lock_name: The name of the lock to acquire
        with_retry: Whether to retry acquiring the lock
        blocking: Whether to block until the lock is acquired

    Returns:
        The lock object if acquired, None otherwise

    Raises:
        LockAcquisitionError: If the lock cannot be acquired after retries
    '''
    assert with_retry ^ blocking, 'with_retry and blocking must be mutually exclusive'

    if with_retry:
        return acquire_lock_with_retry(lock_name)
    else:
        return acquire_lock_blocking(lock_name)

def acquire_lock_blocking(lock_name: str, timeout: int = LOCK_TIMEOUT, blocking_timeout: int = LOCK_BLOCKING_TIMEOUT) -> Optional[Any]:
    '''Acquire a Redis lock blocking until it is acquired.

    Args:
        lock_name: The name of the lock to acquire
        timeout: The timeout for the lock in seconds
    '''
    try:
        lock = r.lock(lock_name, timeout=timeout)
        if lock.acquire(blocking=True, blocking_timeout=blocking_timeout):
            return lock
    except LockError as e:
        logger.error(f'Error acquiring lock {lock_name}: {e}')
        return None
    except Exception as e:
        logger.error(f'Unexpected error acquiring lock {lock_name}: {e}')
        return None

    raise LockAcquisitionError(f'Failed to acquire lock {lock_name} after {timeout} seconds')

def acquire_lock_with_retry(lock_name: str, timeout: int = LOCK_TIMEOUT, retry_times: int = LOCK_RETRY_TIMES, retry_delay: float = LOCK_RETRY_DELAY) -> Optional[Any]:
    '''Acquire a Redis lock with retry logic.

    Args:
        lock_name: The name of the lock to acquire
        timeout: The timeout for the lock in seconds
        retry_times: The number of times to retry acquiring the lock
        retry_delay: The delay between retries in seconds

    Returns:
        The lock object if acquired, None otherwise

    Raises:
        LockAcquisitionError: If the lock cannot be acquired after retries
    '''
    for attempt in range(retry_times):
        try:
            # Try to acquire the lock
            lock = r.lock(lock_name, timeout=timeout)
            if lock.acquire(blocking=False):
                logger.debug(f'Acquired lock {lock_name} on attempt {attempt + 1}')
                return lock
        except LockError as e:
            logger.warning(f'Lock error on attempt {attempt + 1}: {e}')
        except Exception as e:
            logger.error(f'Unexpected error acquiring lock {lock_name}: {e}')

        # Wait before retrying
        if attempt < retry_times - 1:
            time.sleep(retry_delay)

    # If we get here, we failed to acquire the lock after all retries
    raise LockAcquisitionError(f'Failed to acquire lock {lock_name} after {retry_times} attempts')

def release_lock(lock: Any) -> None:
    '''Release a Redis lock.

    Args:
        lock: The lock object to release
    '''
    try:
        lock.release()
    except Exception as e:
       logger.error(f'Error releasing lock: {e}')