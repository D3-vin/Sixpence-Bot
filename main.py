#!/usr/bin/env python3
"""
Sixpence Bot - Main Entry Point
Optimized and refactored version
"""

import asyncio
import sys
import signal
import os
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.app import SixpenceApp
from app.utils.logging import get_logger
from app.data.database import init_database


def handle_interrupt(signum, frame):
    """Handle interrupt signals - immediate exit"""
    logger = get_logger()
    logger.info("Received interrupt signal. Exiting immediately...")
    
    # Force immediate exit
    try:
        # Cancel all running tasks
        for task in asyncio.all_tasks():
            task.cancel()
    except:
        pass
    
    # Force exit with os._exit (bypasses cleanup)
    os._exit(0)


async def main():
    """Main entry point"""
    logger = get_logger()
    
    try:
        logger.info("Starting Sixpence Bot...")
        
        # Initialize database
        await init_database()
        
        manager = SixpenceApp()
        await manager.run()
        
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Setup signal handlers for immediate exit
    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)
    
    # Set event loop policy for Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)