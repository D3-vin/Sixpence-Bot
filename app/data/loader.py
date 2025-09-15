import os
from typing import List
from itertools import cycle

from app.utils.logging import get_logger

logger = get_logger()


def load_accounts(file_name: str) -> List[str]:
    """Load private keys from file"""
    file_path = f"config/data/{file_name}"
    
    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        accounts = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and line.startswith('0x'):
                accounts.append(line)
        
        logger.info(f"Loaded {len(accounts)} accounts from {file_name}")
        return accounts
        
    except Exception as e:
        logger.error(f"Error loading accounts from {file_name}: {e}")
        return []


def load_proxies() -> List[str]:
    """Load proxies from proxy.txt"""
    file_path = "config/data/proxy.txt"
    
    if not os.path.exists(file_path):
        logger.error(f"Proxy file not found: {file_path}")
        raise FileNotFoundError(f"Proxy file is required: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        proxies = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                # Ensure proxy has proper format
                if not line.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
                    line = f"http://{line}"
                proxies.append(line)
        
        if not proxies:
            raise ValueError("No valid proxies found in proxy file")
        
        logger.debug(f"Loaded {len(proxies)} proxies")
        return proxies
        
    except Exception as e:
        logger.error(f"Error loading proxies: {e}")
        raise


def get_proxy_for_account(proxies: List[str], account_index: int) -> str:
    """Get proxy for specific account"""
    if not proxies:
        raise ValueError("Proxies are required but no proxies loaded")
    
    proxy_cycle = cycle(proxies)
    # Skip to the appropriate proxy for this account
    for _ in range(account_index):
        next(proxy_cycle)
    
    return next(proxy_cycle)


def load_twitter_tokens() -> List[str]:
    """Load Twitter auth tokens from twitter_token.txt"""
    file_path = "config/data/twitter_token.txt"
    
    if not os.path.exists(file_path):
        logger.warning(f"Twitter tokens file not found: {file_path}")
        return []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        tokens = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                tokens.append(line)
        
        logger.info(f"Loaded {len(tokens)} Twitter tokens")
        return tokens
        
    except Exception as e:
        logger.error(f"Error loading Twitter tokens: {e}")
        return []