import asyncio
import logging
import os

import psycopg
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from psycopg.types.composite import register_composite, CompositeInfo
from sqlalchemy import event
from sqlalchemy.engine import make_url
import psycopg
from psycopg.adapt import Loader, Dumper
from psycopg.types import TypeInfo
from psycopg.types.composite import register_composite

_logger = logging.getLogger(__name__)

Base = declarative_base()

def psycopg_dsn_from_sqlalchemy_url(sqlalchemy_url: str) -> str:
    url = make_url(sqlalchemy_url)
    return (
        f"dbname={url.database} "
        f"user={url.username} "
        f"password={url.password or ''} "
        f"host={url.host or 'localhost'} "
        f"port={url.port or 5432}"
    )


def register_bit_base(conn):
    """Register adapter for bit() base type and force mapping for the bit256 domain."""
    # register base 'bit'
    bit_info = TypeInfo.fetch(conn, "bit")

    class BitLoader(Loader):
        def load(self, data):
            # PostgreSQL sends text; keep it as str
            return data

    class BitDumper(Dumper):
        def dump(self, value):
            # psycopg expects bytes
            if isinstance(value, str):
                return value.encode("ascii")
            return value


    conn.adapters.register_loader(bit_info.oid, BitLoader)
    conn.adapters.register_dumper(str, BitDumper)

    # also map bit256 domain OID explicitly to same handlers
    domain_oid = conn.execute("SELECT oid FROM pg_type WHERE typname = 'bit256'").fetchone()[0]
    conn.adapters.register_loader(domain_oid, BitLoader)
    conn.adapters.register_dumper(str, BitDumper)


def register_composite_force(conn, typename):
    """Force psycopg to unwrap domains by creating a temporary view."""
    tmpname = f"_tmp_{typename.replace('.', '_')}"
    conn.execute(f"CREATE TEMP VIEW {tmpname} AS SELECT (NULL::{typename}).*;")
    # Now introspect via this temporary composite alias
    info = CompositeInfo.fetch(conn, tmpname)
    conn.execute(f"DROP VIEW {tmpname}")
    return info


def register_transaction_types_sync(sqlalchemy_url: str):
    dsn = psycopg_dsn_from_sqlalchemy_url(sqlalchemy_url)
    with psycopg.connect(dsn, autocommit=True) as conn:
        print(conn.execute(
            "SELECT typname, typtype, typbasetype::regtype "
            "FROM pg_type WHERE typname IN ('bit','bit256');"
        ).fetchall())

        register_bit_base(conn)

        # Manually unwrap domains for introspection
        in_info = register_composite_force(conn, "transactions_inputs")
        out_info = register_composite_force(conn, "transactions_outputs")

        in_info.register(conn)
        out_info.register(conn)

        print("Composite registration forced and successful.")


def init_db():
    sql_url = os.getenv(
        "SQL_URI",
        "postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
    )
    register_transaction_types_sync(sql_url)



init_db()


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
