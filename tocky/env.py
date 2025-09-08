from dataclasses import dataclass
import functools
from functools import cached_property
import os
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlparse

from openai import OpenAI

from tocky.utils.async_cache import CacheWithAsync


@functools.cache
def get_env() -> "TockyEnv":
    """Get the Tocky environment configuration."""
    return TockyEnv.from_env()

@dataclass
class TockyEnv:
    @cached_property
    def TOCKY_PUBLIC_URL(self) -> str:
        """Public URL of the Tocky server."""
        return getenv_required('TOCKY_PUBLIC_URL').rstrip('/')

    @cached_property
    def TOCKY_PUBLIC_URL_SCHEME(self) -> str:
        """Scheme of the Tocky public URL."""
        return urlparse(self.TOCKY_PUBLIC_URL).scheme

    @cached_property
    def TOCKY_INTERNAL_URL(self) -> str:
        """Internal URL of the Tocky server."""
        return getenv_required('TOCKY_INTERNAL_URL').rstrip('/')

    @cached_property
    def TOCKY_APPLICATION_ROOT(self) -> str:
        return urlparse(self.TOCKY_PUBLIC_URL).path

    @property
    def TOCKY_DISK_CACHE(self) -> Path:
        """Path to the disk cache directory."""
        return Path(getenv_required('TOCKY_DISK_CACHE')).resolve()

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

    @functools.cached_property
    def cache(self):
        return CacheWithAsync(self.TOCKY_DISK_CACHE)

    @functools.cached_property
    def cache_sync(self):
        from diskcache import Cache
        return Cache(self.TOCKY_DISK_CACHE)

    @property
    def OPENAI_API_KEY(self) -> str:
        return getenv_required('OPENAI_API_KEY')

    @functools.cached_property
    def openai_client(self):
        return OpenAI(api_key=self.OPENAI_API_KEY)

    @property
    def GEMINI_API_KEY(self) -> str:
        return getenv_required("GEMINI_API_KEY")

    @functools.cached_property
    def gemini_openai_client(self):
        """
        This supports some of the features of the OpenAI client, but not all.
        Notably: it does not support batches.
        """
        return OpenAI(
            api_key=self.GEMINI_API_KEY,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )

    @functools.cached_property
    def google_genai_client(self):
        from google import genai

        return genai.Client(
            api_key=self.GEMINI_API_KEY,
        )

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
