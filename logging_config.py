"""
Logging configuration for AP Automation application.

This module sets up centralized logging with different levels and output options.
Use this instead of print statements for better debugging and production monitoring.

Usage:
    from utils.logging_config import setup_logging, get_logger

    # In main.py:
    setup_logging()  # Sets up logging for entire application

    # In any module:
    logger = get_logger(__name__)
    logger.debug("Detailed debugging info")  # Only shows in debug mode
    logger.info("General information")       # Shows in normal operation
    logger.warning("Something unusual")      # Always shows (important)
    logger.error("Something broke")          # Always shows (critical)
"""

import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler


def setup_logging(level=logging.INFO, console_output=True, file_output=True, debug_mode=False):
    """
    Configure logging for the entire application.

    Args:
        level: Minimum logging level (logging.DEBUG, INFO, WARNING, ERROR)
        console_output: Whether to show logs in console/terminal
        file_output: Whether to save logs to files
        debug_mode: If True, enables verbose debug logging
    """

    # Clear any existing handlers to avoid duplicates
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # Set level based on debug mode
    if debug_mode:
        level = logging.DEBUG

    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )

    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )

    handlers = []

    # Console handler (what you see in terminal)
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(simple_formatter)
        handlers.append(console_handler)

    # File handlers (permanent record)
    if file_output:
        # Create logs directory if it doesn't exist
        log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
        os.makedirs(log_dir, exist_ok=True)

        # Main application log (rotates when it gets too big)
        main_log_file = os.path.join(log_dir, 'ap_automation.log')
        file_handler = RotatingFileHandler(
            main_log_file,
            maxBytes=10*1024*1024,  # 10MB files
            backupCount=5           # Keep 5 old files
        )
        file_handler.setLevel(logging.DEBUG)  # File gets everything
        file_handler.setFormatter(detailed_formatter)
        handlers.append(file_handler)

        # Error-only log (for quick problem identification)
        error_log_file = os.path.join(log_dir, 'errors.log')
        error_handler = RotatingFileHandler(
            error_log_file,
            maxBytes=5*1024*1024,   # 5MB files
            backupCount=3           # Keep 3 old files
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        handlers.append(error_handler)

    # Configure root logger
    logging.basicConfig(
        level=level,
        handlers=handlers
    )

    # Log the setup
    setup_logger = get_logger('logging_setup')
    setup_logger.info("Logging system initialized")
    setup_logger.info(f"Console output: {console_output}")
    setup_logger.info(f"File output: {file_output}")
    setup_logger.info(f"Log level: {logging.getLevelName(level)}")
    if debug_mode:
        setup_logger.info("Debug mode enabled - verbose logging active")


def get_logger(name):
    """
    Get a logger for a specific module.

    Args:
        name: Usually __name__ from the calling module

    Returns:
        Logger instance configured with the application settings

    Example:
        logger = get_logger(__name__)
        logger.info("This is how you log messages")
    """
    return logging.getLogger(name)


def set_debug_mode():
    """Enable debug-level logging for troubleshooting."""
    logging.getLogger().setLevel(logging.DEBUG)
    logger = get_logger('debug')
    logger.info("Debug mode enabled - showing all log messages")


def set_quiet_mode():
    """Reduce logging to warnings and errors only."""
    logging.getLogger().setLevel(logging.WARNING)
    logger = get_logger('quiet')
    logger.warning("Quiet mode enabled - only warnings and errors will show")


def set_performance_mode():
    """Reduce logging during intensive operations for better performance.

    This temporarily reduces console output to WARNING level while keeping
    full file logging for later review.
    """
    root_logger = logging.getLogger()

    # Keep file logging at full level, but reduce console output
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, (RotatingFileHandler,)):
            handler.setLevel(logging.WARNING)

    logger = get_logger('performance')
    logger.warning("Performance mode enabled - reduced console logging during processing")


def restore_normal_mode():
    """Restore normal logging levels after performance mode."""
    root_logger = logging.getLogger()

    # Restore console output to INFO level
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, (RotatingFileHandler,)):
            handler.setLevel(logging.INFO)

    logger = get_logger('performance')
    logger.info("Normal logging mode restored")


def log_function_entry(func_name, **kwargs):
    """Helper to log function entry with parameters (useful for debugging)."""
    logger = get_logger('function_trace')
    if kwargs:
        params = ', '.join(f"{k}={v}" for k, v in kwargs.items())
        logger.debug(f"Entering {func_name}({params})")
    else:
        logger.debug(f"Entering {func_name}()")


def log_function_exit(func_name, result=None):
    """Helper to log function exit with return value."""
    logger = get_logger('function_trace')
    if result is not None:
        logger.debug(f"Exiting {func_name}() -> {result}")
    else:
        logger.debug(f"Exiting {func_name}()")


# Performance monitoring helpers
def log_timing(operation_name, duration_ms):
    """Log operation timing for performance monitoring."""
    logger = get_logger('performance')
    if duration_ms > 1000:  # Over 1 second
        logger.warning(f"{operation_name} took {duration_ms:.2f}ms (slow)")
    elif duration_ms > 100:  # Over 100ms
        logger.info(f"{operation_name} took {duration_ms:.2f}ms")
    else:
        logger.debug(f"{operation_name} took {duration_ms:.2f}ms")