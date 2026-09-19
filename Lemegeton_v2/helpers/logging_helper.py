"""Logging helper for the project.

Provides a small factory to create per-module loggers that:
- write to `logs/<module>.log` by default using RotatingFileHandler
- use a single FileHandler per logger (avoid duplicate handlers on reload)
- use an ISO-like UTC timestamp in the formatter

Usage:
    from helpers.logging_helper import get_logger
    logger = get_logger("Recommendations", level=logging.DEBUG)
    logger.info("started")
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
import time
from typing import Optional


DEFAULT_MAX_BYTES = 5_000_000
DEFAULT_BACKUP_COUNT = 5


def _utc_formatter(fmt: Optional[str] = None) -> logging.Formatter:
    fmt = fmt or "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    formatter = logging.Formatter(fmt)
    # Use UTC time for timestamps
    formatter.converter = time.gmtime
    return formatter


def get_logger(
    name: str,
    logfile: Optional[str] = None,
    level: int = logging.INFO,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    console: bool = False,
) -> logging.Logger:
    """Return a configured logger for `name`.

    - If `logfile` is not provided, uses `logs/{name.lower()}.log`.
    - Ensures the `logs/` directory exists.
    - Avoids adding duplicate FileHandlers when the cog/module is reloaded.
    - Optionally adds a console StreamHandler when `console=True` (useful for local dev).
    """

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Ensure logs directory exists
    logs_dir = os.path.join(os.getcwd(), "logs")
    try:
        os.makedirs(logs_dir, exist_ok=True)
    except Exception:
        # If we can't create logs dir, fall back to current working directory
        logs_dir = os.getcwd()

    if logfile:
        # allow both absolute and relative paths
        logfile_path = logfile if os.path.isabs(logfile) else os.path.join(logs_dir, logfile)
    else:
        logfile_path = os.path.join(logs_dir, f"{name.lower()}.log")

    # Check whether a RotatingFileHandler for this path is already attached
    file_handler_exists = False
    for h in logger.handlers:
        if isinstance(h, RotatingFileHandler):
            try:
                existing = os.path.abspath(getattr(h, "baseFilename", ""))
                if existing == os.path.abspath(logfile_path):
                    file_handler_exists = True
                    break
            except Exception:
                # Some handlers may not have baseFilename or be inaccessible; ignore
                continue

    if not file_handler_exists:
        fh = RotatingFileHandler(logfile_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(_utc_formatter())
        logger.addHandler(fh)

    # Optionally add a console handler (only one)
    if console:
        has_console = any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
        if not has_console:
            ch = logging.StreamHandler()
            ch.setLevel(level)
            ch.setFormatter(_utc_formatter())
            logger.addHandler(ch)

    # Avoid propagating to root logger so logs don't double-print
    logger.propagate = False

    return logger


__all__ = ["get_logger"]
"""
Logging Helper Functions
Centralized logging configuration and utilities for the bot
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List


# Configuration constants
LOG_DIR = Path("logs")
DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_FORMAT = "[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_LOG_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_LOG_FILES = 5

# Ensure logs directory exists
LOG_DIR.mkdir(exist_ok=True)


# ===== LOGGER SETUP FUNCTIONS =====

def setup_logger(
    name: str,
    log_file: Optional[str] = None,
    level: int = DEFAULT_LOG_LEVEL,
    format_string: str = DEFAULT_FORMAT,
    date_format: str = DEFAULT_DATE_FORMAT,
    console_output: bool = True,
    file_output: bool = True,
    max_file_size: int = MAX_LOG_FILE_SIZE,
    backup_count: int = MAX_LOG_FILES
) -> logging.Logger:
    """
    Set up a logger with both file and console handlers.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(format_string, date_format)
    
    # Add console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # Add file handler
    if file_output:
        if log_file is None:
            log_file = f"{name.lower()}.log"
        
        log_path = LOG_DIR / log_file
        
        # Use rotating file handler to prevent huge log files
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    logger.info(f"Logger '{name}' initialized with level {logging.getLevelName(level)}")
    return logger


def setup_bot_logger(bot_name: str = "bot") -> logging.Logger:
    """
    Set up the main bot logger with standard configuration.
    """
    return setup_logger(
        name=bot_name,
        log_file="bot.log",
        level=logging.INFO,
        console_output=True,
        file_output=True
    )


def setup_cog_logger(cog_name: str, level: int = DEFAULT_LOG_LEVEL) -> logging.Logger:
    """
    Set up a logger for a specific cog.
    """
    return setup_logger(
        name=cog_name,
        log_file=f"{cog_name.lower()}.log",
        level=level,
        console_output=False,  # Cogs usually don't need console output
        file_output=True
    )


def setup_database_logger() -> logging.Logger:
    """
    Set up the database logger with specific configuration.
    """
    return setup_logger(
        name="Database",
        log_file="database.log",
        level=logging.DEBUG,  # Database operations often need detailed logging
        console_output=False,
        file_output=True
    )


# ===== LOGGING UTILITIES =====

def log_command_usage(logger: logging.Logger, interaction, command_name: str, **kwargs):
    """
    Log command usage with user and guild information.
    """
    user_id = interaction.user.id
    user_name = interaction.user.display_name
    guild_id = interaction.guild.id if interaction.guild else "DM"
    guild_name = interaction.guild.name if interaction.guild else "Direct Message"
    
    log_msg = f"Command '{command_name}' used by {user_name} ({user_id}) in {guild_name} ({guild_id})"
    
    if kwargs:
        params = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        log_msg += f" with params: {params}"
    
    logger.info(log_msg)


def log_api_request(logger: logging.Logger, api_name: str, endpoint: str, status_code: int, response_time: float = None):
    """
    Log API request details.
    """
    log_msg = f"API {api_name} - {endpoint} - Status: {status_code}"
    
    if response_time is not None:
        log_msg += f" - Time: {response_time:.2f}s"
    
    if status_code >= 400:
        logger.warning(log_msg)
    else:
        logger.debug(log_msg)


def log_database_operation(logger: logging.Logger, operation: str, table: str, success: bool, **details):
    """
    Log database operation details.
    """
    status = "SUCCESS" if success else "FAILED"
    log_msg = f"DB {operation} on {table} - {status}"
    
    if details:
        detail_str = ", ".join([f"{k}={v}" for k, v in details.items()])
        log_msg += f" - {detail_str}"
    
    if success:
        logger.debug(log_msg)
    else:
        logger.error(log_msg)


def log_error_with_context(logger: logging.Logger, error: Exception, context: str = "", **kwargs):
    """
    Log error with additional context information.
    """
    error_msg = f"Error in {context}: {type(error).__name__}: {str(error)}"
    
    if kwargs:
        context_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        error_msg += f" - Context: {context_str}"
    
    logger.error(error_msg, exc_info=True)


def log_user_action(logger: logging.Logger, user_id: int, action: str, details: str = ""):
    """
    Log user action for audit trail.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"User {user_id} performed action '{action}'"
    
    if details:
        log_msg += f" - {details}"
    
    logger.info(log_msg)


# ===== LOG ANALYSIS UTILITIES =====

def get_log_files() -> List[Path]:
    """
    Get list of all log files in the logs directory.
    """
    if not LOG_DIR.exists():
        return []
    
    return list(LOG_DIR.glob("*.log*"))


def get_log_file_info(log_file: Path) -> Dict[str, Any]:
    """
    Get information about a log file.
    """
    try:
        stat = log_file.stat()
        return {
            "name": log_file.name,
            "size_bytes": stat.st_size,
            "size_mb": stat.st_size / (1024 * 1024),
            "modified": datetime.fromtimestamp(stat.st_mtime),
            "created": datetime.fromtimestamp(stat.st_ctime)
        }
    except Exception as e:
        return {
            "name": log_file.name,
            "error": str(e)
        }


def clean_old_logs(max_age_days: int = 30) -> int:
    """
    Remove log files older than specified days.
    Returns number of files removed.
    """
    if not LOG_DIR.exists():
        return 0
    
    current_time = datetime.now().timestamp()
    max_age_seconds = max_age_days * 24 * 3600
    removed_count = 0
    
    for log_file in get_log_files():
        try:
            file_age = current_time - log_file.stat().st_mtime
            if file_age > max_age_seconds:
                try:
                    log_file.unlink()
                    removed_count += 1
                except PermissionError:
                    # File is in use by another process; skip
                    continue
        except Exception:
            continue
    
    return removed_count


def get_recent_errors(log_file: Optional[str] = None, hours: int = 24, limit: int = 100) -> List[str]:
    """
    Get recent error messages from log files.
    """
    errors = []
    
    if log_file:
        log_files = [LOG_DIR / log_file] if (LOG_DIR / log_file).exists() else []
    else:
        log_files = get_log_files()
    
    cutoff_time = datetime.now().timestamp() - (hours * 3600)
    
    for log_path in log_files:
        try:
            # Check if file is recent enough
            if log_path.stat().st_mtime < cutoff_time:
                continue
            
            with open(log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if any(level in line for level in ['ERROR', 'CRITICAL', 'EXCEPTION']):
                        errors.append(line.strip())
                        if len(errors) >= limit:
                            return errors
        except Exception:
            continue
    
    return errors


def get_log_statistics(log_file: Optional[str] = None, hours: int = 24) -> Dict[str, int]:
    """
    Get log level statistics from recent logs.
    """
    stats = {
        "DEBUG": 0,
        "INFO": 0,
        "WARNING": 0,
        "ERROR": 0,
        "CRITICAL": 0
    }
    
    if log_file:
        log_files = [LOG_DIR / log_file] if (LOG_DIR / log_file).exists() else []
    else:
        log_files = get_log_files()
    
    cutoff_time = datetime.now().timestamp() - (hours * 3600)
    
    for log_path in log_files:
        try:
            # Check if file is recent enough
            if log_path.stat().st_mtime < cutoff_time:
                continue
            
            with open(log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    for level in stats.keys():
                        if f"[{level}]" in line:
                            stats[level] += 1
                            break
        except Exception:
            continue
    
    return stats


# ===== PERFORMANCE LOGGING =====

class PerformanceLogger:
    """
    Context manager for logging performance metrics.
    """
    
    def __init__(self, logger: logging.Logger, operation: str, **context):
        self.logger = logger
        self.operation = operation
        self.context = context
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.debug(f"Starting {self.operation}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        if exc_type is None:
            self.logger.info(f"Completed {self.operation} in {duration:.2f}s", extra=self.context)
        else:
            self.logger.error(f"Failed {self.operation} after {duration:.2f}s: {exc_val}", extra=self.context)


# ===== LOG FORMATTING UTILITIES =====

def format_user_for_log(user) -> str:
    """
    Format Discord user for logging.
    """
    if hasattr(user, 'id'):
        return f"{user.display_name} ({user.id})"
    return str(user)


def format_guild_for_log(guild) -> str:
    """
    Format Discord guild for logging.
    """
    if hasattr(guild, 'id'):
        return f"{guild.name} ({guild.id})"
    return str(guild)


def format_channel_for_log(channel) -> str:
    """
    Format Discord channel for logging.
    """
    if hasattr(channel, 'id'):
        if hasattr(channel, 'name'):
            return f"#{channel.name} ({channel.id})"
        else:
            return f"Channel {channel.id}"
    return str(channel)


# ===== CUSTOM LOG FILTERS =====

class SensitiveDataFilter(logging.Filter):
    """
    Filter to remove sensitive data from log messages.
    """
    
    SENSITIVE_PATTERNS = [
        r'token[=:]\s*\S+',
        r'password[=:]\s*\S+',
        r'key[=:]\s*\S+',
        r'secret[=:]\s*\S+'
    ]
    
    def filter(self, record):
        import re
        
        if hasattr(record, 'msg'):
            message = str(record.msg)
            for pattern in self.SENSITIVE_PATTERNS:
                message = re.sub(pattern, '[REDACTED]', message, flags=re.IGNORECASE)
            record.msg = message
        
        return True


def add_sensitive_data_filter(logger: logging.Logger):
    """
    Add sensitive data filter to logger.
    """
    filter_obj = SensitiveDataFilter()
    logger.addFilter(filter_obj)


# ===== INTEGRATION WITH DISCORD.PY =====

def setup_discord_logging(level: int = logging.WARNING):
    """
    Set up logging for discord.py library.
    """
    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(level)
    
    # Create handler for discord logs
    handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / 'discord.log',
        maxBytes=MAX_LOG_FILE_SIZE,
        backupCount=MAX_LOG_FILES,
        encoding='utf-8'
    )
    
    formatter = logging.Formatter(DEFAULT_FORMAT, DEFAULT_DATE_FORMAT)
    handler.setFormatter(formatter)
    discord_logger.addHandler(handler)
    
    return discord_logger


# ===== EMERGENCY LOGGING =====

def emergency_log(message: str, level: int = logging.CRITICAL):
    """
    Emergency logging function that writes directly to file.
    Use when normal logging might be compromised.
    """
    try:
        emergency_file = LOG_DIR / "emergency.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        level_name = logging.getLevelName(level)
        
        with open(emergency_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{level_name}] EMERGENCY: {message}\n")
    except Exception:
        # If even emergency logging fails, try stderr
        try:
            print(f"EMERGENCY LOG FAILED - {message}", file=sys.stderr)
        except Exception:
            pass  # Nothing more we can do