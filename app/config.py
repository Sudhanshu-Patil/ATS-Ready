from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent  # points to resume_agent/


class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    MODEL: str = "gemini-2.0-flash"
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"

    # Database
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/metabase.db"

    # Resume generation
    MAX_SKILLS_IN_RESUME: int = 12
    MAX_PROJECTS_IN_RESUME: int = 4
    MAX_EXPERIENCE_BULLETS: int = 5  # per role

    # ATS weights (must sum to 1.0)
    ATS_KEYWORD_WEIGHT: float = 0.40
    ATS_SKILLS_WEIGHT: float = 0.30
    ATS_ACTION_VERB_WEIGHT: float = 0.15
    ATS_FORMAT_WEIGHT: float = 0.15

    # Output
    OUTPUT_DIR: Path = BASE_DIR / "outputs"

    # Scraper
    SCRAPE_TIMEOUT: int = 15
    RESPECT_ROBOTS_TXT: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
settings.OUTPUT_DIR.mkdir(exist_ok=True)