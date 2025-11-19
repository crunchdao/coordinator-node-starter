import logging
import sys


def setup_logging(level: int = logging.INFO):
    """Configures logging for the application."""
    logger = logging.getLogger()  # Root logger
    logger.setLevel(level)  # Set global log level only using the provided level

    # Clear existing handlers before adding a new one
    while logger.hasHandlers():
        logger.removeHandler(logger.handlers[0])

    # Create a new StreamHandler with timestamp formatting
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname).1s | %(name)-30.30s | %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
