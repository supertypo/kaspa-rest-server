# encoding: utf-8
import logging
from datetime import datetime, timezone

from fastapi import Path
from pydantic import BaseModel
from sqlalchemy import func, case
from sqlalchemy.future import select
from starlette.responses import Response

from constants import (
    A_DAY_MS,
    AN_HOUR_MS,
    REGEX_DATE,
    SUBNETWORK_ID_COINBASE,
    SUBNETWORK_ID_REGULAR,
    GENESIS_START_OF_DAY_MS,
)
from dbsession import async_session
from models.Subnetwork import Subnetwork
from models.Transaction import Transaction
from server import app

_logger = logging.getLogger(__name__)


class TransactionCountResponse(BaseModel):
    total: int
    regular: int
    coinbase: int


@app.get("/transactions/count/{day}", response_model=TransactionCountResponse, tags=["Kaspa transactions"])
async def get_transaction_count_for_day(response: Response, day: str = Path(pattern=REGEX_DATE)):
    """
    Count the number of transactions for a specific UTC day (YYYY-MM-DD)
    """
    dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start_ms = int(dt.timestamp() * 1000)
    end_ms = start_ms + A_DAY_MS
    now_ms = datetime.now(tz=timezone.utc).timestamp() * 1000

    if end_ms < now_ms - A_DAY_MS:
        response.headers["Cache-Control"] = "public, max-age=86400"
    elif end_ms < now_ms - AN_HOUR_MS:
        response.headers["Cache-Control"] = "public, max-age=3600"
    else:
        response.headers["Cache-Control"] = "public, max-age=300"

    if start_ms < GENESIS_START_OF_DAY_MS or start_ms > now_ms:
        return {"total": 0, "coinbase": 0, "regular": 0}

    async with async_session() as s:
        result = await s.execute(
            select(
                func.sum(case((Subnetwork.subnetwork_id == SUBNETWORK_ID_COINBASE, 1), else_=0)),
                func.sum(case((Subnetwork.subnetwork_id == SUBNETWORK_ID_REGULAR, 1), else_=0)),
            )
            .select_from(Transaction)
            .join(Subnetwork, Transaction.subnetwork_id == Subnetwork.id)
            .where(Transaction.block_time >= start_ms, Transaction.block_time < end_ms)
        )
        coinbase, regular = result.one()
        return {"total": coinbase + regular, "coinbase": coinbase, "regular": regular}
