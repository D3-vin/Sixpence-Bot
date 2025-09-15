"""
Twitter OAuth2 integration for Sixpence
Handles Twitter account binding using OAuth2 flow
"""

import asyncio
import base64
import hashlib
import json
import os
import uuid
from typing import Optional, Union

from aiohttp import ClientSession, ClientTimeout
from aiohttp_socks import ProxyConnector

from app.api.client import SixpenceAPI
from app.data.database import get_db
from app.utils.logging import get_logger
from app.utils.proxy_rotation import ProxyRotator
from app.config.settings import get_settings

# Twitter API imports (required)
from Jam_Twitter_API.account_sync import TwitterAccountSync
from Jam_Twitter_API.errors import TwitterAccountSuspended, TwitterError, IncorrectData, RateLimitError

TWITTER_API_AVAILABLE = True

logger = get_logger()


class TwitterBindingProcess:
    """Handle Twitter OAuth2 binding process"""
    
    def __init__(self, private_key: str, twitter_tokens: list, proxy: Optional[str] = None):
        self.private_key = private_key
        self.twitter_tokens = twitter_tokens  # List of available tokens
        self.current_token_index = 0  # Track current token
        self.proxy = proxy
        self.api = SixpenceAPI(private_key, proxy)
        self.db = get_db()
        self.settings = get_settings()
        self.proxy_rotator = ProxyRotator(proxy)
        self.running = True
        self.attempt_count = 0
        self.token_already_linked = False  # Track if current token is already linked
        
        # Twitter API is now required, no need to check availability
    
    @property
    def current_twitter_token(self) -> Optional[str]:
        """Get current Twitter token"""
        if self.current_token_index < len(self.twitter_tokens):
            return self.twitter_tokens[self.current_token_index]
        return None
    
    def try_next_token(self) -> bool:
        """Move to next available token"""
        self.current_token_index += 1
        self.token_already_linked = False
        self.attempt_count = 0  # Reset attempts for new token
        return self.current_token_index < len(self.twitter_tokens)
    
    async def process(self) -> bool:
        """Run Twitter binding process with retry and proxy rotation"""
        # Twitter API is now required, no need to check availability
        
        max_attempts = self.settings.retry_max_attempts
        
        while self.current_token_index < len(self.twitter_tokens):
            try:
                # Ensure database is initialized
                await self.db.init()
                
                current_token = self.current_twitter_token
                if not current_token:
                    logger.error("No more Twitter tokens available", self.api.eth_address)
                    return False
                    
                logger.info(f"Starting Twitter binding with token {self.current_token_index + 1}/{len(self.twitter_tokens)} (attempt {self.attempt_count + 1}/{max_attempts})", self.api.eth_address)
                
                # Try Twitter binding using Jam_Twitter_API
                binding_result = await self._attempt_twitter_binding()
                if binding_result is True:
                    logger.success("Twitter binding completed successfully", self.api.eth_address)
                    return True
                elif binding_result == "already_linked":
                    # This token is already linked, try next token
                    logger.warning(f"Token {self.current_token_index + 1} already linked, trying next token", self.api.eth_address)
                    if not self.try_next_token():
                        logger.error("All Twitter tokens already linked", self.api.eth_address)
                        return False
                    continue  # Try next token immediately
                
                # Binding failed for other reasons, handle failure
                if not await self._handle_binding_failure():
                    # Try next token if available
                    if self.try_next_token():
                        continue
                    return False
                    
            except Exception as e:
                logger.error(f"Twitter binding failed: {e}", self.api.eth_address)
                if not await self._handle_binding_failure():
                    # Try next token if available  
                    if self.try_next_token():
                        continue
                    return False
        
        logger.error(f"Twitter binding failed after {max_attempts} attempts", self.api.eth_address)
        return False
    
    async def _attempt_twitter_binding(self) -> Union[bool, str]:
        """Single Twitter binding attempt using Jam_Twitter_API"""
        try:
            # First, get OAuth URL from Sixpence backend
            oauth_url = await self._get_sixpence_oauth_url()
            if not oauth_url:
                logger.error("Failed to get OAuth URL from Sixpence", self.api.eth_address)
                return False
            
            # Parse OAuth parameters from the URL
            oauth_params = self._parse_oauth_url(oauth_url)
            if not oauth_params:
                logger.error("Failed to parse OAuth URL parameters", self.api.eth_address)
                return False
            
            # Initialize Twitter account sync
            proxy_str = self.proxy if self.proxy else ""
            
            current_token = self.current_twitter_token
            if not current_token:
                logger.error("No more Twitter tokens available", self.api.eth_address)
                return False
            
            account = TwitterAccountSync.run(
                auth_token=current_token, 
                proxy=proxy_str, 
                setup_session=True
            )
            
            # Bind account using OAuth2 parameters
            bind_result = account.bind_account_v2(oauth_params)
            
            if bind_result:
                logger.debug(f"Got OAuth code: {bind_result}", self.api.eth_address)
                
                # Complete OAuth2 flow by calling callback URL
                callback_success = await self._complete_oauth_callback(bind_result, oauth_params["state"])
                
                if callback_success is True:
                    logger.success("Twitter account bound successfully", self.api.eth_address)
                    return True
                elif callback_success == "already_linked":
                    # Return special status for already linked accounts
                    return "already_linked"
                else:
                    logger.debug("Failed to complete OAuth callback", self.api.eth_address)
                    return False
            else:
                logger.error("Failed to bind Twitter account", self.api.eth_address)
                return False
                
        except TwitterAccountSuspended as error:
            logger.error(f"Twitter account suspended: {error}", self.api.eth_address)
            return False
        except TwitterError as error:
            error_msg = getattr(error, 'error_message', str(error))
            error_code = getattr(error, 'error_code', 'unknown')
            logger.error(f"Twitter error: {error_msg} | {error_code}", self.api.eth_address)
            return False
        except IncorrectData as error:
            logger.error(f"Incorrect data: {error}", self.api.eth_address)
            return False
        except RateLimitError as error:
            logger.error(f"Rate limit exceeded: {error}", self.api.eth_address)
            return False

            
        except Exception as e:
            logger.error(f"Twitter binding attempt failed: {e}", self.api.eth_address)
            return False
    
    async def _handle_binding_failure(self) -> bool:
        """Handle binding failure with delay and proxy rotation"""
        
        self.attempt_count += 1
        max_attempts = self.settings.retry_max_attempts
        
        # If we haven't exhausted attempts yet, use regular retry delay
        if self.attempt_count < max_attempts:
            delay_seconds = max(self.settings.retry_delay, 5)  # Minimum 5 seconds for binding
            logger.warning(f"Twitter binding failed (attempt {self.attempt_count}/{max_attempts}), waiting {delay_seconds} seconds...", self.api.eth_address)
            
            for remaining in range(delay_seconds, 0, -1):
                if not self.running:
                    return False
                await asyncio.sleep(1)
            
            return True
        
        # We've exhausted all attempts with current proxy
        if not self.settings.proxy_rotation_enabled:
            logger.info(f"Max attempts ({max_attempts}) reached, but proxy rotation disabled. Stopping Twitter binding.", self.api.eth_address)
            return False
        
        # Try to get next proxy
        new_proxy = self.proxy_rotator.get_next_proxy(self.api.eth_address)
        if new_proxy == self.proxy:
            logger.warning("No alternative proxy available, stopping Twitter binding", self.api.eth_address)
            return False
        
        # Update proxy and reset attempt count
        self.proxy = new_proxy
        self.attempt_count = 0
        logger.info(f"Max attempts reached, switching to new proxy for Twitter binding", self.api.eth_address)
        
        # Create new API instance with new proxy
        await self.api.close()
        
        # Wait 2 seconds to prevent connection errors
        await asyncio.sleep(2)
        
        try:
            self.api = SixpenceAPI(self.private_key, self.proxy)
            logger.debug("New API instance created successfully with new proxy", self.api.eth_address)
        except Exception as e:
            logger.error(f"Failed to create new API instance: {e}", self.api.eth_address)
            # If we can't create new API instance, stop binding
            return False
        
        return True
    
    async def _complete_oauth_callback(self, code: str, state: str) -> Union[bool, str]:
        """Complete OAuth2 callback to finish Twitter binding"""
        try:
            # Construct callback URL with code and state
            callback_url = f"https://backend.sixpence.ai/api/service/oauth2/callback?state={state}&code={code}"
            
            # Set up headers similar to other API requests
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors", 
                "Sec-Fetch-Site": "same-site",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
            }
            
            # Set up proxy connector if proxy is available
            connector = ProxyConnector.from_url(self.proxy) if self.proxy else None
            
            # Disable auto redirects to check redirect location manually
            async with ClientSession(connector=connector, timeout=ClientTimeout(total=30)) as session:
                async with session.get(callback_url, headers=headers, ssl=False, allow_redirects=False) as response:
                    
                    # Check if response is a redirect (302 Found)
                    if response.status == 302:
                        redirect_location = response.headers.get('Location', '')
                        logger.debug(f"Redirect location: {redirect_location}", self.api.eth_address)
                        
                        # Check for successful binding
                        if "twitter-connect.openlayer.tech/?success=" in redirect_location:
                            # Extract referral code if present
                            if "referralCode=" in redirect_location:
                                referral_code = redirect_location.split("referralCode=")[1]
                                logger.success(f"Twitter binding successful! Referral code: {referral_code}", self.api.eth_address)
                            else:
                                logger.success("Twitter binding successful!", self.api.eth_address)
                            return True
                        
                        # Check for binding failure
                        elif "twitter-connect.openlayer.tech/?error=" in redirect_location:
                            error_msg = redirect_location.split("error=")[1].replace("+", " ")
                            
                            # Check if Twitter account is already linked
                            if "already+been+linked" in redirect_location or "already been linked" in error_msg:
                                logger.warning(f"Twitter account already linked: {error_msg}", self.api.eth_address)
                                # Don't retry with different proxy for this specific error
                                return "already_linked"
                            else:
                                logger.error(f"Twitter binding failed: {error_msg}", self.api.eth_address)
                                return False
                        
                        else:
                            logger.debug(f"Unknown redirect location: {redirect_location}", self.api.eth_address)
                            return False
                    
                    # If not a redirect, check direct response
                    elif response.status == 200:
                        try:
                            result = await response.json()
                            if result.get("success"):
                                logger.success("OAuth callback completed successfully (direct response)", self.api.eth_address)
                                return True
                            else:
                                logger.error(f"OAuth callback failed: {result.get('msg', 'Unknown error')}", self.api.eth_address)
                                return False
                        except Exception:
                            # If not JSON, assume success
                            logger.success("OAuth callback completed (non-JSON response)", self.api.eth_address)
                            return True
                    
                    else:
                        logger.error(f"OAuth callback failed with status {response.status}", self.api.eth_address)
                        return False
                        
        except Exception as e:
            logger.error(f"Error completing OAuth callback: {e}", self.api.eth_address)
            return False
    
    async def _get_sixpence_oauth_url(self) -> Optional[str]:
        """Get Twitter OAuth2 URL from Sixpence backend"""
        try:
            # Get authentication token (from database or login)
            auth_token = await self._get_auth_token()
            if not auth_token:
                logger.error("Failed to get auth token", self.api.eth_address)
                return None
            
            # Set up headers for authenticated request
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Authorization": f"Bearer {auth_token}",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors", 
                "Sec-Fetch-Site": "same-site",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
            }
            
            # Set up proxy connector if proxy is available
            connector = ProxyConnector.from_url(self.proxy) if self.proxy else None
            
            async with ClientSession(connector=connector, timeout=ClientTimeout(total=30)) as session:
                async with session.get("https://backend.sixpence.ai/api/service/oauth2/twitter?", headers=headers, ssl=False) as response:
                    response.raise_for_status()
                    
                    if response.status == 200:
                        result = await response.json()
                        if result.get("success") and result.get("data", {}).get("url"):
                            oauth_url = result["data"]["url"]
                            logger.debug("Retrieved OAuth URL from Sixpence backend", self.api.eth_address)
                            return oauth_url
                        else:
                            logger.debug(f"Invalid response from Sixpence: {result}", self.api.eth_address)
                            return None
                    else:
                        logger.debug(f"Failed to get OAuth URL, status: {response.status}", self.api.eth_address)
                        return None
                        
        except Exception as e:
            logger.debug(f"Error getting OAuth URL from Sixpence: {e}", self.api.eth_address)
            return None
    
    def _parse_oauth_url(self, oauth_url: str) -> Optional[dict]:
        """Parse OAuth2 parameters from URL"""
        try:
            from urllib.parse import urlparse, parse_qs
            
            parsed = urlparse(oauth_url)
            params = parse_qs(parsed.query)
            
            # Extract required OAuth2 parameters
            oauth_params = {}
            
            # Get single values from query parameters
            param_mapping = {
                'response_type': 'response_type',
                'client_id': 'client_id', 
                'redirect_uri': 'redirect_uri',
                'state': 'state',
                'code_challenge': 'code_challenge',
                'code_challenge_method': 'code_challenge_method',
                'scope': 'scope'
            }
            
            for url_param, oauth_param in param_mapping.items():
                if url_param in params and len(params[url_param]) > 0:
                    oauth_params[oauth_param] = params[url_param][0]
            
            # Validate required parameters
            required_params = ['response_type', 'client_id', 'redirect_uri', 'scope', 'state']
            for param in required_params:
                if param not in oauth_params:
                    logger.error(f"Missing required OAuth parameter: {param}", self.api.eth_address)
                    return None
            
            logger.debug("Successfully parsed OAuth parameters from Sixpence URL", self.api.eth_address)
            return oauth_params
            
        except Exception as e:
            logger.error(f"Error parsing OAuth URL: {e}", self.api.eth_address)
            return None
    
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


async def bind_twitter_for_account(private_key: str, twitter_tokens: list, proxy: Optional[str] = None) -> bool:
    """Helper function to bind Twitter for a single account"""
    process = TwitterBindingProcess(private_key, twitter_tokens, proxy)
    return await process.process()