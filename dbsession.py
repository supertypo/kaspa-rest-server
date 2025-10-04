import asyncio
import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from psycopg.types.composite import register_composite, CompositeInfo
from sqlalchemy import event

_logger = logging.getLogger(__name__)

Base = declarative_base()


def _make_engine(uri: str):
    return create_async_engine(
        uri,
        pool_pre_ping=True,
        pool_size=int(os.getenv("SQL_POOL_SIZE", "15")),
        max_overflow=int(os.getenv("SQL_POOL_MAX_OVERFLOW", "0")),
        pool_recycle=int(os.getenv("SQL_POOL_RECYCLE_SECONDS", "1200")),
        echo=os.getenv("DEBUG") == "true",
    )


primary_engine = _make_engine(os.getenv("SQL_URI", "postgresql+psycopg://127.0.0.1:5432"))
async_session_factory = sessionmaker(primary_engine, expire_on_commit=False, class_=AsyncSession)


def async_session():
    return async_session_factory()


if os.getenv("SQL_URI_BLOCKS"):
    blocks_engine = _make_engine(os.getenv("SQL_URI_BLOCKS"))
    async_session_blocks_factory = sessionmaker(blocks_engine, expire_on_commit=False, class_=AsyncSession)

    def async_session_blocks():
        return async_session_blocks_factory()
else:

    def async_session_blocks():
        return async_session_factory()


async def register_pg_types_once():
    async with primary_engine.begin() as conn:
        raw = await conn.get_raw_connection()
        pgconn = raw.driver_connection
        print(type(pgconn))
        print(repr(pgconn))
        pgconn.execute("SET enable_seqscan = off")
        print(type(pgconn))
        print(repr(pgconn))
        register_composite(CompositeInfo.fetch(conn, "transactions_inputs"), pgconn)
        register_composite(CompositeInfo.fetch(conn, "transactions_outputs"), pgconn)


async def init_db():
    await register_pg_types_once()


asyncio.run(init_db())
