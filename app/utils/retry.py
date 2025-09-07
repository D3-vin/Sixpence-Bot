"""        
Retry utility for Sixpence
Provides configurable retry logic with exponential backoff
"""

import asyncio
from typing import Callable, Any, Optional
from app.config.settings import get_settings
from app.utils.logging import get_logger
from app.utils.shutdown import is_shutdown_requested

logger = get_logger()


def _is_rate_limit_error(error: Exception) -> bool:
    """Check if error is a rate limit (429) error"""
    return "429" in str(error)
def _simplify_error_message(error: Exception) -> str:
    """Simplify error messages for better readability"""
    error_str = str(error)
    
    # Handle 429 errors (rate limiting)
    if "429" in error_str:
        return "Rate limit exceeded (429)"
    
    # Handle 522 errors
    if "522" in error_str:
        return "Connection timeout (522)"
    
    # Handle connection timeout
    if "connection timed out" in error_str.lower() or "timeout" in error_str.lower():
        return "Connection timeout"
    
    # Handle connection refused
    if "connection refused" in error_str.lower():
        return "Connection refused"
    
    # Handle invalid response status
    if "invalid response status" in error_str.lower():
        return "Invalid server response"
    
    # Return original if no simplification applies
    return error_str


async def retry_async(
    func: Callable,
    *args,
    eth_address: Optional[str] = None,
    operation_name: str = "operation",
    **kwargs
) -> Any:
    """
    Retry an async function with exponential backoff
    
    Args:
        func: Async function to retry
        *args: Arguments for the function
        eth_address: Ethereum address for logging context
        operation_name: Name of operation for logging
        **kwargs: Keyword arguments for the function
        
    Returns:
        Result of successful function call or None if all retries failed
    """
    settings = get_settings()
    max_attempts = settings.retry_max_attempts
    base_delay = settings.retry_delay
    backoff_multiplier = settings.retry_backoff_multiplier
    
    for attempt in range(1, max_attempts + 1):
        # Check shutdown before each attempt
        if is_shutdown_requested():
            logger.info(f"{operation_name} cancelled by shutdown", eth_address)
            return None
            
        try:
            result = await func(*args, **kwargs)
            if result:  # Success
                if attempt > 1:
                    logger.success(f"{operation_name} succeeded on attempt {attempt}", eth_address)
                return result
        except Exception as e:
            # Check shutdown before processing error
            if is_shutdown_requested():
                logger.info(f"{operation_name} cancelled by shutdown", eth_address)
                return None
                
            simplified_error = _simplify_error_message(e)
            logger.warning(
                f"{operation_name} failed (attempt {attempt}/{max_attempts}): {simplified_error}", 
                eth_address
            )
            
            # Don't sleep after the last attempt
            if attempt < max_attempts:
                # Use special delay for rate limit errors
                if _is_rate_limit_error(e):
                    delay = settings.retry_rate_limit_delay
                    logger.info(f"Rate limit detected, waiting {delay} seconds before retry...", eth_address)
                else:
                    delay = base_delay * (backoff_multiplier ** (attempt - 1))
                    logger.info(f"Retrying in {delay:.1f} seconds...", eth_address)
                
                # Sleep with shutdown checking every 100ms for faster response
                delay_ms = int(delay * 10)  # Convert to 100ms intervals
                for _ in range(delay_ms):
                    if is_shutdown_requested():
                        logger.info(f"{operation_name} cancelled during retry delay", eth_address)
                        return None
                    await asyncio.sleep(0.1)
            else:
                logger.error(f"{operation_name} failed after {max_attempts} attempts", eth_address)
    
    return None