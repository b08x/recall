from typing import Optional
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    """Configuration settings for the recall package."""
    
    # Paths
    notebook_path: str = Field(default="~/Notebook", description="Path to Obsidian notebook")
    workspace_path: str = Field(default="~/Workspace", description="Path to code workspace")
    db_path: str = Field(default="recall.db", description="Path to SQLite database")
    vector_db_dir: str = Field(default="./chroma_db", description="Directory for ChromaDB storage")
    
    # DSPy Settings
    dspy_provider: str = Field(default="openrouter", description="DSPy provider (openrouter, openai, ollama, mistral)")
    dspy_insights_provider: Optional[str] = Field(
        default=None,
        description="Specific provider for deep insight extraction",
        validation_alias="insights_provider"
    )
    dspy_model: str = Field(default="openai/gpt-4o-mini", description="DSPy model identifier for general analysis")
    dspy_insights_model: Optional[str] = Field(
        default=None, 
        description="Specific model for deep insight extraction",
        validation_alias="insights_model"
    )
    
    # Embedding Settings
    ollama_host: str = Field(default="http://tinybot:11434", description="Host for Ollama embedding service")
    embedding_model: str = Field(default="embeddinggemma", description="Ollama model for embeddings")
    embedding_max_tokens: int = Field(default=768, description="Maximum tokens for local embedding models")
    chunk_max_chars: int = Field(default=6000, description="Conservative character limit for text chunking")
    
    # API Keys
    openrouter_api_key: Optional[SecretStr] = None
    openai_api_key: Optional[SecretStr] = None
    anthropic_api_key: Optional[SecretStr] = None
    gemini_api_key: Optional[SecretStr] = None
    mistral_api_key: Optional[SecretStr] = None
    
    # Platform specific
    github_token: Optional[SecretStr] = None
    
    # Rate Limiting & Retry
    retry_max_attempts: int = Field(default=5, description="Maximum number of retry attempts")
    retry_min_wait: float = Field(default=1.0, description="Minimum wait time between retries (seconds)")
    retry_max_wait: float = Field(default=60.0, description="Maximum wait time between retries (seconds)")
    requests_per_minute: int = Field(default=20, description="Conservative rate limit (requests per minute)")
    max_workers: int = Field(default=10, description="Maximum number of worker threads for parallel extraction/analysis")
    token_warning_threshold: int = Field(default=100000, description="Threshold for token count warning before LLM analysis")
    
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
