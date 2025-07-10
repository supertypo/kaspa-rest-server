# encoding: utf-8
import time
from typing import List

from fastapi import Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.future import select
from starlette.responses import Response

from constants import TOP_ADDRESSES
from dbsession import async_session_blocks
from endpoints import sql_db_only
from models.TopScript import TopScript
from server import app


class TopAddress(BaseModel):
    timestamp: int
    rank: int
    address: str
    amount: int


@app.get(
    "/addresses/top",
    response_model=List[TopAddress],
    tags=["Kaspa addresses"],
    summary="Get top Kaspa addresses (rich list)",
    description="Get top addresses, use 'before' to get historical data (must be aligned to a full hour).",
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_addresses_top(response: Response, before: int | None = Query(None)):
    if not TOP_ADDRESSES:
        raise HTTPException(status_code=503, detail="Top addresses is disabled")

    response.headers["Cache-Control"] = "public, max-age=60"
    if before is not None:
        if before % 3_600_000 != 0:
            raise HTTPException(status_code=400, detail="'before' must be aligned to a full hour")
        now_ms = int(time.time() * 1000)
        if before < now_ms - 3_600_000:
            response.headers["Cache-Control"] = "public, max-age=3600"
        elif before > now_ms + 600_000:
            return []

    async with async_session_blocks() as s:
        ts_subquery = select(func.max(TopScript.timestamp))
        if before is not None:
            ts_subquery = ts_subquery.where(TopScript.timestamp < before)
        top_scripts = (
            (
                await s.execute(
                    select(TopScript)
                    .where(TopScript.timestamp == ts_subquery.scalar_subquery())
                    .order_by(TopScript.rank)
                )
            )
            .scalars()
            .all()
        )

    return [
        TopAddress(timestamp=ts.timestamp, rank=ts.rank, address=ts.script_public_key_address, amount=ts.amount)
        for ts in top_scripts
    ]
