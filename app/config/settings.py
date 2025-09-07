"""
Simple settings for Sixpence
Configuration management
"""

import os
import yaml
from typing import Optional, Dict, Any
from pathlib import Path

from app.utils.logging import get_logger

logger = get_logger()


class SixpenceSettings:
    """Simple settings manager"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = config_path
        self.data = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if not os.path.exists(self.config_path):
            logger.error(f"Config file not found: {self.config_path}")
            raise FileNotFoundError(f"Configuration file required: {self.config_path}")
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
                if not config_data:
                    raise ValueError("Config file is empty or invalid")
                return config_data
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            raise
    
    @property
    def registration_threads(self) -> int:
        """Number of threads for registration"""
        return self.data.get("threads", {}).get("registration", 5)
    
    @property
    def farming_threads(self) -> int:
        """Number of threads for farming"""
        return self.data.get("threads", {}).get("farming", 3)
    
    @property
    def threads(self) -> int:
        """Number of threads (backward compatibility)"""
        return self.registration_threads
    
    @property
    def logging_level(self) -> str:
        """Logging level"""
        return self.data.get("logging", {}).get("level", "INFO")
    
    @property
    def delay_min(self) -> int:
        """Minimum delay"""
        return self.data["delay_before_start"]["min"]
    
    @property
    def delay_max(self) -> int:
        """Maximum delay"""
        return self.data["delay_before_start"]["max"]
    
    @property
    def use_static_ref_code(self) -> bool:
        """Use static referral code"""
        return self.data["use_static_ref_code"]
    
    @property
    def static_ref_code(self) -> str:
        """Static referral code"""
        return self.data["sixpence_ref_code"]
    
    @property
    def retry_max_attempts(self) -> int:
        """Maximum retry attempts"""
        return self.data.get("retry", {}).get("max_attempts", 3)
    
    @property
    def retry_delay(self) -> int:
        """Retry delay in seconds"""
        return self.data.get("retry", {}).get("delay_seconds", 5)
    
    @property
    def retry_backoff_multiplier(self) -> float:
        """Retry backoff multiplier"""
        return self.data.get("retry", {}).get("backoff_multiplier", 2.0)
    
    @property
    def retry_rate_limit_delay(self) -> int:
        """Special delay for rate limit (429) errors"""
        return self.data.get("retry", {}).get("rate_limit_delay", 60)
    
    @property
    def farming_wait_seconds(self) -> int:
        """Wait time in seconds before retrying farming"""
        return self.data.get("retry", {}).get("farming_wait_seconds", 60)
    
    @property
    def proxy_rotation_enabled(self) -> bool:
        """Whether to enable proxy rotation on retry exhaustion"""
        return self.data.get("retry", {}).get("proxy_rotation", True)


# Global settings instance
_settings_instance: Optional[SixpenceSettings] = None


def get_settings() -> SixpenceSettings:
    """Get global settings instance"""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = SixpenceSettings()
    return _settings_instance