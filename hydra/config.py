"""
Configuration for Hydra framework via pydantic-settings.
Load from environment variables with HYDRA_ prefix.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HydraConfig(BaseSettings):
    """
    Hydra configuration. All settings can be set via environment variables
    with the HYDRA_ prefix (e.g., HYDRA_API_KEY=sk-ant-...).
    """

    # ── LLM Provider ──────────────────────────────────────────────────────────
    api_key: str = Field(default="", description="Provider API key (Anthropic, OpenAI, etc.)")
    api_base: str | None = Field(default=None, description="Custom API endpoint URL (for self-hosted/enterprise)")
    default_model: str = Field(
        default="anthropic/claude-sonnet-4-6",
        description="litellm model string (e.g. anthropic/claude-sonnet-4-6, gpt-4o, ollama/llama3)",
    )
    brain_model: str = Field(
        default="anthropic/claude-sonnet-4-6",
        description="Model used for task decomposition (Brain). Can be more capable than default.",
    )
    post_brain_model: str = Field(
        default="anthropic/claude-sonnet-4-6",
        description="Model used for synthesis and quality scoring (Post-Brain).",
    )
    max_tokens_per_agent: int = Field(default=4096, description="Max tokens for each agent LLM call.")
    max_tokens_synthesis: int = Field(default=8192, description="Max tokens for the post-brain synthesis LLM call.")
    max_tokens_brain: int = Field(default=4096, description="Max tokens for the Brain task-decomposition LLM call.")

    # ── Execution ─────────────────────────────────────────────────────────────
    max_concurrent_agents: int = Field(default=5, ge=1, le=50, description="Max number of agents running simultaneously.")
    per_agent_timeout_seconds: int = Field(default=60, gt=0, le=3600, description="Timeout (seconds) per agent execution.")
    total_task_timeout_seconds: int = Field(default=600, gt=0, le=7200, description="Total timeout for the entire task pipeline.")
    total_token_budget: int = Field(default=100_000, ge=1000, le=10_000_000, description="Abort if total token usage exceeds this budget.")

    # ── Tool Loop ─────────────────────────────────────────────────────────────
    max_tool_iterations: int = Field(default=20, ge=1, le=200, description="Safety cap on LLM tool-use loop iterations per agent.")

    # ── Retry ─────────────────────────────────────────────────────────────────
    default_max_retries: int = Field(default=2, ge=0, le=10, description="Default max retries for failed agents.")
    retry_backoff_base: float = Field(default=1.0, description="Base delay (seconds) for exponential backoff.")

    # ── Quality ───────────────────────────────────────────────────────────────
    min_quality_score: float = Field(default=5.0, ge=0.0, le=10.0, description="Minimum quality score to pass the quality gate.")

    # ── Paths ─────────────────────────────────────────────────────────────────
    output_directory: str = Field(default="./hydra_output", description="Directory where generated files are written.")

    # ── File Upload ───────────────────────────────────────────────────────────
    max_upload_files: int = Field(default=20, ge=1, le=100, description="Maximum number of files that can be attached per run.")
    max_upload_file_size_mb: int = Field(default=50, ge=1, le=500, description="Maximum file size in MB; larger files are skipped.")

    # ── Search ────────────────────────────────────────────────────────────────
    search_api_key: str = Field(default="", description="API key for web search (Brave/Tavily/SerpAPI).")
    search_backend: str = Field(default="brave", description="Search backend: brave | tavily | serpapi")

    # ── Server Auth ───────────────────────────────────────────────────────────
    server_token: str = Field(
        default="",
        description="Optional API token for server auth. When set, all /api/* routes require X-API-Key header. Env: HYDRA_SERVER_TOKEN.",
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: str = Field(
        default="*",
        description="Comma-separated list of allowed CORS origins (e.g. 'http://localhost:3000,https://myapp.com'). Use '*' to allow all. Env: HYDRA_CORS_ORIGINS.",
    )

    model_config = SettingsConfigDict(
        env_prefix="HYDRA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
