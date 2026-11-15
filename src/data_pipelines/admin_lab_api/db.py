from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from data_pipelines.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url())


def get_db() -> Generator[Session, None, None]:
    session = sessionmaker(bind=get_engine())()
    try:
        yield session
    finally:
        session.close()
