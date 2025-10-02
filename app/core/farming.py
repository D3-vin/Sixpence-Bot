"""
Farming process for Sixpence
Handles WebSocket farming with authentication and proxy rotation
"""

import asyncio
from typing import Optional

from app.api.client import SixpenceAPI
from app.api.websocket import SixpenceWebSocket
from app.data.database import get_db
from app.utils.logging import get_logger
from app.utils.proxy_rotation import ProxyRotator
from app.config.settings import get_settings

logger = get_logger()


class FarmingProcess:
    """Handle farming process with persistence and proxy rotation"""
    
    def __init__(self, private_key: str, proxy: Optional[str] = None):
        self.private_key = private_key
        self.proxy = proxy
        self.api = SixpenceAPI(private_key, proxy)
        self.db = get_db()
        self.websocket = None
        self.settings = get_settings()
        self.proxy_rotator = ProxyRotator(proxy)
        self.running = True
        self.attempt_count = 0  # Track attempts with current proxy
    
    async def process(self) -> None:
        """Run persistent farming process with proxy rotation"""
        while self.running:
            try:
                logger.debug("Starting farming session", self.api.eth_address)
                
                # Get or refresh auth token
                auth_token = await self._get_auth_token()
                if not auth_token:
                    logger.error("Failed to get auth token", self.api.eth_address)
                    if not await self._handle_farming_failure():
                        break
                    continue
                
                # Start WebSocket farming (WebSocket auth message is stored in database)
                self.websocket = SixpenceWebSocket(self.private_key, auth_token, self.proxy)
                
                # Try single connection attempt without internal retries
                if not await self.websocket.connect_single_attempt():
                    logger.warning("WebSocket connection failed", self.api.eth_address)
                    if not await self._handle_farming_failure():
                        break
                    continue
                
                # Try single authentication attempt without internal retries
                if not await self.websocket.authenticate_single_attempt():
                    logger.warning("WebSocket authentication failed", self.api.eth_address)
                    await self.websocket.disconnect()
                    if not await self._handle_farming_failure():
                        break
                    continue
                
                # Start farming session (this will run until connection is lost)
                try:
                    session_ok = await self.websocket.start_farming_session()
                except Exception as e:
                    logger.error(f"Farming session error: {e}", self.api.eth_address)
                    if not await self._handle_farming_failure():
                        break
                    continue

                if session_ok:
                    self.attempt_count = 0  # Reset on success
                    continue

                logger.warning("WebSocket session ended unexpectedly, scheduling reconnect", self.api.eth_address)
                if not await self._handle_farming_failure():
                    break
                    
            except KeyboardInterrupt:
                logger.info("Farming interrupted by user", self.api.eth_address)
                break
            except Exception as e:
                error_msg = str(e)
                if "ctype 'void *'" in error_msg or "cdata pointer" in error_msg:
                    logger.error(f"curl_cffi library error detected: {error_msg}", self.api.eth_address)
                    # Handle curl_cffi error with session reset and proxy rotation
                    if not await self._handle_curl_cffi_error():
                        break
                else:
                    logger.error(f"Farming session failed: {e}", self.api.eth_address)
                    if not await self._handle_farming_failure():
                        break
                    
            # Loop will exit naturally when self.running becomes False
            pass
                
        # Cleanup after the main loop
        await self._cleanup()
                
        logger.info("Farming process terminated", self.api.eth_address)
    
    async def _handle_curl_cffi_error(self) -> bool:
        """Handle curl_cffi library error with session reset and proxy rotation"""
        logger.info("Handling curl_cffi error in farming: waiting 1-2 seconds before session reset", self.api.eth_address)
        
        # Wait 1-2 seconds as requested
        await asyncio.sleep(1.5)
        
        # Cleanup current session
        await self._cleanup_session()
        await self.api.close()
        
        # Try to get next proxy if proxy rotation is enabled
        if self.settings.proxy_rotation_enabled:
            new_proxy = self.proxy_rotator.get_next_proxy(self.api.eth_address)
            if new_proxy != self.proxy:
                self.proxy = new_proxy
                logger.info("Switched to new proxy due to curl_cffi error", self.api.eth_address)
                self.attempt_count = 0  # Reset attempts with new proxy
            else:
                logger.warning("No alternative proxy available for curl_cffi error recovery", self.api.eth_address)
        
        # Wait additional 1 second before creating new session
        await asyncio.sleep(1)
        
        # Create new API session
        try:
            self.api = SixpenceAPI(self.private_key, self.proxy)
            logger.debug("New API session created after curl_cffi error", self.api.eth_address)
            return True
        except Exception as e:
            logger.error(f"Failed to create new API session after curl_cffi error: {e}", self.api.eth_address)
            return False

    async def _handle_farming_failure(self) -> bool:
        """Handle farming failure with delay and proxy rotation"""
        
        self.attempt_count += 1
        max_attempts = self.settings.retry_max_attempts
        
        # If we haven't exhausted attempts yet, use regular retry delay
        if self.attempt_count < max_attempts:
            delay_seconds = self.settings.retry_delay
            logger.warning(f"WebSocket failed (attempt {self.attempt_count}/{max_attempts}), waiting {delay_seconds} seconds...", self.api.eth_address)
            
            for remaining in range(delay_seconds, 0, -1):
                if not self.running:
                    return False
                #if remaining > 1:
                    #logger.debug(f"Retrying in {remaining} seconds...", self.api.eth_address)
                await asyncio.sleep(1)
            
            return True
        
        # We've exhausted all attempts, now apply farming wait delay
        farming_wait_seconds = self.settings.farming_wait_seconds
        logger.info(f"All {max_attempts} attempts failed, waiting {farming_wait_seconds} seconds before next action...", self.api.eth_address)
        
        for remaining in range(farming_wait_seconds, 0, -1):
            if not self.running:
                return False
            #if remaining > 1:
                #logger.debug(f"Next action in {remaining} seconds...", self.api.eth_address)
            await asyncio.sleep(1)
        
        # Check proxy rotation setting
        if not self.settings.proxy_rotation_enabled:
            logger.info(f"Max attempts ({max_attempts}) reached, but proxy rotation disabled. Continuing with same proxy.", self.api.eth_address)
            self.attempt_count = 0  # Reset counter to continue with same proxy
            return True
        
        # Try to get next proxy
        new_proxy = self.proxy_rotator.get_next_proxy(self.api.eth_address)
        if new_proxy == self.proxy:
            logger.warning("No alternative proxy available, continuing with current proxy", self.api.eth_address)
            self.attempt_count = 0  # Reset counter to continue with same proxy
            return True
        
        # Update proxy and reset attempt count
        self.proxy = new_proxy
        self.attempt_count = 0
        logger.info(f"Max attempts reached, switching to new proxy", self.api.eth_address)
        
        # Create new API instance with new proxy
        await self.api.close()
        self.api = SixpenceAPI(self.private_key, self.proxy)
        
        return True
    
    async def _cleanup_session(self) -> None:
        """Cleanup current farming session"""
        try:
            if self.websocket:
                await self.websocket.disconnect()
                self.websocket = None
        except Exception as e:
            logger.error(f"Session cleanup error: {e}", self.api.eth_address)
    
    def stop(self) -> None:
        """Stop the farming process"""
        self.running = False
        logger.info("Farming cancelled", self.api.eth_address)
    
    async def _get_auth_token(self) -> Optional[str]:
        """Get authentication token"""
        # Try to get saved token
        saved_token = await self.db.get_token(self.private_key)
        if saved_token:
            logger.debug("Using saved token", self.api.eth_address)
            return saved_token
        
        # Get new token
        try:
            login_result = await self.api.login()
            
            if login_result:
                auth_token = self.api.access_token
                if auth_token:
                    # Save token to database
                    await self.db.save_token(self.private_key, auth_token)
                    logger.success("New token obtained and saved", self.api.eth_address)
                    return auth_token
            
            return None
        except Exception as e:
            logger.error(f"Failed to get auth token: {e}", self.api.eth_address)
            return None
    
    async def _cleanup(self) -> None:
        """Cleanup resources"""
        try:
            await self._cleanup_session()
            await self.api.close()
        except Exception as e:
            logger.error(f"Cleanup error: {e}", self.api.eth_address)