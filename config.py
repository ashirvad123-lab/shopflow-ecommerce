import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool

BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from .env if present
load_dotenv(BASE_DIR / '.env')


def normalize_database_url(url: str | None) -> str:
    """Normalize legacy PostgreSQL URLs and resolve relative SQLite URLs explicitly."""
    if not url:
        return f"sqlite:///{BASE_DIR / 'ecommerce.db'}"
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    if url.startswith("sqlite:"):
        parsed_url = make_url(url)
        if parsed_url.database in (None, ':memory:'):
            return url
        database_path = Path(parsed_url.database)
        if not database_path.is_absolute():
            database_path = BASE_DIR / 'instance' / database_path
        return parsed_url.set(database=str(database_path.resolve())).render_as_string(
            hide_password=False
        )
    return url


class Config:
    """Base application configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-replace-in-production-random-hash")
    SQLALCHEMY_DATABASE_URI = normalize_database_url(os.getenv("DATABASE_URL"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Session and Cookie security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 86400  # 1 day in seconds
    
    # CSRF Protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # Valid for session duration
    
    # Currency configuration
    CURRENCY_SYMBOL = "$"
    CURRENCY_CODE = "USD"
    
    # Free shipping threshold
    FREE_SHIPPING_THRESHOLD = 50.00
    STANDARD_SHIPPING_FEE = 5.00

    # Google Maps Platform Configuration
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
    STORE_NAME = os.getenv("STORE_NAME", "ShopFlow")
    STORE_ADDRESS = os.getenv("STORE_ADDRESS", "")
    STORE_EMAIL = os.getenv("STORE_EMAIL", "")
    STORE_PHONE = os.getenv("STORE_PHONE", "")

    # Razorpay Payment Gateway Configuration
    RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
    RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class TestingConfig(Config):
    """Testing configuration with shared in-memory SQLite and CSRF disabled for unit tests."""
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool
    }
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SESSION_COOKIE_SECURE = True


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
