"""
HTTP API client for Sixpence
All HTTP requests (GET/POST) to the site
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Union, Literal
from uuid import uuid4

from curl_cffi.requests import AsyncSession
from eth_account import Account as EthAccount
from eth_account.messages import encode_defunct
from eth_utils.conversions import to_hex

from app.utils.logging import get_logger

logger = get_logger()


class APIError(Exception):
    """API error exception"""
    pass


class SessionBlocked(Exception):
    """Session blocked exception"""
    pass


class ServerTimeout(Exception):
    """Server timeout exception"""
    pass


class SixpenceAPI:
    """Sixpence API client for all HTTP requests"""
    
    API_URL = "https://us-central1-openoracle-de73b.cloudfunctions.net/new_backend_apis/api/service"
    
    def __init__(self, private_key: str, proxy: Optional[str] = None):
        self.private_key = private_key
        self.proxy = proxy
        self.session = self._create_session()
        self.eth_address = self._get_eth_address()
        self.nonce: Optional[str] = None
        self.access_token: Optional[str] = None
        
    def _create_session(self) -> AsyncSession:
        """Create HTTP session with error protection"""
        try:
            session = AsyncSession(
                impersonate="chrome136",
                verify=False,
                timeout=30
            )
            
            session.headers.update({
                "Accept": "application/json, text/plain, */*",
                "Origin": "chrome-extension://bcakokeeafaehcajfkajcpbdkfnoahlh",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-Storage-Access": "active",
                "Accept-Language": "en-US,en;q=0.9",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
            })
            
            if self.proxy:
                session.proxies = {"http": self.proxy, "https": self.proxy}
            
            return session
        except Exception as e:
            logger.error(f"Failed to create session: {e}", self.eth_address if hasattr(self, 'eth_address') else 'unknown')
            raise
    
    def _get_eth_address(self) -> str:
        """Get Ethereum address from private key"""
        account = EthAccount.from_key(self.private_key)
        return account.address
    
    async def _auto_login(self) -> None:
        """Automatic login when token expires"""
        await self.get_nonce()
        await self.login()
    
    async def _make_request(
        self,
        endpoint: str,
        method: Literal["GET", "POST"] = "GET",
        data: Optional[Dict] = None,
        auth_required: bool = True
    ) -> Optional[Union[Dict[str, Any], list, str]]:
        """Simple unified request method"""
        # Ensure session exists
        if not self.session:
            self.session = self._create_session()
        
        # Set headers
        headers = {"Content-Type": "application/json"}
        if auth_required and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        elif not auth_required:
            headers["Authorization"] = "Bearer null"
            
        # Special handling for nonce requests
        if "nonce" in endpoint:
            headers["Authorization"] = "Bearer null"
            if "Origin" in self.session.headers:
                del self.session.headers["Origin"]
        
        self.session.headers.update(headers)
        
        try:
            # Make request
            url = f"{self.API_URL}{endpoint}"
            if method == "POST":
                response = await self.session.post(url, json=data)
            else:
                response = await self.session.get(url)
            
            response.raise_for_status()
            
            try:
                result = response.json()
                # Auto-retry on 401 if we have auth
                if response.status_code == 401 and auth_required and self.access_token:
                    await self._auto_login()
                    return await self._make_request(endpoint, method, data, auth_required)
                return result
            except json.JSONDecodeError:
                return response.text
                
        except Exception as e:
            logger.debug(f"Request failed: {e}")
            return None
    
    def generate_payload(self, websocket: bool = False) -> Dict[str, Any]:
        """Generate payload for login request"""
        if not self.nonce:
            # This should be called after get_nonce
            raise ValueError("Nonce not available. Call get_nonce first.")
        
        # Use different Chain ID for WebSocket vs HTTP API
        chain_id = "1" if websocket else "42000"
        
        # Generate SIWE message format
        issued_at = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        message = (
            f"bcakokeeafaehcajfkajcpbdkfnoahlh wants you to sign in with your Ethereum account:\n"
            f"{self.eth_address}\n\n"
            f"By signing, you are proving you own this wallet and logging in. This does not initiate a transaction or cost any fees.\n\n"
            f"URI: chrome-extension://bcakokeeafaehcajfkajcpbdkfnoahlh\n"
            f"Version: 1\n"
            f"Chain ID: {chain_id}\n"
            f"Nonce: {self.nonce}\n"
            f"Issued At: {issued_at}"
        )
        
        # Sign the message
        encoded_message = encode_defunct(text=message)
        account = EthAccount.from_key(self.private_key)
        signed_message = account.sign_message(encoded_message)
        signature = to_hex(signed_message.signature)
        
        if websocket:
            return {
                "userId": self.eth_address,
                "message": message,
                "signature": signature
            }
        
        return {
            "message": message,
            "signature": signature
        }
    
    async def get_nonce(self) -> bool:
        """Get nonce for authentication"""
        result = await self._make_request(f"/{self.eth_address}/nonce??", auth_required=False)
        if isinstance(result, dict) and result.get("success"):
            data = result.get("data", {})
            self.nonce = data.get("nonce")
            if self.nonce:
                return True
        return False
    
    async def login(self) -> bool:
        """User login with signed message"""
        if not self.nonce and not await self.get_nonce():
            return False
            
        payload = self.generate_payload()
        result = await self._make_request("/login", "POST", payload, auth_required=False)
        
        if result and isinstance(result, dict) and result.get("success"):
            data = result.get("data", {})
            token = data.get("token")
            if token:
                self.access_token = token
                logger.success("Login successful", self.eth_address)
                return True
        return False
    
    async def user_info(self) -> Optional[Dict[str, Any]]:
        """Get user information"""
        result = await self._make_request("/userInfo?")
        return result if isinstance(result, dict) else None
    
    async def bind_invite(self, ref_code: str) -> bool:
        """Bind referral code"""
        data = {"inviteCode": ref_code}
        result = await self._make_request("/inviteBind", "POST", data)
        
        if isinstance(result, dict) and result.get("success"):
            logger.success(f"Referral code {ref_code} bound", self.eth_address)
            return True
        return False
    
    async def get_egg_info(self) -> Optional[Dict[str, Any]]:
        """Get available egg information"""
        result = await self._make_request("/getEggInfo?")
        return result if isinstance(result, dict) else None
    
    async def get_invite_code(self) -> Optional[Dict[str, Any]]:
        """Get generated invite code after registration"""
        result = await self._make_request("/getInviteCode?")
        return result if isinstance(result, dict) else None
    
    async def register_companion(self, egg_id: str) -> Optional[Dict[str, Any]]:
        """Register companion with egg ID"""
        data = {"eggInfoId": egg_id, "name": "sixpenceai"}
        result = await self._make_request("/registerCompanion", "POST", data)
        return result if isinstance(result, dict) else None
    
    async def close(self) -> None:
        """Close session safely"""
        if self.session:
            try:
                await self.session.close()
            except (AttributeError, Exception) as e:
                # Fallback for different curl_cffi versions or other session errors
                logger.debug(f"Session close error (safe to ignore): {e}", self.eth_address)
            finally:
                self.session = None
                self.access_token = None
                self.nonce = None