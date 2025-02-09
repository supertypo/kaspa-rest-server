import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

_logger = logging.getLogger(__name__)

Base = declarative_base()

primary_sql_uri = os.getenv("SQL_URI", "postgresql+asyncpg://127.0.0.1:5432")
primary_engine = create_async_engine(primary_sql_uri, pool_pre_ping=True, echo=os.getenv("DEBUG") == "true")
async_session = sessionmaker(primary_engine, expire_on_commit=False, class_=AsyncSession)

sql_uri_blocks = os.getenv("SQL_URI_BLOCKS")
if sql_uri_blocks:
    blocks_engine = create_async_engine(sql_uri_blocks, pool_pre_ping=True, echo=os.getenv("DEBUG") == "true")
    async_session_blocks = sessionmaker(blocks_engine, expire_on_commit=False, class_=AsyncSession)
else:
    async_session_blocks = async_session
