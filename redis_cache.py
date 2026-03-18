import redis
import json
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Any, List
from functools import wraps
import time
import jsonlog
import config as env_config

logger = jsonlog.setup_logger("cache")

redis_config = env_config.Config(group="REDIS")
redisHost = redis_config.get("REDIS_HOST")
redisPassword = redis_config.get("REDIS_PASSWORD")


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime, date, and Decimal objects."""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def retry_on_failure(max_retries: int = 3, delay: float = 0.1):
    """Retry decorator for Redis operations with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except redis.ConnectionError as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Redis operation failed after {max_retries} attempts: {e}")
                        raise
                    time.sleep(delay * (2 ** attempt))  # Exponential backoff
                    logger.warning(f"Redis connection failed, retrying ({attempt + 1}/{max_retries})...")
            return None
        return wrapper
    return decorator


class RedisClient:
    """Redis client wrapper with JSON support and retry logic."""
    
    _pool = None
    
    @classmethod
    def _get_pool(cls, host: str, port: int, db: int, password: Optional[str]):
        """Get or create connection pool (singleton pattern)."""
        if cls._pool is None:
            cls._pool = redis.ConnectionPool(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=True,
                max_connections=50,
                socket_keepalive=True,
                socket_connect_timeout=5,
                retry_on_timeout=True
            )
        return cls._pool
    
    def __init__(self, host: Optional[str] = None, port: int = 6379, 
                 db: int = 0, password: Optional[str] = None):
        """
        Initialize Redis client with connection pooling.
        
        Args:
            host: Redis host (defaults to config)
            port: Redis port
            db: Redis database number
            password: Redis password (defaults to config)
            
        Raises:
            redis.RedisError: If connection fails
        """
        host = host or redisHost
        password = password or redisPassword
        
        pool = self._get_pool(host, port, db, password)
        self.client = redis.Redis(connection_pool=pool)
        
        # Test connection
        try:
            self.client.ping()
            logger.info(f"Redis client initialized: {host}:{port}, db={db}")
        except redis.RedisError as e:
            logger.error(f"Redis initialization failed: {e}")
            raise
    
    def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            return self.client.ping()
        except redis.RedisError:
            return False
    
    # ===== String Operations =====
    
    @retry_on_failure()
    def set_string(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """Set a string value in Redis."""
        self.client.set(key, value, ex=ttl)
    
    @retry_on_failure()
    def get_string(self, key: str) -> Optional[str]:
        """Retrieve a string value from Redis."""
        return self.client.get(key)
    
    # ===== JSON Operations =====
    
    @retry_on_failure()
    def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Serialize and store JSON object in Redis."""
        json_value = json.dumps(value, cls=DateTimeEncoder)
        self.client.set(key, json_value, ex=ttl)
    
    @retry_on_failure()
    def get_json(self, key: str) -> Optional[Any]:
        """Retrieve and deserialize JSON object from Redis."""
        json_value = self.client.get(key)
        if json_value:
            logger.debug(f"Cache HIT: {key}")
            return json.loads(json_value)
        logger.debug(f"Cache MISS: {key}")
        return None
    
    # ===== List Operations (Using Redis Native Lists) =====
    
    @retry_on_failure()
    def lpush_json(self, key: str, value: Any, ttl: Optional[int] = None) -> int:
        """
        Push JSON value to the LEFT (head) of a Redis list.
        
        Args:
            key: Redis key
            value: Value to serialize and push
            ttl: Optional TTL in seconds
            
        Returns:
            Length of list after push
        """
        json_value = json.dumps(value, cls=DateTimeEncoder)
        length = self.client.lpush(key, json_value)
        if ttl:
            self.client.expire(key, ttl)
        return length
    
    @retry_on_failure()
    def rpush_json(self, key: str, value: Any, ttl: Optional[int] = None) -> int:
        """
        Push JSON value to the RIGHT (tail) of a Redis list.
        
        Args:
            key: Redis key
            value: Value to serialize and push
            ttl: Optional TTL in seconds
            
        Returns:
            Length of list after push
        """
        json_value = json.dumps(value, cls=DateTimeEncoder)
        length = self.client.rpush(key, json_value)
        if ttl:
            self.client.expire(key, ttl)
        return length
    
    @retry_on_failure()
    def lpush_json_with_limit(self, key: str, value: Any, limit: int, 
                              ttl: Optional[int] = None) -> int:
        """
        Push JSON value to LEFT of list and trim to limit.
        
        Args:
            key: Redis key
            value: Value to serialize and push
            limit: Maximum list length
            ttl: Optional TTL in seconds
            
        Returns:
            Length of list after push and trim
        """
        json_value = json.dumps(value, cls=DateTimeEncoder)
        
        # Use pipeline for atomic operation
        pipe = self.client.pipeline()
        pipe.lpush(key, json_value)
        pipe.ltrim(key, 0, limit - 1)  # Keep only first 'limit' items
        if ttl:
            pipe.expire(key, ttl)
        results = pipe.execute()
        
        length = results[0]  # Length after lpush
        logger.debug(f"Pushed to list {key}, trimmed to {limit} items")
        return min(length, limit)
    
    @retry_on_failure()
    def rpush_json_with_limit(self, key: str, value: Any, limit: int, 
                              ttl: Optional[int] = None) -> int:
        """
        Push JSON value to RIGHT of list and trim to limit.
        
        Args:
            key: Redis key
            value: Value to serialize and push
            limit: Maximum list length
            ttl: Optional TTL in seconds
            
        Returns:
            Length of list after push and trim
        """
        json_value = json.dumps(value, cls=DateTimeEncoder)
        
        # Use pipeline for atomic operation
        pipe = self.client.pipeline()
        pipe.rpush(key, json_value)
        pipe.ltrim(key, -limit, -1)  # Keep only last 'limit' items
        if ttl:
            pipe.expire(key, ttl)
        results = pipe.execute()
        
        length = results[0]  # Length after rpush
        logger.debug(f"Pushed to list {key}, trimmed to {limit} items")
        return min(length, limit)
    
    @retry_on_failure()
    def lrange_json(self, key: str, start: int = 0, end: int = -1) -> Optional[List[Any]]:
        """
        Get range of items from Redis list and deserialize.
        
        Args:
            key: Redis key
            start: Start index (0-based)
            end: End index (-1 for all)
            
        Returns:
            List of deserialized objects or None if key doesn't exist
        """
        json_values = self.client.lrange(key, start, end)
        if not json_values:
            return None
        
        logger.debug(f"Retrieved {len(json_values)} items from list {key}")
        return [json.loads(v) for v in json_values]
    
    @retry_on_failure()
    def llen(self, key: str) -> int:
        """Get length of Redis list."""
        return self.client.llen(key)
    
    @retry_on_failure()
    def get_list_items(self, key: str, count: int = 1, pop: bool = False, 
                       direction: str = 'left') -> Optional[List[Any]]:
        """
        Get items from Redis list with flexible direction and pop options.
        
        Args:
            key: Redis key
            count: Number of items to get
            pop: If True, remove items from list. If False, just read
            direction: 'left' for head/start, 'right' for tail/end
            
        Returns:
            List of deserialized objects or None if key doesn't exist
        """
        direction = direction.lower()
        
        if pop:
            # Use LPOP or RPOP to remove and return items
            items = []
            pop_command = self.client.lpop if direction == 'left' else self.client.rpop
            
            for _ in range(count):
                json_value = pop_command(key)
                if json_value is None:
                    break
                items.append(json.loads(json_value))
            
            if items:
                logger.debug(f"Popped {len(items)} items from {direction} of {key}")
                return items
            return None
        else:
            if direction == 'left':
                json_values = self.client.lrange(key, 0, count - 1)
            else:
                # Get from tail: indices -count to -1
                json_values = self.client.lrange(key, -count, -1)
            
            if not json_values:
                return None
            
            logger.debug(f"Retrieved {len(json_values)} items from {direction} of {key}")
            return [json.loads(v) for v in json_values]
    
    # ===== Key Operations =====
    
    @retry_on_failure()
    def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        return self.client.exists(key) > 0
    
    @retry_on_failure()
    def delete_key(self, key: str) -> bool:
        """Delete a single key."""
        try:
            return self.client.delete(key) > 0
        except redis.RedisError as e:
            logger.warning(f"Error deleting key {key}: {e}")
            return False
    
    @retry_on_failure()
    def delete_pattern(self, pattern: str) -> int:
        try:
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = self.client.scan(cursor, match=pattern, count=100)
                if keys:
                    deleted += self.client.delete(*keys)
                if cursor == 0:
                    break
            
            if deleted > 0:
                logger.info(f"Deleted {deleted} keys matching pattern: {pattern}")
            return deleted
        except redis.RedisError as e:
            logger.warning(f"Error deleting keys matching pattern {pattern}: {e}")
            return 0
    
    # ===== Cache Invalidation Helpers =====
    
    def invalidate_server_cache(self, server_id: int, app_name: str = "smart_system") -> int:
        patterns = [
            f"{app_name}:servers:server_actions:{server_id}:*",
            f"{app_name}:servers:server_info:{server_id}",
            f"{app_name}:servers:ssh_credentials:{server_id}",
        ]
        total_deleted = 0
        for pattern in patterns:
            deleted = self.delete_pattern(pattern)
            total_deleted += deleted
        
        # Also invalidate the all actions cache as it may be affected
        self.delete_pattern(f"{app_name}:actions:all_actions:*")
        
        if total_deleted > 0:
            logger.info(f"Invalidated {total_deleted} cache entries for server {server_id}")
        return total_deleted
    
    def invalidate_action_cache(self, app_name: str = "smart_system") -> int:
        pattern = f"{app_name}:actions:*"
        deleted = self.delete_pattern(pattern)
        if deleted > 0:
            logger.info(f"Invalidated {deleted} action cache entries")
        return deleted