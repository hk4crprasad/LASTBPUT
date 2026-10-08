from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    app_mode: str = 'demo'
    facility_timezone: str = 'Asia/Kolkata'
    database_url: str = 'postgresql+psycopg://greenops:unset@localhost:5432/greenops'
    database_prepare_threshold: str = 'disabled'
    database_statement_timeout_ms: int = Field(default=3000, ge=100, le=60000)
    database_connect_timeout_seconds: int = Field(default=15, ge=2, le=60)
    redis_url: str = 'redis://localhost:6379/0'
    object_storage_provider: Literal['s3', 'azure'] = 's3'
    azure_storage_connection_string: str = ''
    azure_storage_account_url: str = ''
    azure_storage_account_key: str = ''
    azure_storage_container: str = 'greenops'
    azure_storage_prefix: str = 'hospital-greenops/'
    azure_storage_create_container: bool = False
    object_storage_endpoint: str = 'http://localhost:9000'
    object_storage_bucket: str = 'greenops'
    object_storage_access_key: str = 'greenops-storage'
    object_storage_secret_key: str = ''
    session_secret: str = ''
    public_url: str = 'http://localhost:3000'
    cors_origins: str = 'http://localhost:3000'
    cookie_secure: bool = False
    llm_enabled: bool = False
    openai_base_url: str = 'https://api.openai.com/v1'
    openai_api_key: str = ''
    openai_chat_model: str = ''
    openai_agent_model: str = ''
    llm_supports_tools: bool = True
    llm_supports_streaming: bool = False
    llm_supports_strict_schema: bool = False
    llm_supports_parallel_tool_calls: bool = False
    llm_reasoning_effort: str = ''
    llm_token_limit_parameter: str = 'max_completion_tokens'
    llm_stream_include_usage: bool = True
    llm_timeout_seconds: int = 45
    agent_max_steps: int = 8
    agent_max_tool_calls: int = 16
    agent_max_run_seconds: int = 120
    agent_max_output_tokens: int = 3000
    agent_autonomous_writes_enabled: bool = False
    demo_credentials_path: str = '/app/shared/demo-credentials.json'
    starter_path: str = '/app/data/public/starter'
    job_max_retries: int = 3
    job_lease_seconds: int = 180

@lru_cache
def settings():
    return Settings()
