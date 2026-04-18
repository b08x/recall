import logging
import os
import time
from datetime import datetime
from contextlib import contextmanager

log_file = "recall.log"

# Central logger for the recall package
logger = logging.getLogger("recall")
logger.setLevel(logging.DEBUG)

# Remove existing handlers to avoid duplicates
if logger.handlers:
    logger.handlers.clear()

# Create a file handler for debug logs
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)

# Create a formatter with timing
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Add the handler to the logger
logger.addHandler(file_handler)

def debug(msg: str):
    logger.debug(msg)

def info(msg: str):
    logger.info(msg)

def error(msg: str):
    logger.error(msg)

@contextmanager
def step(name: str, detail: str = None):
    """Context manager for timing execution steps."""
    start = time.perf_counter()
    debug(f"STEP_START | {name}" + (f" | {detail}" if detail else ""))
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        debug(f"STEP_COMPLETE | {name} | {elapsed:.3f}s")

def log_metric(name: str, value: float, unit: str = "count"):
    """Log a metric value."""
    debug(f"METRIC | {name} | {value} | {unit}")

def log_data(name: str, data: dict):
    """Log structured data as JSON."""
    import json
    debug(f"DATA | {name} | {json.dumps(data, default=str)}")
