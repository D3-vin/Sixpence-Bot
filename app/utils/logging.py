"""
Simple logging for Sixpence (based on Teneo style)
Keep it simple and effective
"""

import sys
from pathlib import Path
from typing import Optional

from colorama import init, Fore, Style
from loguru import logger

# Initialize colorama
init(autoreset=True)


class SixpenceLogger:
    """Simple logger for Sixpence"""
    
    def __init__(self, log_level: str = "INFO"):
        self.log_level = log_level
        self._setup_logger()
    
    def _setup_logger(self) -> None:
        """Setup simple logging"""
        logger.remove()
        
        # Console with colors
        logger.add(
            sys.stdout,
            colorize=True,
            format="<light-cyan>{time:HH:mm:ss}</light-cyan> | <level>{level: <8}</level> | - <white>{message}</white>",
            level=self.log_level
        )
        
        # Ensure logs directory
        Path("./logs").mkdir(exist_ok=True)
        
        # File logging
        logger.add(
            "./logs/sixpence.log",
            rotation="1 day",
            retention="7 days",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            level=self.log_level
        )
    
    def _format_account(self, account: str) -> str:
        """Format account for display"""
        if account.startswith('0x') and len(account) > 12:
            return f"{account[:6]}...{account[-4:]}"
        return account[:10] + "..." if len(account) > 10 else account
    
    def info(self, message: str, account: Optional[str] = None) -> None:
        """Log info message"""
        if account:
            formatted_account = self._format_account(account)
            logger.info(f"[{formatted_account}] {message}")
        else:
            logger.info(message)
    
    def success(self, message: str, account: Optional[str] = None) -> None:
        """Log success message"""
        if account:
            formatted_account = self._format_account(account)
            logger.success(f"[{formatted_account}] {message}")
        else:
            logger.success(message)
    
    def warning(self, message: str, account: Optional[str] = None) -> None:
        """Log warning message"""
        if account:
            formatted_account = self._format_account(account)
            logger.warning(f"[{formatted_account}] {message}")
        else:
            logger.warning(message)
    
    def error(self, message: str, account: Optional[str] = None) -> None:
        """Log error message"""
        if account:
            formatted_account = self._format_account(account)
            logger.error(f"[{formatted_account}] {message}")
        else:
            logger.error(message)
    
    def debug(self, message: str, account: Optional[str] = None) -> None:
        """Log debug message"""
        if account:
            formatted_account = self._format_account(account)
            logger.debug(f"[{formatted_account}] {message}")
        else:
            logger.debug(message)


# Global logger
_logger_instance: Optional[SixpenceLogger] = None


def get_logger() -> SixpenceLogger:
    """Get global logger instance"""
    global _logger_instance
    if _logger_instance is None:
        # Try to get log level from settings, fallback to INFO
        try:
            from app.config.settings import get_settings
            settings = get_settings()
            log_level = settings.logging_level
        except Exception:
            # Fallback if settings not available (e.g., during initialization)
            log_level = "INFO"
        
        _logger_instance = SixpenceLogger(log_level)
    return _logger_instance