#!/usr/bin/env python3
"""
Sixpence Bot - Main Entry Point
Optimized and refactored version
"""

import asyncio
import sys
import signal
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.app import SixpenceApp
from app.utils.logging import get_logger
from app.data.database import init_database, close_database
from app.utils.shutdown import get_shutdown_manager

# Global flag for shutdown
shutdown_event = asyncio.Event()
shutdown_initiated = False


def handle_interrupt(signum, frame):
    """Handle interrupt signals"""
    global shutdown_initiated
    if not shutdown_initiated:
        logger = get_logger()
        logger.info("Received interrupt signal. Shutting down...")
        shutdown_event.set()  # Set the shutdown event instead of sys.exit
        shutdown_initiated = True
    # Ignore subsequent signals


async def main():
    """Main entry point"""
    logger = get_logger()
    manager = None
    
    try:
        logger.info("Starting Sixpence Bot...")
        
        # Initialize database
        await init_database()
        
        # Initialize shutdown manager
        get_shutdown_manager().initialize(shutdown_event)
        
        manager = SixpenceApp()
        
        # Pass shutdown event to manager
        await manager.run(shutdown_event)
        
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
    finally:
        if manager:
            await manager.stop()
        
        # Close database
        await close_database()
        
        # Cancel all remaining tasks
        tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        if tasks:
            logger.info(f"Cancelling {len(tasks)} remaining tasks")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info("Application shutdown complete")


if __name__ == "__main__":
    # Setup signal handlers
    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)
    
    # Set event loop policy for Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)