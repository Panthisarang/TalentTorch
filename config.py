import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI API Configuration
    openai_api_key: str = "s"
    serpapi_key: str = "q"
    # Database Configuration
    database_url: str = "sqlite:///./linkedin_sourcing.db"
    
    # Redis Configuration (for caching and Celery)
    redis_url: str = "redis://localhost:6379"
    
    # LinkedIn/RapidAPI Configuration
    rapidapi_key: Optional[str] = ""
    rapidapi_host: str = "l"

    rapidapi_key: Optional[str] = ""
    rapidapi_host: str = "a"
    
    # GitHub API (for multi-source enhancement)
    github_token: Optional[str] = ""
    
    # Twitter API (for multi-source enhancement)
    twitter_bearer_token: Optional[str] = None
    
    # Application Configuration
    debug: bool = True
    secret_key: str = "your-secret-key-change-this-in-production"
    allowed_hosts: str = "localhost,127.0.0.1"
    
    # Rate Limiting
    max_requests_per_minute: int = 60
    max_requests_per_hour: int = 1000
    RATE_LIMIT_DELAY: float = 1.0  # Default rate limit delay in seconds
    
    # Cache Configuration
    cache_ttl: int = 3600  # 1 hour in seconds
    
    # Fit Score Weights
    education_weight: float = 0.20
    trajectory_weight: float = 0.20
    company_weight: float = 0.15
    skills_weight: float = 0.25
    location_weight: float = 0.10
    tenure_weight: float = 0.10
    
    # Elite Schools List
    elite_schools: list = [
        "MIT", "Stanford", "Harvard", "Berkeley", "CMU", "Caltech",
        "Princeton", "Yale", "Columbia", "Cornell", "UCLA", "UCSD"
    ]
    
    # Top Tech Companies
    top_tech_companies: list = [
        "Google", "Meta", "Apple", "Amazon", "Microsoft", "Netflix",
        "Twitter", "LinkedIn", "Salesforce", "Adobe", "Oracle", "IBM",
        "Intel", "NVIDIA", "AMD", "Qualcomm", "Cisco", "VMware"
    ]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings() 