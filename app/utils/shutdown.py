"""Централизованное управление завершением работы для Sixpence."""

import asyncio
from typing import Optional


class ShutdownManager:
    """Менеджер, хранящий глобальное событие завершения."""

    def __init__(self) -> None:
        self._shutdown_event: Optional[asyncio.Event] = None
        self._initialized = False

    def initialize(self, shutdown_event: asyncio.Event) -> None:
        """Привязывает внешнее событие завершения."""
        self._shutdown_event = shutdown_event
        self._initialized = True

    def is_shutdown_requested(self) -> bool:
        """Проверяет, запрошено ли завершение."""
        if not self._initialized or not self._shutdown_event:
            return False
        return self._shutdown_event.is_set()

    async def wait_for_shutdown(self) -> None:
        """Ожидает установки события завершения."""
        if self._initialized and self._shutdown_event:
            await self._shutdown_event.wait()

    def should_continue(self) -> bool:
        """True, если можно продолжать выполнение."""
        return not self.is_shutdown_requested()


_shutdown_manager = ShutdownManager()


def get_shutdown_manager() -> ShutdownManager:
    """Возвращает глобальный менеджер завершения."""
    return _shutdown_manager


def is_shutdown_requested() -> bool:
    """Удобный шорткат для проверки завершения."""
    return _shutdown_manager.is_shutdown_requested()


def should_continue() -> bool:
    """Удобный шорткат для проверки возможности продолжения."""
    return _shutdown_manager.should_continue()
