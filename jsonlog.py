import logging
import json
import os
from pythonjsonlogger import jsonlogger

default_log_level = os.getenv("APP_LOG_LEVEL", "INFO").upper()

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record['name'] = record.name
        log_record['level'] = record.levelname
        log_record['timestamp'] = self.formatTime(record, self.datefmt)
        log_record['message'] = record.getMessage()

def setup_logger(name, level=logging._nameToLevel.get(default_log_level, logging.INFO)):
    """
    Sets up a logger with JSON formatting for production use.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Remove all existing handlers
    logger.handlers.clear()

    # Create a stream handler
    handler = logging.StreamHandler()
    formatter = CustomJsonFormatter('%(timestamp)s %(level)s %(message)s')
    handler.setFormatter(formatter)

    # Add the custom handler to the logger
    logger.addHandler(handler)
    logger.propagate = False

    return logger
