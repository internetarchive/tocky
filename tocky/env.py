from dataclasses import dataclass
import functools
from functools import cached_property
import os
from pathlib import Path
from dotenv import load_dotenv


@functools.cache
def get_env() -> "TockyEnv":
    """Get the Tocky environment configuration."""
    return TockyEnv.from_env()

@dataclass
class TockyEnv:
    @cached_property
    def TOCKY_SERVER_NAME(self) -> str:
        return getenv_required('TOCKY_SERVER_NAME').rstrip('/')

    @cached_property
    def TOCKY_APPLICATION_ROOT(self) -> str:
        return getenv_required('TOCKY_APPLICATION_ROOT').rstrip('/')

    @cached_property
    def TOCKY_PREFERRED_URL_SCHEME(self) -> str:
        return getenv_required('TOCKY_PREFERRED_URL_SCHEME')

    @cached_property
    def TOCKY_QUEUE_DB_PATH(self) -> Path:
        return Path(getenv_required('TOCKY_QUEUE_DB_PATH'))

    @property
    def TOCKY_SERVER_KEY(self) -> str:
        return getenv_required('TOCKY_SERVER_KEY')

    @property
    def TOCKY_USER_KEY(self) -> str:
        return getenv_required('TOCKY_USER_KEY')

    @property
    def AZURE_SUBSCRIPTION_KEY(self) -> str | None:
        return os.environ.get('AZURE_SUBSCRIPTION_KEY')

    @property
    def AZURE_ENDPOINT(self) -> str | None:
        return os.environ.get('AZURE_ENDPOINT')

    def get_app_prefix(self) -> str:
        return f'{self.TOCKY_PREFERRED_URL_SCHEME}://{self.TOCKY_SERVER_NAME}{self.TOCKY_APPLICATION_ROOT}'

    @staticmethod
    def from_env() -> "TockyEnv":
        print("Loading environment variables from .env...")
        load_dotenv('.env')
        APP_ENV = os.environ.get('APP_ENV', '.env')
        if APP_ENV and APP_ENV != '.env':
            print(f"Loading environment variables from {APP_ENV}...")
            load_dotenv(APP_ENV, override=True)
        local_overrides = Path(f"{APP_ENV}.local")
        if local_overrides.exists():
            print(f"Loading local overrides from {local_overrides}...")
            load_dotenv(local_overrides, override=True)
        return TockyEnv()

def getenv_required(key: str, default: str | None = None) -> str:
    """Retrieve an environment variable or raise ConfigError if missing."""
    value = os.getenv(key, default)
    if value is None:
        if default is not None:
            return default
        else:
            raise RuntimeError(f"Environment variable '{key}' is required but not set.")
    return value
