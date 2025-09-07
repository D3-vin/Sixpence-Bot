"""
Proxy rotation utility for Sixpence
Handles proxy switching for persistent farming
"""

import random
from typing import List, Optional
from app.data.loader import load_proxies
from app.utils.logging import get_logger

logger = get_logger()


class ProxyRotator:
    """Handle proxy rotation for farming persistence"""
    
    def __init__(self, current_proxy: Optional[str] = None):
        self.current_proxy = current_proxy
        self.used_proxies = set()
        if current_proxy:
            self.used_proxies.add(current_proxy)
    
    def get_next_proxy(self, eth_address: Optional[str] = None) -> Optional[str]:
        """Get next available proxy"""
        proxies = load_proxies()
        if not proxies:
            logger.warning("No proxies available for rotation", eth_address)
            return None
        
        # Filter out already used proxies
        available_proxies = [p for p in proxies if p not in self.used_proxies]
        
        # If all proxies used, reset and start over
        if not available_proxies:
            logger.info("All proxies used, resetting rotation", eth_address)
            self.used_proxies.clear()
            if self.current_proxy:
                self.used_proxies.add(self.current_proxy)
            available_proxies = [p for p in proxies if p not in self.used_proxies]
        
        if not available_proxies:
            logger.warning("No alternative proxies available", eth_address)
            return self.current_proxy
        
        # Select random proxy from available ones
        new_proxy = random.choice(available_proxies)
        self.used_proxies.add(new_proxy)
        
        logger.debug(f"Switching proxy: {self._mask_proxy(self.current_proxy)} → {self._mask_proxy(new_proxy)}", eth_address)
        self.current_proxy = new_proxy
        
        return new_proxy
    
    def _mask_proxy(self, proxy: Optional[str]) -> str:
        """Mask proxy for logging"""
        if not proxy:
            return "None"
        
        # Extract host from proxy URL
        try:
            if "://" in proxy:
                parts = proxy.split("://")[1]
            else:
                parts = proxy
            
            if "@" in parts:
                parts = parts.split("@")[1]
            
            host = parts.split(":")[0]
            return f"{host[:3]}***{host[-3:]}" if len(host) > 6 else f"{host[:2]}***"
        except:
            return "proxy***"
    
    def reset(self):
        """Reset used proxies tracking"""
        self.used_proxies.clear()
        if self.current_proxy:
            self.used_proxies.add(self.current_proxy)