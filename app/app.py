"""
Main Sixpence Bot application
Coordinates all operations and processes
"""

import asyncio
import random
from typing import List

from app.ui.menu import get_menu
from app.utils.logging import get_logger
from app.utils.shutdown import should_continue
from app.data.loader import load_accounts, load_proxies, get_proxy_for_account
from app.core.registration import RegistrationProcess
from app.core.farming import FarmingProcess
from app.config.settings import get_settings

logger = get_logger()


class SixpenceApp:
    """Main Sixpence application"""
    
    def __init__(self):
        self.menu = get_menu()
        self.settings = get_settings()
        self.running = True
        self.farming_processes = []  # Track farming processes for cleanup
    
    async def run(self, shutdown_event: asyncio.Event) -> None:
        """Main execution loop"""
        while self.running and should_continue():
            try:
                self.menu.show_welcome()
                choice = self.menu.show_menu()
                
                if choice == 1:
                    await self._handle_registration()
                elif choice == 2:
                    await self._handle_farming()
                elif choice == 3:
                    self.running = False
                    logger.info("Shutting down...")
                    break
                
                if self.running and should_continue():
                    input("Press Enter to continue...")
                    
            except KeyboardInterrupt:
                self.running = False
                logger.info("Interrupted by user")
                break
            except Exception as e:
                logger.error(f"Application error: {e}")
                # Wait for user input before continuing to show menu again
                input("Press Enter to continue...")
    
    async def _handle_registration(self) -> None:
        """Handle registration process"""
        accounts = load_accounts("reg.txt")
        if not accounts:
            logger.error("No accounts found in reg.txt")
            return
        
        proxies = load_proxies()
        
        self.menu.show_operation_info("Registration", len(accounts))
        
        # Create semaphore for concurrent processing
        semaphore = asyncio.Semaphore(self.settings.registration_threads)
        
        async def process_account(account: str, index: int) -> bool:
            async with semaphore:
                # Apply delay
                delay = random.randint(self.settings.delay_min, self.settings.delay_max)
                if delay > 0:
                    # Check shutdown during delay
                    for _ in range(delay):
                        if not should_continue():
                            return False
                        await asyncio.sleep(1)
                
                proxy = get_proxy_for_account(proxies, index)
                
                process = RegistrationProcess(account, proxy)
                return await process.process()
        
        # Process all accounts
        tasks = [
            process_account(account, i) 
            for i, account in enumerate(accounts)
        ]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except KeyboardInterrupt:
            logger.info("Registration interrupted")
            return
        
        # Count results - now results include skip status
        success_count = sum(1 for r in results if r is True)
        failed_count = sum(1 for r in results if r is False or isinstance(r, Exception))
        
        logger.info(f"Registration completed: {success_count} processed, {failed_count} failed")
    
    async def _handle_farming(self) -> None:
        """Handle farming process"""
        accounts = load_accounts("farm.txt")
        if not accounts:
            logger.error("No accounts found in farm.txt")
            return
        
        proxies = load_proxies()
        
        self.menu.show_operation_info("Farming", len(accounts))
        
        # Create semaphore for concurrent processing
        semaphore = asyncio.Semaphore(self.settings.farming_threads)
        
        async def process_account(account: str, index: int) -> None:
            async with semaphore:
                # Apply delay
                delay = random.randint(self.settings.delay_min, self.settings.delay_max)
                if delay > 0:
                    # Check shutdown during delay
                    for _ in range(delay):
                        if not should_continue():
                            return
                        await asyncio.sleep(1)
                
                proxy = get_proxy_for_account(proxies, index)
                
                process = FarmingProcess(account, proxy)
                self.farming_processes.append(process)  # Track for cleanup
                await process.process()
        
        # Process all accounts
        tasks = [
            process_account(account, i) 
            for i, account in enumerate(accounts)
        ]
        
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            logger.info("Farming interrupted")
            # Stop all farming processes immediately
            for process in self.farming_processes:
                process.stop()
        except Exception as e:
            logger.error(f"Farming error: {e}")
            # Stop all farming processes on error  
            for process in self.farming_processes:
                process.stop()
        finally:
            # Ensure all processes are stopped
            for process in self.farming_processes:
                process.stop()
    
    async def stop(self) -> None:
        """Stop the application"""
        self.running = False
        
        # Stop all farming processes
        for process in self.farming_processes:
            process.stop()
        
        logger.info("Application stopped")