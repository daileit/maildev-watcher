import os
from typing import Dict, Optional, Any
from uuid import uuid4

class Config:
    """Configuration manager that groups environment variables by prefix."""
    
    def __init__(self, group: Optional[str] = None):
        self._configs: Dict[str, Any] = {}
        self._groups: Dict[str, Dict[str, Any]] = {}
        self._group_filter = group.upper() if group else None
        self._load_predefined_configs()
        self._load_env_variables()
        self._build_groups()
    
    def _load_predefined_configs(self):
        """Load predefined configs with default values."""
        # MySQL configs
        self._configs['MYSQL_HOST'] = os.getenv('MYSQL_HOST', 'localhost')
        self._configs['MYSQL_USER'] = os.getenv('MYSQL_USER', 'task_user')
        self._configs['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD', '')
        self._configs['MYSQL_DATABASE'] = os.getenv('MYSQL_DATABASE', 'database')
        self._configs['MYSQL_PORT'] = os.getenv('MYSQL_PORT', '3306')
        
        # Redis configs
        self._configs['REDIS_HOST'] = os.getenv('REDIS_HOST', 'localhost')
        self._configs['REDIS_PORT'] = os.getenv('REDIS_PORT', '6379')
        self._configs['REDIS_PASSWORD'] = os.getenv('REDIS_PASSWORD', '')
        self._configs['REDIS_DB'] = os.getenv('REDIS_DB', '0')
        
        # Application configs
        self._configs['APP_NAME'] = os.getenv('APP_NAME', 'smart_system')
        self._configs['APP_ENV'] = os.getenv('APP_ENV', 'development')
        self._configs['APP_DEBUG'] = os.getenv('APP_DEBUG', 'false')
        self._configs['APP_INIT_SECRET'] = os.getenv('APP_INIT_SECRET', uuid4().hex)
        self._configs['APP_LOG_LEVEL'] = os.getenv('APP_LOG_LEVEL', 'INFO')
        self._configs['APP_PORT'] = os.getenv('APP_PORT', '8080')
        self._configs['APP_CRAWLER_DELAY'] = os.getenv('APP_CRAWLER_DELAY', '30')
        self._configs['APP_MODEL_DELAY'] = os.getenv('APP_MODEL_DELAY', '120')

        # OpenAI configs
        self._configs['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY', '')
        self._configs['OPENAI_BASE_URL'] = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
        self._configs['OPENAI_MODEL'] = os.getenv('OPENAI_MODEL', 'gpt-4o')
        self._configs['OPENAI_LANGUAGE'] = os.getenv('OPENAI_LANGUAGE', 'Vietnamese')

    def _load_env_variables(self):
        """Load all environment variables into the config (override predefined if set)."""
        for key, value in os.environ.items():
            self._configs[key.upper()] = value.strip()
    
    def _build_groups(self):
        """Build groups dictionary from all configs."""
        for key, value in self._configs.items():
            if '_' in key:
                prefix = key.split('_')[0]
                if prefix not in self._groups:
                    self._groups[prefix] = {}
                self._groups[prefix][key] = value
        
        # If group filter is set, filter configs to only the specified group
        if self._group_filter and self._group_filter in self._groups:
            self._configs = self._groups[self._group_filter].copy()
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a specific config value by key."""
        return self._configs.get(key, default)
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values."""
        return self._configs.copy()
    
    def get_group(self, prefix: str) -> Dict[str, Any]:
        """Get all configs that start with a specific prefix."""
        return self._groups.get(prefix.upper(), {}).copy()
    
    def get_all_groups(self) -> Dict[str, Dict[str, Any]]:
        """Get all groups."""
        return {k: v.copy() for k, v in self._groups.items()}
    
    def reload(self):
        """Reload environment variables."""
        self._configs.clear()
        self._groups.clear()
        self._load_predefined_configs()
        self._load_env_variables()
        self._build_groups()
