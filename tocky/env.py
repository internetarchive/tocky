from dataclasses import dataclass
import functools
import os
from pathlib import Path


@functools.cache
def get_env() -> 'TockyEnv':
    return TockyEnv.from_env()


@dataclass
class TockyEnv:
    TOCKY_SERVER_NAME: str
    """e.g. 'localhost:5000'"""

    TOCKY_APPLICATION_ROOT: str
    """e.g. '/tocky' or ''"""

    TOCKY_PREFERRED_URL_SCHEME: str
    """e.g. 'http' or 'https'"""

    TOCKY_QUEUE_DB_PATH: Path
    
    @property
    def TOCKY_SERVER_KEY(self) -> str:
        return os.environ['TOCKY_SERVER_KEY']
    
    @property
    def AZURE_SUBSCRIPTION_KEY(self) -> str | None:
        return os.environ.get('AZURE_SUBSCRIPTION_KEY')
    
    @property
    def AZURE_ENDPOINT(self) -> str | None:
        return os.environ.get('AZURE_ENDPOINT')

    def get_app_prefix(self) -> str:
        return f'{self.TOCKY_PREFERRED_URL_SCHEME}://{self.TOCKY_SERVER_NAME}{self.TOCKY_APPLICATION_ROOT}'

    @staticmethod
    def from_env() -> 'TockyEnv':
        return TockyEnv(
            TOCKY_SERVER_NAME=os.environ['TOCKY_SERVER_NAME'].rstrip('/'),
            TOCKY_APPLICATION_ROOT=os.environ['TOCKY_APPLICATION_ROOT'].rstrip('/'),
            TOCKY_PREFERRED_URL_SCHEME=os.environ['TOCKY_PREFERRED_URL_SCHEME'],
            TOCKY_QUEUE_DB_PATH=Path(os.environ['TOCKY_QUEUE_DB_PATH']),
        )
