from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Agentic Web Browser"
    debug: bool = False
    database_path: str = "data/browser.duckdb"
    media_path: str = "data/media"
    model_id: str = "gpt-5.4-mini"
    agent_max_steps: int = 20
    model_base_url: str = "https://api.openai.com/v1"
    model_api_key: str

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
