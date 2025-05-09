import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

_logger = logging.getLogger(__name__)

Base = declarative_base()

primary_engine = create_async_engine(
    os.getenv("SQL_URI", "postgresql+asyncpg://127.0.0.1:5432"),
    pool_pre_ping=True,
    connect_args={"server_settings": {"enable_seqscan": "off"}},
    echo=os.getenv("DEBUG") == "true",
)
async_session_factory = sessionmaker(primary_engine, expire_on_commit=False, class_=AsyncSession)


def async_session():
    return async_session_factory()


if os.getenv("SQL_URI_BLOCKS"):
    blocks_engine = create_async_engine(
        os.getenv("SQL_URI_BLOCKS"),
        pool_pre_ping=True,
        connect_args={"server_settings": {"enable_seqscan": "off"}},
        echo=os.getenv("DEBUG") == "true",
    )
    async_session_blocks_factory = sessionmaker(blocks_engine, expire_on_commit=False, class_=AsyncSession)

    def async_session_blocks():
        return async_session_blocks_factory()
else:

    def async_session_blocks():
        return async_session_factory()
