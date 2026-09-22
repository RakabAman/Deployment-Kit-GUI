"""
logger.py - Central logging setup for console and file output.

Each run gets its own timestamped log file under <base_dir>/logs/, so
past sessions stay available for comparison/troubleshooting instead of
being wiped by the next launch. A retention limit prunes old sessions
so the logs folder doesn't grow forever.
"""

import logging
import os
import sys
import glob
import datetime

# Keep at most this many session log files; oldest are deleted first.
MAX_LOG_SESSIONS = 20

LOG_FILENAME_PREFIX = 'session_'
LOG_FILENAME_SUFFIX = '.log'


def _prune_old_sessions(logs_dir, keep=MAX_LOG_SESSIONS):
    """Delete oldest session log files beyond the retention limit."""
    try:
        pattern = os.path.join(logs_dir, f'{LOG_FILENAME_PREFIX}*{LOG_FILENAME_SUFFIX}')
        files = sorted(glob.glob(pattern), key=os.path.getmtime)
        excess = len(files) - keep
        for old_file in files[:max(0, excess)]:
            try:
                os.remove(old_file)
            except OSError:
                pass  # best-effort cleanup; a locked/in-use file is not fatal
    except OSError:
        pass


def setup_logging(base_dir, max_sessions=MAX_LOG_SESSIONS):
    """Configure logging to write to console and to a fresh, timestamped
    per-session file. Returns the logger; the active log file path is
    available as logger.log_file_path for anything that wants to show it
    (e.g. a report generator or an "Open log folder" button)."""
    logs_dir = os.path.join(base_dir, 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    _prune_old_sessions(logs_dir, keep=max_sessions)

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    log_file = os.path.join(logs_dir, f'{LOG_FILENAME_PREFIX}{timestamp}{LOG_FILENAME_SUFFIX}')

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

    # File handler - each session gets its own file (mode='w' is safe here
    # since the filename itself is unique per run; nothing is overwritten
    # across sessions anymore).
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

    # Make the active log path discoverable to other modules (e.g. a
    # post-run report that wants to link/attach it, or a "View Log" button).
    logger.log_file_path = log_file
    logger.logs_dir = logs_dir

    # Also log the starting directory
    logger.info(f"Logging initialized. Session log file: {log_file}")
    logger.info(f"Base directory: {base_dir}")
    logger.info(f"Retention: keeping the last {max_sessions} session log(s)")

    return logger
