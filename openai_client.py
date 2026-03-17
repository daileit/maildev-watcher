"""
OpenAI client module for Smart System Operator.
Provides AI-powered decision making for server actions based on metrics and logs.
"""

import jsonlog
import json
import random
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass
from openai import OpenAI
import config as env_config

logger = jsonlog.setup_logger("openai_client")


class OpenAIClient:
    """OpenAI client for AI-powered server management decisions."""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, base_url: Optional[str] = None):
        """
        Initialize OpenAI client.
        
        Args:
            api_key: OpenAI API key (defaults to env config)
            model: Model(s) to use - can be a single model or comma-separated list for random selection
                   (defaults to env config or gpt-4o)
            base_url: API base URL (defaults to env config or https://api.openai.com/v1)
        """
        openai_config = env_config.Config(group="OPENAI")
        
        self.api_key = api_key or openai_config.get("OPENAI_API_KEY")
        self.model_config = model or openai_config.get("OPENAI_MODEL", "gpt-4o")
        self.base_url = base_url or openai_config.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        
        if not self.api_key:
            logger.error("OpenAI API key not configured")
            raise ValueError("OpenAI API key is required")
        
        # Parse model configuration - support comma-separated list for random selection
        self.model_list = [m.strip() for m in self.model_config.split(',') if m.strip()]
        if not self.model_list:
            self.model_list = ["gpt-4o"]
        
        # Initialize client with base_url support
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.logger = logger
        
        # Initialize Redis client for model ignore cache
        try:
            self.redis = RedisClient()
        except Exception as e:
            self.logger.warning(f"Redis client initialization failed: {e}. Model ignore cache disabled.")
            self.redis = None
        
        # Initialize system prompt
        self._init_system_prompt()
        
        if len(self.model_list) > 1:
            logger.info(f"OpenAI client initialized with base_url: {self.base_url}, "
                       f"models: {self.model_list} (random selection enabled)")
        else:
            logger.info(f"OpenAI client initialized with base_url: {self.base_url}, "
                       f"model: {self.model_list[0]}")
    
    def _get_model(self, ignore_model: str = "") -> str:
        """
        Get a model to use for the current request.        
        Args:
            ignore_model: Model name to ignore and cache for 2 hours (7200s)        
        Returns:
            Model name to use
        """
        if ignore_model and self.redis:
            ignore_key = f"smart_system:ignored_model:{ignore_model}"
            try:
                self.redis.set_string(ignore_key, "1", ttl=7200)
                self.logger.info(f"Cached ignored model: {ignore_model} (TTL: 7200s)")
            except Exception as e:
                self.logger.warning(f"Failed to cache ignored model {ignore_model}: {e}")
        
        if len(self.model_list) == 1:
            return self.model_list[0]
        
        max_attempts = len(self.model_list)
        
        for attempt in range(max_attempts):
            selected_model = random.choice(self.model_list)            
            if self.redis:
                ignore_key = f"smart_system:ignored_model:{selected_model}"
                try:
                    if self.redis.exists(ignore_key):
                        self.logger.debug(f"Model {selected_model} is ignored, retrying... (attempt {attempt + 1}/{max_attempts})")
                        continue
                except Exception as e:
                    self.logger.warning(f"Failed to check ignore cache for {selected_model}: {e}")

            self.logger.debug(f"Selected model: {selected_model} from {self.model_list}")
            return selected_model

        selected_model = random.choice(self.model_list)
        self.logger.warning(f"All models are ignored. Returning random model anyway: {selected_model}")
        return selected_model
    
    @staticmethod
    def fetch_available_models(api_key: Optional[str] = None, base_url: Optional[str] = None) -> List[Tuple[str, str, bool, int]]:
        """
        Fetch available models from OpenAI-compatible API endpoint.
        
        Args:
            api_key: API key (defaults to env config)
            base_url: API base URL (defaults to env config)
            
        Returns:
            List of tuples: (model_id, label, is_default, display_order)
        """
        try:
            openai_config = env_config.Config(group="OPENAI")
            
            if not api_key:
                api_key = openai_config.get("OPENAI_API_KEY")
            
            if not base_url:
                base_url = openai_config.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            
            if not api_key:
                logger.error("OPENAI_API_KEY not configured")
                return None
            
            client = OpenAI(api_key=api_key, base_url=base_url)
            models_response = client.models.list()
            
            default_model_config = openai_config.get("OPENAI_MODEL", "gpt-4o")
            default_model_list = [m.strip() for m in default_model_config.split(',') if m.strip()]
            

            available_models = []
            display_order = 1
            
            for model in models_response.data:
                model_id = model.id
                
                is_default = model_id in default_model_list
                
                label = model_id.replace('_', ' ').replace('-', ' ').title()
                             
                available_models.append((model_id, label, is_default, display_order))
                display_order += 1
            
            # Sort models: default first, then alphabetically
            available_models.sort(key=lambda x: (not x[2], x[0].lower()))
            
            # Re-assign display order after sorting
            available_models = [(m[0], m[1], m[2], i+1) for i, m in enumerate(available_models)]
            
            if not available_models:
                logger.warning(f"No models found from {base_url}")
                return None
            
            logger.info(f"Fetched {len(available_models)} available models from {base_url}")
            return available_models
            
        except Exception as e:
            logger.error(f"Error fetching models from {base_url}: {e}")
            return None
    
    def _init_system_prompt(self):
        """Initialize the system prompt for server management AI."""
        self.system_prompt = """You are a helpful AI.
OUTPUT JSON:
{

}"""
    
    