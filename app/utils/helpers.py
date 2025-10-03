"""Общие утилиты для повторных попыток и обработки ошибок."""

import asyncio
from typing import Any, Callable, Optional

from app.config.settings import get_settings
from app.utils.logging import get_logger
from app.utils.shutdown import is_shutdown_requested

logger = get_logger()


def _is_rate_limit_error(error: Exception) -> bool:
    """Определяет, указывает ли ошибка на лимит 429."""
    return "429" in str(error)


def _simplify_error_message(error: Exception) -> str:
    """Упрощает текст ошибок для более понятного логирования."""
    error_str = str(error)

    if "429" in error_str:
        return "Rate limit exceeded (429)"
    if "522" in error_str:
        return "Connection timeout (522)"

    lowered = error_str.lower()
    if "connection timed out" in lowered or "timeout" in lowered:
        return "Connection timeout"
    if "connection refused" in lowered:
        return "Connection refused"
    if "invalid response status" in lowered:
        return "Invalid server response"

    return error_str


async def retry_async(
    func: Callable,
    *args: Any,
    eth_address: Optional[str] = None,
    operation_name: str = "operation",
    **kwargs: Any,
) -> Any:
    """Повторяет асинхронную операцию с экспоненциальным бэкоффом."""

    settings = get_settings()
    max_attempts = settings.retry_max_attempts
    base_delay = settings.retry_delay
    backoff_multiplier = settings.retry_backoff_multiplier

    for attempt in range(1, max_attempts + 1):
        if is_shutdown_requested():
            logger.info(f"{operation_name} cancelled by shutdown", eth_address)
            return None

        try:
            result = await func(*args, **kwargs)
            if result:
                if attempt > 1:
                    logger.success(f"{operation_name} succeeded on attempt {attempt}", eth_address)
                return result
        except Exception as exc:  # noqa: BLE001
            if is_shutdown_requested():
                logger.info(f"{operation_name} cancelled by shutdown", eth_address)
                return None

            simplified = _simplify_error_message(exc)
            logger.warning(
                f"{operation_name} failed (attempt {attempt}/{max_attempts}): {simplified}",
                eth_address,
            )

            if attempt >= max_attempts:
                logger.error(f"{operation_name} failed after {max_attempts} attempts", eth_address)
                break

            if _is_rate_limit_error(exc):
                delay = settings.retry_rate_limit_delay
                logger.info(f"Rate limit detected, waiting {delay} seconds before retry...", eth_address)
            else:
                delay = base_delay * (backoff_multiplier ** (attempt - 1))
                logger.info(f"Retrying in {delay:.1f} seconds...", eth_address)

            intervals = int(delay * 10)
            for _ in range(intervals):
                if is_shutdown_requested():
                    logger.info(f"{operation_name} cancelled during retry delay", eth_address)
                    return None
                await asyncio.sleep(0.1)

    return None


__all__ = ["retry_async", "_is_rate_limit_error", "_simplify_error_message"]
