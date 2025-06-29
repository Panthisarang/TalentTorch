from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from models import Base
from config import settings
import redis
from typing import Generator
import json


class DatabaseManager:
    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self.redis_client = None
        self._setup_database()
        self._setup_redis()
    
    def _setup_database(self):
        """Setup database connection"""
        if settings.database_url.startswith("sqlite"):
            # SQLite configuration for development
            self.engine = create_engine(
                settings.database_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
                echo=settings.debug
            )
        else:
            # PostgreSQL configuration for production
            self.engine = create_engine(
                settings.database_url,
                echo=settings.debug,
                pool_pre_ping=True
            )
        
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    def _setup_redis(self):
        """Setup Redis connection for caching"""
        try:
            self.redis_client = redis.from_url(settings.redis_url)
            # Test connection
            self.redis_client.ping()
        except Exception as e:
            print(f"Warning: Redis connection failed: {e}")
            self.redis_client = None
    
    def create_tables(self):
        """Create all database tables"""
        Base.metadata.create_all(bind=self.engine)
    
    def get_db(self) -> Generator[Session, None, None]:
        """Get database session"""
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    def get_cache(self, key: str):
        """Get value from cache"""
        if not self.redis_client:
            return None
        
        try:
            value = self.redis_client.get(key)
            return json.loads(value) if value else None
        except Exception as e:
            print(f"Cache get error: {e}")
            return None
    
    def set_cache(self, key: str, value: any, ttl: int = None):
        """Set value in cache"""
        if not self.redis_client:
            return False
        
        try:
            ttl = ttl or settings.cache_ttl
            self.redis_client.setex(key, ttl, json.dumps(value))
            return True
        except Exception as e:
            print(f"Cache set error: {e}")
            return False
    
    def delete_cache(self, key: str):
        """Delete value from cache"""
        if not self.redis_client:
            return False
        
        try:
            self.redis_client.delete(key)
            return True
        except Exception as e:
            print(f"Cache delete error: {e}")
            return False
    
    def clear_cache(self):
        """Clear all cache"""
        if not self.redis_client:
            return False
        
        try:
            self.redis_client.flushdb()
            return True
        except Exception as e:
            print(f"Cache clear error: {e}")
            return False


# Global database manager instance
db_manager = DatabaseManager()


def get_db():
    """Dependency to get database session"""
    return db_manager.get_db()


def get_cache():
    """Dependency to get cache client"""
    return db_manager.redis_client 