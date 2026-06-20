from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Agentic Web Browser"
    debug: bool = False
    database_path: str = "data/browser.duckdb"
    model_id: str 
    agent_max_steps: int = 20
    model_base_url: str
    model_api_key: str
    
    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
