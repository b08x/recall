from typing import Optional
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    """Configuration settings for the recall package."""
    
    # Paths
    notebook_path: str = Field(default="~/Notebook", description="Path to Obsidian notebook")
    workspace_path: str = Field(default="~/Workspace", description="Path to code workspace")
    
    # DSPy Settings
    dspy_provider: str = Field(default="openrouter", description="DSPy provider (openrouter, openai, ollama)")
    dspy_model: str = Field(default="openai/gpt-4o-mini", description="DSPy model identifier")
    
    # API Keys
    openrouter_api_key: Optional[SecretStr] = None
    openai_api_key: Optional[SecretStr] = None
    anthropic_api_key: Optional[SecretStr] = None
    gemini_api_key: Optional[SecretStr] = None
    
    # Platform specific
    github_token: Optional[SecretStr] = None
    
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def resolved_notebook_path(self) -> Path:
        return Path(self.notebook_path).expanduser()

    @property
    def resolved_workspace_path(self) -> Path:
        return Path(self.workspace_path).expanduser()
