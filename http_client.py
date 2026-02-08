# encoding: utf-8
"""
Shared HTTP client session for making external API requests.
This module is intentionally minimal to avoid circular imports.
"""

from typing import Optional
import aiohttp

# Global HTTP session for external API requests with connection pooling
http_session: Optional[aiohttp.ClientSession] = None


def create_http_session() -> aiohttp.ClientSession:
    """Create and return a new HTTP session with connection pooling."""
    return aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=20, limit_per_host=3), timeout=aiohttp.ClientTimeout(total=3)
    )


async def close_http_session() -> None:
    """Close the global HTTP session if it exists."""
    global http_session
    if http_session:
        await http_session.close()
        http_session = None


def setup_lifecycle(app) -> None:
    """Register startup and shutdown handlers for the HTTP session."""

    @app.on_event("startup")
    async def startup_http_client():
        global http_session
        http_session = create_http_session()

    @app.on_event("shutdown")
    async def shutdown_http_client():
        await close_http_session()
