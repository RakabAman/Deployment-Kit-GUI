"""
logger.py - Central logging setup for console and file output.
"""

import logging
import os
import sys

def setup_logging(base_dir):
    """Configure logging to write to console and to a file."""
    log_file = os.path.join(base_dir, 'deployment.log')

    # Create a logger
    logger = logging.getLogger('DeploymentKit')
    logger.setLevel(logging.DEBUG)

    # Remove any existing handlers to avoid duplicates
    if logger.hasHandlers():
        logger.handlers.clear()

    # Formatter for all messages
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler (overwrites on each run)
    file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler with UTF-8 encoding to support emojis
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    # Force UTF-8 encoding for console output
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    logger.addHandler(console_handler)

    # Also log the starting directory
    logger.info(f"Logging initialized. Log file: {log_file}")
    logger.info(f"Base directory: {base_dir}")

    return logger