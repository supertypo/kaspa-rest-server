# encoding: utf-8
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict

from pydantic import BaseModel
from sqlalchemy import select

from dbsession import async_session
from models.Transaction import Transaction
from server import app, kaspad_client
from endpoints.get_virtual_chain_blue_score import current_blue_score_data


class KaspadResponse(BaseModel):
    kaspadHost: str = ""
    serverVersion: str = "0.12.6"
    isUtxoIndexed: bool = True
    isSynced: bool = True
    p2pId: str = "1231312"


class HealthResponse(BaseModel):
    kaspadServers: List[KaspadResponse]
    currentBlueScore: int = None
    dbCheck: Dict[str, str]  # report database status


@app.get("/info/health", response_model=HealthResponse, tags=["Kaspa network info"])
async def health_state():
    """
    Checks health by verifying node sync status, the recency of the latest block in
    the database, and returns each node's status, version, and the current blue score.

    If the database check fails, `dbCheck` will show an "error" status and relevant
    message. If the latest block is older than 10 minutes, it will indicate an outdated
    status. Otherwise, the status is marked as "valid".
    """
    await kaspad_client.initialize_all()

    kaspads = []

    # dbCheck status
    db_check_status = {"status": "valid", "message": "Database is up-to-date"}

    # check the recency of the latest transaction's block time in the database
    try:
        async with async_session() as s:
            last_block_time = (
                await s.execute(
                    select(Transaction.block_time)
                    .limit(1)
                    .order_by(Transaction.block_time.desc())
                )
            ).scalar()

        time_diff = datetime.now() - datetime.fromtimestamp(last_block_time / 1000)

        if time_diff > timedelta(minutes=10):
            db_check_status = {
                "status": "error",
                "message": "Block age older than 10 minutes",
            }
    except Exception:
        db_check_status = {"status": "error", "message": "Database unavailable"}

    for i, kaspad_info in enumerate(kaspad_client.kaspads):
        kaspads.append(
            {
                "isSynced": kaspad_info.is_synced,
                "isUtxoIndexed": kaspad_info.is_utxo_indexed,
                "p2pId": hashlib.sha256(kaspad_info.p2p_id.encode()).hexdigest(),
                "kaspadHost": f"KASPAD_HOST_{i + 1}",
                "serverVersion": kaspad_info.server_version,
            }
        )

    current_blue_score = current_blue_score_data.get("blue_score")

    return {
        "kaspadServers": kaspads,
        "currentBlueScore": current_blue_score,
        "dbCheck": db_check_status,
    }
