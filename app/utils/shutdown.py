"""
Centralized shutdown management for Sixpence
Handles graceful shutdown across all components
"""

import asyncio
from typing import Optional


class ShutdownManager:
    """Centralized shutdown event manager"""
    
    def __init__(self):
        self._shutdown_event: Optional[asyncio.Event] = None
        self._initialized = False
    
    def initialize(self, shutdown_event: asyncio.Event) -> None:
        """Initialize with shutdown event from main"""
        self._shutdown_event = shutdown_event
        self._initialized = True
    
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested"""
        if not self._initialized or not self._shutdown_event:
            return False
        return self._shutdown_event.is_set()
    
    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal"""
        if self._initialized and self._shutdown_event:
            await self._shutdown_event.wait()
    
    def should_continue(self) -> bool:
        """Check if operations should continue"""
        return not self.is_shutdown_requested()


# Global shutdown manager
_shutdown_manager = ShutdownManager()


def get_shutdown_manager() -> ShutdownManager:
    """Get global shutdown manager instance"""
    return _shutdown_manager


def is_shutdown_requested() -> bool:
    """Quick check if shutdown was requested"""
    return get_shutdown_manager().is_shutdown_requested()


def should_continue() -> bool:
    """Quick check if operations should continue"""
    return get_shutdown_manager().should_continue()