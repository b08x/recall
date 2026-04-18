import logging
import os
from datetime import datetime

# Central logger for the recall package
logger = logging.getLogger("recall")
logger.setLevel(logging.DEBUG)

# Create a file handler for debug logs
log_file = "recall.log"
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)

# Create a formatter
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
