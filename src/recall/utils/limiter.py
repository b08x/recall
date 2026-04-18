import time
from functools import wraps
from typing import Callable, Any, Optional
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
import logging
from recall.logging import debug, info, error

logger = logging.getLogger(__name__)

class RateLimiter:
    """Simple rate limiter using time.sleep."""
    
    def __init__(self, requests_per_minute: int):
        self.interval = 60.0 / requests_per_minute if requests_per_minute > 0 else 0
        self.last_call = 0.0

    def wait(self):
        """Wait if necessary before the next call."""
        if self.interval == 0:
            return
            
        now = time.time()
        elapsed = now - self.last_call
        wait_time = self.interval - elapsed
        
        if wait_time > 0:
            time.sleep(wait_time)
            
        self.last_call = time.time()

# Global default limiter instance, will be configured by MultiSourceCorrelator
_default_limiter = RateLimiter(requests_per_minute=20)

def get_default_limiter() -> RateLimiter:
    return _default_limiter

def set_default_limiter(limiter: RateLimiter):
    global _default_limiter
    _default_limiter = limiter

def get_retry_decorator(
    max_attempts: int = 5,
    min_wait: float = 1.0,
    max_wait: float = 60.0,
    exceptions: tuple = (Exception,)
) -> Callable:
    """
    Returns a tenacity retry decorator configured with exponential backoff.
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=min_wait, max=max_wait),
        retry=retry_if_exception_type(exceptions),
        before_sleep=before_sleep_log(logger, logging.INFO),
        reraise=True
    )

def rate_limited(limiter: RateLimiter):
    """Decorator to apply rate limiting to a function."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            limiter.wait()
            return func(*args, **kwargs)
        return wrapper
    return decorator
