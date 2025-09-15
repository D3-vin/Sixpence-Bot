"""
Tortoise ORM database for Sixpence
Stores private keys, tokens, and referral codes
"""

import asyncio
import random
from typing import Optional, List, Dict, Any
from pathlib import Path

from tortoise import Tortoise, fields
from tortoise.models import Model
from tortoise.functions import Count

from app.utils.logging import get_logger

logger = get_logger()


class Account(Model):
    """Account model"""
    
    id = fields.IntField(pk=True)
    private_key = fields.CharField(max_length=66, unique=True, index=True)
    auth_token = fields.TextField(null=True)
    ref_code = fields.CharField(max_length=50, null=True)
    websocket_auth_message = fields.TextField(null=True)  # New field for WebSocket auth message
    created_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:  # type: ignore
        table = "accounts"
        
    def __str__(self):
        return f"Account({self.private_key[:10]}...)"


class SixpenceDatabase:
    """Tortoise ORM database manager for Sixpence"""
    
    def __init__(self, db_path: str = "data/sixpence.db"):
        self.db_path = db_path
        self._ensure_data_dir()
        self.initialized = False
    
    def _ensure_data_dir(self) -> None:
        """Ensure data directory exists"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
    
    async def init(self) -> None:
        """Initialize database connection"""
        if self.initialized:
            return
            
        try:
            await Tortoise.init(
                db_url=f"sqlite://{self.db_path}",
                modules={"models": ["app.data.database"]}
            )
            await Tortoise.generate_schemas()
            
            # Check if websocket_auth_message column exists, if not add it
            await self._ensure_websocket_auth_message_column()
            
            self.initialized = True
            logger.debug("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    async def _ensure_websocket_auth_message_column(self) -> None:
        """Ensure websocket_auth_message column exists in accounts table"""
        try:
            # Get database connection
            connection = Tortoise.get_connection("default")
            
            # Check if column exists by trying to query it
            try:
                await connection.execute_query("SELECT websocket_auth_message FROM accounts LIMIT 1")
                logger.debug("websocket_auth_message column already exists")
            except Exception:
                # Column doesn't exist, add it
                logger.info("Adding websocket_auth_message column to accounts table")
                await connection.execute_query(
                    "ALTER TABLE accounts ADD COLUMN websocket_auth_message TEXT NULL"
                )
                logger.success("websocket_auth_message column added successfully")
        except Exception as e:
            logger.warning(f"Failed to check/add websocket_auth_message column: {e}")
    
    async def close(self) -> None:
        """Close database connection"""
        if self.initialized:
            await Tortoise.close_connections()
            self.initialized = False
            logger.debug("Database connection closed")
    
    async def save_account(self, private_key: str, auth_token: Optional[str] = None, ref_code: Optional[str] = None, websocket_auth_message: Optional[str] = None, twitter_bound: Optional[bool] = None) -> bool:
        """Save account to database"""
        try:
            account, created = await Account.get_or_create(
                private_key=private_key,
                defaults={"auth_token": auth_token, "ref_code": ref_code, "websocket_auth_message": websocket_auth_message}
            )
            
            if not created:
                # Update existing account
                if auth_token is not None:
                    account.auth_token = auth_token
                if ref_code is not None:
                    account.ref_code = ref_code
                if websocket_auth_message is not None:
                    account.websocket_auth_message = websocket_auth_message
                # Twitter bound status is handled separately for now
                await account.save()
            
            return True
        except Exception as e:
            logger.error(f"Failed to save account: {e}")
            return False
    
    async def get_account(self, private_key: str) -> Optional[Dict[str, Any]]:
        """Get account by private key"""
        try:
            account = await Account.filter(private_key=private_key).first()
            if account:
                return {
                    "id": account.id,
                    "private_key": account.private_key,
                    "auth_token": account.auth_token,
                    "ref_code": account.ref_code,
                    "websocket_auth_message": account.websocket_auth_message,
                    "created_at": account.created_at
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get account: {e}")
            return None
    
    async def save_token(self, private_key: str, auth_token: str) -> bool:
        """Save auth token for account"""
        try:
            account, created = await Account.get_or_create(
                private_key=private_key,
                defaults={"auth_token": auth_token}
            )
            
            if not created:
                account.auth_token = auth_token
                await account.save()
            
            return True
        except Exception as e:
            logger.error(f"Failed to save token: {e}")
            return False
    
    async def get_token(self, private_key: str) -> Optional[str]:
        """Get auth token for account"""
        try:
            account = await Account.filter(private_key=private_key).first()
            return account.auth_token if account else None
        except Exception as e:
            logger.error(f"Failed to get token: {e}")
            return None
    
    async def save_websocket_auth_message(self, private_key: str, websocket_auth_message: str) -> bool:
        """Save WebSocket auth message for account"""
        try:
            account, created = await Account.get_or_create(
                private_key=private_key,
                defaults={"websocket_auth_message": websocket_auth_message}
            )
            
            if not created:
                account.websocket_auth_message = websocket_auth_message
                await account.save()
            
            return True
        except Exception as e:
            logger.error(f"Failed to save WebSocket auth message: {e}")
            return False
    
    async def get_websocket_auth_message(self, private_key: str) -> Optional[str]:
        """Get WebSocket auth message for account"""
        try:
            account = await Account.filter(private_key=private_key).first()
            return account.websocket_auth_message if account else None
        except Exception as e:
            logger.error(f"Failed to get WebSocket auth message: {e}")
            return None
    
    async def get_random_ref_code(self) -> Optional[str]:
        """Get random referral code from database"""
        try:
            # Get all accounts with ref codes
            accounts = await Account.filter(ref_code__isnull=False).all()
            if accounts:
                # Select random account from the list
                random_account = random.choice(accounts)
                return random_account.ref_code
            return None
        except Exception as e:
            logger.error(f"Failed to get random ref code: {e}")
            return None
    
    async def get_all_accounts(self) -> List[Dict[str, Any]]:
        """Get all accounts"""
        try:
            accounts = await Account.all()
            return [
                {
                    "id": account.id,
                    "private_key": account.private_key,
                    "auth_token": account.auth_token,
                    "ref_code": account.ref_code,
                    "websocket_auth_message": account.websocket_auth_message,
                    "created_at": account.created_at
                }
                for account in accounts
            ]
        except Exception as e:
            logger.error(f"Failed to get all accounts: {e}")
            return []
    
    async def get_accounts_count(self) -> int:
        """Get total count of accounts"""
        try:
            return await Account.all().count()
        except Exception as e:
            logger.error(f"Failed to get accounts count: {e}")
            return 0
    
    async def get_all_accounts_with_tokens(self) -> List[Dict[str, Any]]:
        """Get all accounts that have auth tokens"""
        try:
            accounts = await Account.filter(auth_token__isnull=False).all()
            return [
                {
                    "id": account.id,
                    "private_key": account.private_key,
                    "auth_token": account.auth_token,
                    "ref_code": account.ref_code,
                    "websocket_auth_message": account.websocket_auth_message,
                    "twitter_bound": False,  # Default to False for now, can be extended later
                    "created_at": account.created_at
                }
                for account in accounts
            ]
        except Exception as e:
            logger.error(f"Failed to get accounts with tokens: {e}")
            return []


# Global database instance
_db_instance: Optional[SixpenceDatabase] = None


def get_db() -> SixpenceDatabase:
    """Get global database instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = SixpenceDatabase()
    return _db_instance


async def init_database() -> None:
    """Initialize database"""
    db = get_db()
    await db.init()


async def close_database() -> None:
    """Close database"""
    db = get_db()
    await db.close()