from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create the SQLAlchemy engine on demand; no connection is made here."""
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def get_db():
    with sessionmaker(bind=get_engine(), class_=Session, expire_on_commit=False)() as session:
        yield session
