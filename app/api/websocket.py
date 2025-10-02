"""
WebSocket client for Sixpence
Handles WebSocket connections and farming
"""

import asyncio
import base64
import json
import secrets
import time
from typing import Dict, Any, Optional

import aiohttp
from aiohttp import ClientSession, WSMsgType
from aiohttp_socks import ProxyConnector

from app.utils.logging import get_logger
from app.utils.retry import retry_async, _simplify_error_message
from app.utils.shutdown import is_shutdown_requested
from app.api.client import SixpenceAPI
from app.data.database import get_db

logger = get_logger()


class SixpenceWebSocket:
    """WebSocket client for Sixpence farming"""
    
    WSS_URL = "wss://ws.sixpence.ai/"
    HEARTBEAT_INTERVAL = 30
    RECEIVE_TIMEOUT = 45
    AUTH_RESPONSE_WAIT = 2
    
    def __init__(self, private_key: str, auth_token: str, proxy: Optional[str] = None):
        self.private_key = private_key
        self.auth_token = auth_token
        self.proxy = proxy
        self.running = False
        self.websocket = None
        self.session = None
        self.wss_token = None  # WebSocket-specific token
        self.db = get_db()
        self._session_error = False
        
        # Get eth address for logging
        temp_api = SixpenceAPI(private_key)
        self.eth_address = temp_api.eth_address
        

        
    async def connect(self) -> bool:
        """Connect to WebSocket with retry logic"""
        return await retry_async(
            self._connect_attempt,
            eth_address=self.eth_address,
            operation_name="WebSocket connection"
        ) or False
    
    async def connect_single_attempt(self) -> bool:
        """Single WebSocket connection attempt without retry"""
        try:
            return await self._connect_attempt()
        except Exception:
            return False
    
    async def _connect_attempt(self) -> bool:
        """Single WebSocket connection attempt"""
        try:
            # Generate unique WebSocket key for each connection
            websocket_key = base64.b64encode(secrets.token_bytes(16)).decode()
            
            # Headers for WebSocket connection
            headers = {
                "Origin": "chrome-extension://bcakokeeafaehcajfkajcpbdkfnoahlh",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
                "Pragma": "no-cache",
                "Cache-Control": "no-cache",
                "Upgrade": "websocket",
                "Sec-WebSocket-Version": "13",
                "Sec-WebSocket-Key": websocket_key,
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits",
                "Accept-Language": "en-US;q=0.8,en;q=0.7"
            }
            
            # Create session with proxy support
            connector = ProxyConnector.from_url(self.proxy) if self.proxy else None
            self.session = ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=30)
            )
            
            # Connect to WebSocket with proxy support
            self.websocket = await self.session.ws_connect(
                self.WSS_URL,
                headers=headers
            )
            logger.success("WebSocket connected", self.eth_address)
            return True
            
        except Exception as e:
            simplified_error = _simplify_error_message(e)
            logger.debug(f"WebSocket connection failed: {simplified_error}", self.eth_address)
            # Cleanup on connection failure
            if self.session:
                await self.session.close()
                self.session = None
            raise  # Re-raise to trigger retry
    
    async def authenticate(self) -> bool:
        """Authenticate WebSocket connection with retry logic"""
        return await retry_async(
            self._authenticate_attempt,
            eth_address=self.eth_address,
            operation_name="WebSocket authentication"
        ) or False
    
    async def authenticate_single_attempt(self) -> bool:
        """Single WebSocket authentication attempt without retry"""
        try:
            return await self._authenticate_attempt()
        except Exception:
            return False
    
    async def _authenticate_attempt(self) -> bool:
        """Single WebSocket authentication attempt"""
        try:
            if not self.websocket:
                logger.error("WebSocket not connected", self.eth_address)
                return False
                
            # Get WebSocket auth message from database
            websocket_auth_message = await self.db.get_websocket_auth_message(self.private_key)
            
            if websocket_auth_message:
                # Send the saved authentication message
                #print(f'mess {websocket_auth_message}')
                await self.websocket.send_str(websocket_auth_message)
                logger.debug("WebSocket authentication sent from saved message", self.eth_address)
                return True
            else:
                logger.warning("No saved WebSocket auth message found, generating new one", self.eth_address)
                # Generate new auth message and save it to database
                # Import here to avoid circular imports
                from app.api.client import SixpenceAPI
                
                # Create a temporary API instance to generate WebSocket payload
                api = SixpenceAPI(self.private_key)
                await api.get_nonce()  # Get fresh nonce
                
                auth_message = {
                    "type": "extension_auth",
                    "data": api.generate_payload(websocket=True)
                }
                
                # Convert to JSON string
                auth_message_str = json.dumps(auth_message, separators=(',', ':'))
                
                # Send the authentication message
                await self.websocket.send_str(auth_message_str)
                logger.info("WebSocket authentication sent (generated)", self.eth_address)
                
                # Save the new auth message to database for future use
                if await self.db.save_websocket_auth_message(self.private_key, auth_message_str):
                    logger.debug("New WebSocket auth message saved to database", self.eth_address)
                else:
                    logger.warning("Failed to save new WebSocket auth message", self.eth_address)
                
                await api.close()  # Clean up temporary API instance
                return True
        except Exception as e:
            simplified_error = _simplify_error_message(e)
            logger.error(f"WebSocket authentication failed: {simplified_error}", self.eth_address)
            raise  # Re-raise to trigger retry
    
    async def _send_heartbeat(self) -> bool:
        """Send single heartbeat message"""
        if not self.websocket:
            return False
        if not self.wss_token:
            logger.warning("No WebSocket token for heartbeat", self.eth_address)
            return False
        try:
            heartbeat = {
                "type": "extension_heartbeat",
                "token": self.wss_token,
                "address": self.eth_address,
                "taskEnable": False
            }
            await self.websocket.send_str(json.dumps(heartbeat))
            logger.debug("Heartbeat sent", self.eth_address)
            return True
        except (aiohttp.ClientConnectionError, ConnectionResetError) as e:
            simplified_error = _simplify_error_message(e)
            logger.error(f"Heartbeat connection error: {simplified_error}", self.eth_address)
            return False
        except Exception as e:
            logger.error(f"Heartbeat failed: {e}", self.eth_address)
            return False
    
    async def _handle_message(self, data: Dict[str, Any]) -> None:
        """Handle incoming WebSocket message"""
        msg_type = data.get("type", "")
        
        if msg_type == "extension_auth":
            # Store the WebSocket token for heartbeats
            self.wss_token = data.get("data", {}).get("token")
            logger.success("WebSocket authentication successful", self.eth_address)
        elif msg_type == "extension_user_msg":
            # Handle points update
            msg_data = data.get("data", {})
            total_points = msg_data.get("currentPoints", 0)
            today_points = msg_data.get("currentDayPoints", 0)
            logger.success(f"Earning refreshed - Today {today_points:.2f} PTS, Total {total_points:.2f} PTS", self.eth_address)
        elif msg_type == "extension_heartbeat":
            logger.debug("Heartbeat acknowledged", self.eth_address)
        elif msg_type == "error":
            error_msg = data.get("message", "Unknown error")
            logger.error(f"WebSocket error: {error_msg}", self.eth_address)
        else:
            logger.debug(f"Unknown message type: {msg_type}", self.eth_address)
    
    async def start_farming_session(self) -> bool:
        """Start farming session (connection and auth should be done already)

        Returns True if session ended normally, False if connection was lost.
        """
        self.running = True
        self._session_error = False
        logger.debug("Starting farming session...", self.eth_address)

        last_heartbeat = time.monotonic()

        try:
            # Give the server a moment to respond with auth data
            await asyncio.sleep(self.AUTH_RESPONSE_WAIT)

            if self.wss_token:
                if not await self._send_heartbeat():
                    self._session_error = True
                    return False
                last_heartbeat = time.monotonic()

            while self.running and self.websocket:
                if is_shutdown_requested():
                    break

                try:
                    msg = await asyncio.wait_for(
                        self.websocket.receive(),
                        timeout=self.RECEIVE_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    if not self.wss_token:
                        logger.debug("Waiting for WebSocket auth response", self.eth_address)
                        continue
                    if not await self._send_heartbeat():
                        self._session_error = True
                        break
                    last_heartbeat = time.monotonic()
                    continue
                except (aiohttp.ClientConnectionError, ConnectionResetError) as e:
                    simplified_error = _simplify_error_message(e)
                    logger.error(f"Connection error while receiving: {simplified_error}", self.eth_address)
                    self._session_error = True
                    break
                except Exception as e:
                    logger.error(f"Message receive error: {e}", self.eth_address)
                    self._session_error = True
                    break

                msg_type = None
                if msg.type == WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    msg_type = data.get("type")
                    await self._handle_message(data)
                elif msg.type == WSMsgType.BINARY:
                    logger.debug("Binary WebSocket message received", self.eth_address)
                elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED):
                    logger.warning("WebSocket connection closed by server", self.eth_address)
                    self._session_error = True
                    break
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {self.websocket.exception()}", self.eth_address)
                    self._session_error = True
                    break

                if msg_type == "extension_auth" and self.wss_token:
                    last_heartbeat = time.monotonic()

                if self.wss_token and (time.monotonic() - last_heartbeat) >= self.HEARTBEAT_INTERVAL:
                    if not await self._send_heartbeat():
                        self._session_error = True
                        break
                    last_heartbeat = time.monotonic()

        except asyncio.CancelledError:
            logger.info("Farming session cancelled", self.eth_address)
        except Exception as e:
            logger.error(f"Farming session error: {e}", self.eth_address)
            self._session_error = True
            raise  # Re-raise to let farming process handle it
        finally:
            self.running = False
            await self.disconnect()

        return not self._session_error
    
    async def start_farming(self) -> None:
        """Start farming process with retry logic"""
        # Initial connection with retry
        if not await self.connect():
            logger.error("Failed to establish WebSocket connection after retries", self.eth_address)
            return

        # Authentication with retry
        if not await self.authenticate():
            logger.error("Failed to authenticate WebSocket after retries", self.eth_address)
            await self.disconnect()
            return

        try:
            await self.start_farming_session()
        finally:
            if self.running:
                self.running = False
    
    async def disconnect(self) -> None:
        """Disconnect WebSocket"""
        self.running = False
        try:
            if self.websocket:
                await self.websocket.close()
                self.websocket = None
        except Exception:
            pass  # Ignore errors during shutdown
        try:
            if self.session:
                await self.session.close()
                self.session = None
        except Exception:
            pass  # Ignore errors during shutdown
        self.wss_token = None
        logger.info("WebSocket disconnected", self.eth_address)