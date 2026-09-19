import logging
import functools
from datetime import datetime
from typing import Callable, Any
import discord
from discord.ext import commands

logger = logging.getLogger("CommandLogger")
logger.setLevel(logging.INFO)

# Ensure logs directory exists
import os
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "command_usage.log")

# Set up file handler for command logging
if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == os.path.abspath(LOG_FILE)
           for h in logger.handlers):
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
        logger.addHandler(file_handler)
    except Exception:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
        logger.addHandler(stream_handler)

def log_command(func: Callable) -> Callable:
    """
    Decorator to log command usage with user, guild, and command information.
    Works with both regular commands and app commands.
    Logs AFTER execution to avoid delaying interaction responses.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Pre-extract logging info but don't log yet
        log_info = None
        
        if args and hasattr(args[0], 'guild_id'):  # App command interaction
            interaction = args[0]
            log_info = {
                'user_id': interaction.user.id,
                'user_name': interaction.user.display_name,
                'guild_id': interaction.guild_id,
                'guild_name': interaction.guild.name if interaction.guild else "DM",
                'command_name': func.__name__
            }
        elif args and hasattr(args[0], 'author'):  # Traditional command context
            ctx = args[0]
            log_info = {
                'user_id': ctx.author.id,
                'user_name': ctx.author.display_name,
                'guild_id': ctx.guild.id if ctx.guild else None,
                'guild_name': ctx.guild.name if ctx.guild else "DM",
                'command_name': func.__name__
            }
        
        # Execute the original function FIRST to avoid interaction delays
        try:
            result = await func(*args, **kwargs)
            
            # Log success AFTER execution
            if log_info:
                logger.info(f"Command '{log_info['command_name']}' used by {log_info['user_name']} ({log_info['user_id']}) in guild '{log_info['guild_name']}' ({log_info['guild_id']})")
            else:
                logger.info(f"Command '{func.__name__}' executed")
            
            return result
        except Exception as e:
            # Log error with context
            if log_info:
                logger.error(f"Error in command '{log_info['command_name']}' by {log_info['user_name']}: {e}")
            else:
                logger.error(f"Error in command '{func.__name__}': {e}")
            raise
    
    return wrapper
