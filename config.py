import os
import tempfile
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
APP_ENV = os.environ.get('APP_ENV', 'development').lower()

# Environment files are chosen per mode so dev never reads production secrets
# and tests read nothing at all (full isolation).
if APP_ENV != 'testing':
    _env_file = os.environ.get('ENV_FILE') or os.path.join(
        basedir, '.env.production' if APP_ENV == 'production' else '.env')
    load_dotenv(_env_file)


def _bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    """Base configuration (safe defaults: mock providers, no real services)."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///' + os.path.join(basedir, 'shop.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(basedir, 'app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    WTF_CSRF_ENABLED = True
    SITE_URL = os.environ.get('SITE_URL', '')  # e.g. https://shop.example.com (used in callbacks/sitemap)

    PRODUCTS_PER_PAGE = 12
    ORDER_PAYMENT_WINDOW_MINUTES = _int('ORDER_PAYMENT_WINDOW_MINUTES', 30)
    LOGIN_MAX_FAILURES = 5
    LOGIN_LOCK_MINUTES = 15

    # SMS
    SMS_PROVIDER = 'mock'
    KAVENEGAR_API_KEY = ''
    KAVENEGAR_SENDER = os.environ.get('KAVENEGAR_SENDER', '')
    KAVENEGAR_OTP_TEMPLATE = os.environ.get('KAVENEGAR_OTP_TEMPLATE', '')
    SMS_VERIFICATION_REQUIRED = True
    OTP_TTL_SECONDS = 300
    OTP_MAX_ATTEMPTS = 5
    OTP_RESEND_COOLDOWN = 60
    OTP_MAX_SENDS_PER_HOUR = 5
    SMS_MAX_RETRIES = 3

    # Payments
    PAYMENT_GATEWAY = 'mock'
    ZARINPAL_MERCHANT_ID = ''
    ZARINPAL_SANDBOX = True


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///' + os.path.join(basedir, 'shop-dev.db')
    _live = _bool('ALLOW_LIVE_SERVICES_IN_DEV')
    # Real credentials are ignored in dev unless explicitly allowed.
    SMS_PROVIDER = os.environ.get('SMS_PROVIDER', 'mock') if _live else 'mock'
    KAVENEGAR_API_KEY = os.environ.get('KAVENEGAR_API_KEY', '') if _live else ''
    PAYMENT_GATEWAY = os.environ.get('PAYMENT_GATEWAY', 'mock') if _live else 'mock'
    ZARINPAL_MERCHANT_ID = os.environ.get('ZARINPAL_MERCHANT_ID', '') if _live else ''
    ZARINPAL_SANDBOX = True  # never live payments from dev


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = 'test-secret'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {'check_same_thread': False},
        'poolclass': __import__('sqlalchemy.pool', fromlist=['StaticPool']).StaticPool,
    }
    UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'shop-test-uploads')
    WTF_CSRF_ENABLED = False
    SERVER_NAME = None
    SMS_PROVIDER = 'mock'
    PAYMENT_GATEWAY = 'mock'
    KAVENEGAR_API_KEY = ''
    ZARINPAL_MERCHANT_ID = ''
    SITE_URL = 'http://localhost'


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = _bool('SESSION_COOKIE_SECURE', True)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SMS_PROVIDER = os.environ.get('SMS_PROVIDER', 'kavenegar')
    KAVENEGAR_API_KEY = os.environ.get('KAVENEGAR_API_KEY', '')
    PAYMENT_GATEWAY = os.environ.get('PAYMENT_GATEWAY', 'zarinpal')
    ZARINPAL_MERCHANT_ID = os.environ.get('ZARINPAL_MERCHANT_ID', '')
    ZARINPAL_SANDBOX = _bool('ZARINPAL_SANDBOX', False)

    @classmethod
    def validate(cls):
        problems = []
        if cls.SECRET_KEY in ('', 'dev-secret-change-me') or len(cls.SECRET_KEY) < 16:
            problems.append('SECRET_KEY must be set to a strong value')
        if cls.SMS_PROVIDER == 'mock':
            problems.append('SMS_PROVIDER=mock is not allowed in production')
        if cls.SMS_PROVIDER == 'kavenegar' and not (cls.KAVENEGAR_API_KEY and cls.KAVENEGAR_SENDER):
            problems.append('KAVENEGAR_API_KEY and KAVENEGAR_SENDER are required')
        if cls.PAYMENT_GATEWAY == 'mock':
            problems.append('PAYMENT_GATEWAY=mock is not allowed in production')
        if cls.PAYMENT_GATEWAY == 'zarinpal' and not cls.ZARINPAL_MERCHANT_ID:
            problems.append('ZARINPAL_MERCHANT_ID is required')
        if not cls.SITE_URL.startswith('https://'):
            problems.append('SITE_URL must be set to the public https URL')
        if problems:
            raise RuntimeError('Invalid production configuration: ' + '; '.join(problems))


CONFIG_BY_ENV = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
}


def get_config():
    return CONFIG_BY_ENV.get(APP_ENV, DevelopmentConfig)
