"""
Registration process for Sixpence
Handles account registration with referral codes and retry logic
"""

import asyncio
import json
from typing import Optional

from app.api.client import SixpenceAPI
from app.data.database import get_db
from app.utils.logging import get_logger
from app.utils.proxy_rotation import ProxyRotator
from app.config.settings import get_settings

logger = get_logger()


class RegistrationProcess:
    """Handle account registration with retry logic and proxy rotation"""
    
    def __init__(self, private_key: str, proxy: Optional[str] = None):
        self.private_key = private_key
        self.proxy = proxy
        self.api = SixpenceAPI(private_key, proxy)
        self.db = get_db()
        self.settings = get_settings()
        self.proxy_rotator = ProxyRotator(proxy)
        self.running = True
        self.attempt_count = 0  # Track attempts with current proxy
    
    async def process(self) -> bool:
        """Run registration process with retry and proxy rotation"""
        max_attempts = self.settings.retry_max_attempts
        
        while self.attempt_count < max_attempts:
            try:
                # Ensure database is initialized
                await self.db.init()
                
                # Check if account already exists in database
                existing_account = await self.db.get_account(self.private_key)
                if existing_account and existing_account.get("auth_token"):
                    logger.info("Account already registered, skipping", self.api.eth_address)
                    return True
                
                logger.info(f"Starting registration (attempt {self.attempt_count + 1}/{max_attempts})", self.api.eth_address)
                
                # Try registration
                if await self._attempt_registration():
                    logger.success("Registration completed successfully", self.api.eth_address)
                    return True
                
                # Registration failed, handle failure
                if not await self._handle_registration_failure():
                    return False
                    
            except Exception as e:
                error_msg = str(e)
                if "ctype 'void *'" in error_msg or "cdata pointer" in error_msg:
                    logger.error(f"curl_cffi library error detected, skipping this account: {error_msg}", self.api.eth_address)
                    return False  # Skip this account to prevent infinite loops
                else:
                    logger.error(f"Registration failed: {e}", self.api.eth_address)
                
                if not await self._handle_registration_failure():
                    return False
        
        logger.error(f"Registration failed after {max_attempts} attempts", self.api.eth_address)
        return False
    
    async def _attempt_registration(self) -> bool:
        """Single registration attempt"""
        try:
            # Get nonce and login
            login_result = await self.api.login()
            
            if not login_result:
                logger.error("Login failed", self.api.eth_address)
                return False
            
            # Save auth token after successful login
            if self.api.access_token:
                await self.db.save_token(self.private_key, self.api.access_token)
                logger.debug("Auth token saved to database", self.api.eth_address)
            
            # Get user info to check registration status
            user_info = await self.api.user_info()
            
            if user_info and user_info.get("msg") == "ok":
                # Check if referral code needs to be bound
                invited = user_info.get("data", {}).get("referral", {}).get("inviteCode")
                if invited is None:
                    ref_code = await self._get_ref_code()
                    if ref_code:
                        bind_result = await self.api.bind_invite(ref_code)
                        if bind_result:
                            logger.success(f"Bound referral code: {ref_code}", self.api.eth_address)
                        else:
                            logger.warning(f"Failed to bind referral code: {ref_code}", self.api.eth_address)
                else:
                    logger.info(f"Referral code already bound: {invited}", self.api.eth_address)
                
                # Check if companion needs to be registered
                egg_info_id = user_info.get("data", {}).get("eggInfo", {}).get("eggInfoId")
                if egg_info_id is None:
                    await self._process_register_companion()
                else:
                    logger.info(f"Companion already registered: {egg_info_id}", self.api.eth_address)
            else:
                logger.error("Failed to get user info or invalid response", self.api.eth_address)
                return False
            
            # Save account to database with auth token
            auth_token = self.api.access_token if self.api.access_token else None
            await self.db.save_account(self.private_key, auth_token=auth_token)
            
            # Get the generated invite code from the dedicated endpoint
            invite_code_response = await self.api.get_invite_code()
            if invite_code_response and invite_code_response.get("success") and invite_code_response.get("data"):
                invite_data = invite_code_response.get("data", [])
                if invite_data and len(invite_data) > 0:
                    invite_code = invite_data[0].get("code")
                    enabled = invite_data[0].get("enabled", False)
                    
                    if invite_code and enabled:
                        # Save the invite code to database for future use (preserve existing auth_token)
                        existing_account = await self.db.get_account(self.private_key)
                        current_auth_token = existing_account.get("auth_token") if existing_account else None
                        await self.db.save_account(self.private_key, auth_token=current_auth_token, ref_code=invite_code)
                        logger.success(f"Generated invite code: {invite_code}", self.api.eth_address)
                    else:
                        logger.warning(f"Invite code disabled or invalid: {invite_code}", self.api.eth_address)
                else:
                    logger.warning("No invite code data in response", self.api.eth_address)
            else:
                logger.warning("Failed to get invite code from dedicated endpoint", self.api.eth_address)
            
            # Generate and save WebSocket authentication message
            websocket_auth_message = await self._generate_websocket_auth_message()
            if websocket_auth_message:
                await self.db.save_websocket_auth_message(self.private_key, websocket_auth_message)
                logger.debug("WebSocket auth message saved to database", self.api.eth_address)
            
            return True
            
        except Exception as e:
            logger.error(f"Registration attempt failed: {e}", self.api.eth_address)
            return False
        finally:
            await self.api.close()
    
    async def _handle_registration_failure(self) -> bool:
        """Handle registration failure with delay and proxy rotation"""
        
        self.attempt_count += 1
        max_attempts = self.settings.retry_max_attempts
        
        # If we haven't exhausted attempts yet, use regular retry delay
        if self.attempt_count < max_attempts:
            delay_seconds = max(self.settings.retry_delay, 5)  # Minimum 5 seconds for registration
            logger.warning(f"Registration failed (attempt {self.attempt_count}/{max_attempts}), waiting {delay_seconds} seconds...", self.api.eth_address)
            
            for remaining in range(delay_seconds, 0, -1):
                if not self.running:
                    return False
                await asyncio.sleep(1)
            
            return True
        
        # We've exhausted all attempts with current proxy
        if not self.settings.proxy_rotation_enabled:
            logger.info(f"Max attempts ({max_attempts}) reached, but proxy rotation disabled. Stopping registration.", self.api.eth_address)
            return False
        
        # Try to get next proxy
        new_proxy = self.proxy_rotator.get_next_proxy(self.api.eth_address)
        if new_proxy == self.proxy:
            logger.warning("No alternative proxy available, stopping registration", self.api.eth_address)
            return False
        
        # Update proxy and reset attempt count
        self.proxy = new_proxy
        self.attempt_count = 0
        logger.info(f"Max attempts reached, switching to new proxy for registration", self.api.eth_address)
        
        # Create new API instance with new proxy
        await self.api.close()
        
        # Wait 2 seconds to prevent cdata errors
        await asyncio.sleep(2)
        
        try:
            self.api = SixpenceAPI(self.private_key, self.proxy)
            logger.debug("New API instance created successfully with new proxy", self.api.eth_address)
        except Exception as e:
            logger.error(f"Failed to create new API instance: {e}", self.api.eth_address)
            # If we can't create new API instance, stop registration
            return False
        
        return True

    
    async def _generate_websocket_auth_message(self) -> Optional[str]:
        """Generate WebSocket authentication message"""
        try:
            # Get fresh nonce for WebSocket authentication
            if not await self.api.get_nonce():
                logger.error("Failed to get nonce for WebSocket auth message", self.api.eth_address)
                return None
            
            # Generate WebSocket payload
            websocket_payload = self.api.generate_payload(websocket=True)
            
            # Create the full authentication message
            auth_message = {
                "type": "extension_auth",
                "data": websocket_payload
            }
            
            # Convert to JSON string for storage
            return json.dumps(auth_message, separators=(',', ':'))
        except Exception as e:
            logger.error(f"Failed to generate WebSocket auth message: {e}", self.api.eth_address)
            return None
    
    async def _get_ref_code(self) -> Optional[str]:
        """Get referral code from config or database"""
        from app.config.settings import get_settings
        
        settings = get_settings()
        
        if settings.use_static_ref_code:
            return settings.static_ref_code
        else:
            # Get random ref code from database
            ref_code = await self.db.get_random_ref_code()
            return ref_code if ref_code else settings.static_ref_code  # Fallback
    
    async def _process_register_companion(self) -> None:
        """Process companion registration"""
        try:
            # Get egg info first
            egg_info = await self.api.get_egg_info()
            
            if egg_info and egg_info.get("msg") == "ok" and egg_info.get("data"):
                # Get the first available egg ID
                egg_id = egg_info["data"][0]["id"]
                
                result = await self.api.register_companion(egg_id)
                
                if result and result.get("success"):
                    logger.success("Companion registered successfully", self.api.eth_address)
                else:
                    logger.warning("Failed to register companion", self.api.eth_address)
            else:
                logger.warning("Failed to get egg info", self.api.eth_address)
        except Exception as e:
            logger.error(f"Companion registration error: {e}", self.api.eth_address)