import time
import threading
from functools import wraps
from typing import Callable, Any, Optional, Dict
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
    """Thread-safe rate limiter using time.sleep."""
    
    def __init__(self, requests_per_minute: int, name: str = "default"):
        self.name = name
        self.interval = 60.0 / requests_per_minute if requests_per_minute > 0 else 0
        self.last_call = 0.0
        self._lock = threading.Lock()

    def wait(self):
        """Wait if necessary before the next call. Thread-safe."""
        if self.interval == 0:
            return
            
        with self._lock:
            now = time.time()
            elapsed = now - self.last_call
            wait_time = self.interval - elapsed
            
            if wait_time > 0:
                debug(f"RateLimiter[{self.name}] waiting {wait_time:.2f}s")
                time.sleep(wait_time)
                
            self.last_call = time.time()

class RateLimiterGroup:
    """Manages a collection of named RateLimiter instances."""
    
    def __init__(self, default_rpm: int = 20):
        self.default_rpm = default_rpm
        self._limiters: Dict[str, RateLimiter] = {
            "default": RateLimiter(default_rpm, "default")
        }
        self._lock = threading.Lock()

    def get(self, name: str) -> RateLimiter:
        """Get or create a named rate limiter."""
        with self._lock:
            if name not in self._limiters:
                debug(f"Creating new RateLimiter for provider: {name} ({self.default_rpm} RPM)")
                self._limiters[name] = RateLimiter(self.default_rpm, name)
            return self._limiters[name]

# Global group instance
_limiter_group = RateLimiterGroup()

def get_limiter(name: str = "default") -> RateLimiter:
    return _limiter_group.get(name)

def get_default_limiter() -> RateLimiter:
    """Alias for get_limiter('default')"""
    return get_limiter("default")

def set_default_limiter(limiter: RateLimiter):
    """Deprecated: Use set_global_rpm instead or manage RateLimiterGroup."""
    pass

def set_global_rpm(rpm: int):
    global _limiter_group
    _limiter_group = RateLimiterGroup(default_rpm=rpm)

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
