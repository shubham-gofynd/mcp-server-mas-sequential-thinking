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
        
        return ModelConfig(
            provider_class=self.provider_class,
            team_model_id=os.environ.get(f"{prefix}_TEAM_MODEL_ID", self.default_team_model),
            agent_model_id=os.environ.get(f"{prefix}_AGENT_MODEL_ID", self.default_agent_model),
            api_key=os.environ.get(self.api_key_name) if self.api_key_name else None
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


# Strategy registry
STRATEGIES = {
    "deepseek": DeepSeekStrategy(),
    "groq": GroqStrategy(),
    "openrouter": OpenRouterStrategy(),
    "ollama": OllamaStrategy(),
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