#!/usr/bin/env python3
"""
Sixpence Bot - Main Entry Point
Optimized and refactored version
"""

import asyncio
import sys
import signal
from pathlib import Path
from typing import Optional

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.app import SixpenceApp
from app.utils.logging import get_logger
from app.data.database import init_database, close_database
from app.utils.shutdown import get_shutdown_manager

shutdown_event: Optional[asyncio.Event] = None


def handle_interrupt(signum, frame):
    """Handle interrupt signals - immediate exit"""
    logger = get_logger()
    logger.info("Interrupt received. Initiating shutdown...")

    if shutdown_event is not None:
        shutdown_event.set()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop:
        for task in asyncio.all_tasks(loop):
            task.cancel()


async def main():
    """Main entry point"""
    logger = get_logger()
    manager = None
    global shutdown_event

    try:
        logger.info("Starting Sixpence Bot...")
        
        # Initialize database
        await init_database()
        shutdown_event = asyncio.Event()
        get_shutdown_manager().initialize(shutdown_event)
        
        manager = SixpenceApp()
        await manager.run()
        
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise
    finally:
        if shutdown_event is not None:
            shutdown_event.set()
        if manager is not None:
            await manager.stop()
        await close_database()

        # Cancel remaining asyncio tasks
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("Application shutdown complete")


if __name__ == "__main__":
    # Setup signal handlers for immediate exit
    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)
    
    # Set event loop policy for Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())