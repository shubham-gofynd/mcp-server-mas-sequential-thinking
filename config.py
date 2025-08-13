"""Simplified configuration management using strategy pattern."""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Type, Optional

from agno.models.base import Model
from agno.models.deepseek import DeepSeek
from agno.models.groq import Groq
from agno.models.ollama import Ollama
from agno.models.openrouter import OpenRouter
from agno.models.openai import OpenAIChat


@dataclass(frozen=True)
class ModelConfig:
    """Configuration for model provider and IDs."""
    provider_class: Type[Model]
    team_model_id: str
    agent_model_id: str
    api_key: Optional[str] = None


class ProviderStrategy(ABC):
    """Abstract strategy for provider configuration."""
    
    @property
    @abstractmethod
    def provider_class(self) -> Type[Model]:
        """Return the provider model class."""
        pass
    
    @property
    @abstractmethod
    def default_team_model(self) -> str:
        """Return default team model ID."""
        pass
    
    @property
    @abstractmethod
    def default_agent_model(self) -> str:
        """Return default agent model ID."""
        pass
    
    @property
    @abstractmethod
    def api_key_name(self) -> Optional[str]:
        """Return API key environment variable name."""
        pass
    
    def get_config(self) -> ModelConfig:
        """Get complete configuration with environment overrides."""
        prefix = self.__class__.__name__.replace("Strategy", "").upper()
        
        # Get team model with fallback to default if empty
        team_model = os.environ.get(f"{prefix}_TEAM_MODEL_ID")
        if not team_model:  # None or empty string
            team_model = self.default_team_model
        
        # Get agent model with fallback to default if empty
        agent_model = os.environ.get(f"{prefix}_AGENT_MODEL_ID")
        if not agent_model:  # None or empty string
            agent_model = self.default_agent_model
        
        # Get API key with None conversion for empty strings
        api_key = os.environ.get(self.api_key_name) if self.api_key_name else None
        if api_key == "":  # Convert empty string to None
            api_key = None
        
        return ModelConfig(
            provider_class=self.provider_class,
            team_model_id=team_model,
            agent_model_id=agent_model,
            api_key=api_key
        )


class DeepSeekStrategy(ProviderStrategy):
    provider_class = DeepSeek
    default_team_model = "deepseek-chat"
    default_agent_model = "deepseek-chat"
    api_key_name = "DEEPSEEK_API_KEY"


class GroqStrategy(ProviderStrategy):
    provider_class = Groq
    default_team_model = "deepseek-r1-distill-llama-70b"
    default_agent_model = "qwen-2.5-32b"
    api_key_name = "GROQ_API_KEY"


class OpenRouterStrategy(ProviderStrategy):
    provider_class = OpenRouter
    default_team_model = "deepseek/deepseek-chat-v3-0324"
    default_agent_model = "deepseek/deepseek-r1"
    api_key_name = "OPENROUTER_API_KEY"


class OllamaStrategy(ProviderStrategy):
    provider_class = Ollama
    default_team_model = "devstral:24b"
    default_agent_model = "devstral:24b"
    api_key_name = None  # No API key required


class GitHubStrategy(ProviderStrategy):
    """GitHub Models provider strategy.
    
    Uses OpenAI agno provider with GitHub Models API endpoint.
    Requires GITHUB_TOKEN for authentication.
    """
    
    @property
    def provider_class(self):
        """Return GitHub-configured OpenAI class for GitHub Models."""
        # Create a custom OpenAI class configured for GitHub Models
        class GitHubOpenAI(OpenAIChat):
            def __init__(self, **kwargs):
                # Set GitHub Models base URL
                kwargs.setdefault('base_url', 'https://models.github.ai/inference')
                # GitHub uses personal access tokens instead of API keys
                if 'api_key' not in kwargs:
                    kwargs['api_key'] = os.environ.get('GITHUB_TOKEN')
                super().__init__(**kwargs)
        
        return GitHubOpenAI
    
    @property
    def default_team_model(self) -> str:
        """Return default team model for GitHub."""
        return "openai/gpt-5"
    
    @property
    def default_agent_model(self) -> str:
        """Return default agent model for GitHub."""
        return "openai/gpt-5-min"
    
    @property
    def api_key_name(self) -> str:
        """Return GitHub API key environment variable name."""
        return "GITHUB_TOKEN"


# Strategy registry
STRATEGIES = {
    "deepseek": DeepSeekStrategy(),
    "groq": GroqStrategy(),
    "openrouter": OpenRouterStrategy(),
    "ollama": OllamaStrategy(),
    "github": GitHubStrategy(),
}


def get_model_config() -> ModelConfig:
    """Get model configuration using strategy pattern."""
    provider_name = os.environ.get("LLM_PROVIDER", "deepseek").lower()
    strategy = STRATEGIES.get(provider_name, STRATEGIES["deepseek"])
    return strategy.get_config()


def check_required_api_keys() -> list[str]:
    """Check for required API keys using current strategy."""
    provider_name = os.environ.get("LLM_PROVIDER", "deepseek").lower()
    strategy = STRATEGIES.get(provider_name, STRATEGIES["deepseek"])
    
    missing_keys = []
    
    # Check provider API key
    if strategy.api_key_name and not os.environ.get(strategy.api_key_name):
        missing_keys.append(strategy.api_key_name)
    
    # Check EXA API key for research tools
    if not os.environ.get("EXA_API_KEY"):
        missing_keys.append("EXA_API_KEY")
    
    return missing_keys