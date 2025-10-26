# encoding: utf-8
import logging
from collections import defaultdict
from typing import List

from fastapi import Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import between, bindparam, exists
from sqlalchemy.future import select
from starlette.responses import Response

from dbsession import async_session, async_session_blocks
from endpoints import sql_db_only
from endpoints.get_transactions import resolve_inputs_from_db, PreviousOutpointLookupMode
from endpoints.get_virtual_chain_blue_score import current_blue_score_data
from helper.utils import add_cache_control
from models.Block import Block
from models.Transaction import Transaction
from models.TransactionAcceptance import TransactionAcceptance
from server import app

_logger = logging.getLogger(__name__)


class VcTxInput(BaseModel):
    previous_outpoint_hash: str
    previous_outpoint_index: int
    signature_script: str | None
    previous_outpoint_script: str | None
    previous_outpoint_address: str | None
    previous_outpoint_amount: int | None


class VcTxOutput(BaseModel):
    script_public_key: str
    script_public_key_address: str
    amount: int


class VcTxModel(BaseModel):
    transaction_id: str
    is_accepted: bool = True
    inputs: List[VcTxInput] | None
    outputs: List[VcTxOutput] | None


class VcBlockModel(BaseModel):
    hash: str
    blue_score: int
    daa_score: int | None
    timestamp: int | None
    transactions: List[VcTxModel] | None


@app.get(
    "/virtual-chain",
    response_model=List[VcBlockModel],
    tags=["Kaspa virtual chain"],
    summary="EXPERIMENTAL - EXPECT BREAKING CHANGES: Get virtual chain transactions by blue score",
    response_model_exclude_none=True,
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_virtual_chain_transactions(
    response: Response,
    blue_score_gte: int = Query(..., ge=0, alias="blueScoreGte", description="Divisible by limit", example=106329050),
    limit: int = Query(default=10, enum=[10, 100]),
    resolve_inputs: bool = Query(default=False, alias="resolveInputs"),
    include_coinbase: bool = Query(default=True, alias="includeCoinbase"),
):
    if limit not in [10, 100]:
        raise HTTPException(400, "'limit' must be in [10, 100]")
    if blue_score_gte % limit != 0:
        raise HTTPException(400, f"'blueScoreGte' must be divisible by limit ({limit})")
    blue_score_lt = blue_score_gte + limit

    add_cache_control(blue_score_lt, None, response)
    if 0 < current_blue_score_data["blue_score"] < blue_score_gte:
        return []

    async with async_session_blocks() as session_blocks:
        chain_blocks = await session_blocks.execute(
            select(
                Block.hash,
                Block.blue_score,
                Block.daa_score,
                Block.timestamp,
            )
            .where(between(Block.blue_score, blue_score_gte, blue_score_lt - 1))
            .where(exists(select(1).where(TransactionAcceptance.block_hash == Block.hash)))
            .order_by(Block.blue_score)
        )
        chain_blocks = chain_blocks.mappings().all()

    if not chain_blocks:
        return []

    async with async_session() as session:
        accepted_txs = await session.execute(
            select(TransactionAcceptance.block_hash, TransactionAcceptance.transaction_id).where(
                TransactionAcceptance.block_hash.in_(bindparam("block_hashes", expanding=True))
            ),
            {"block_hashes": [x["hash"] for x in chain_blocks]},
        )
        accepted_txs = accepted_txs.mappings().all()

    if not accepted_txs:
        return []

    transaction_ids = []
    accepted_txs_dict = defaultdict(list)
    for accepted_tx in accepted_txs:
        transaction_ids.append(accepted_tx["transaction_id"])
        accepted_txs_dict[accepted_tx["block_hash"]].append(accepted_tx["transaction_id"])
    del accepted_txs
    logging.warning(f"TXS: {len(transaction_ids)}")
    print(type(chain_blocks), len(chain_blocks))
    print([type(x["hash"]) for x in chain_blocks])
    print(transaction_ids, [type(x) for x in transaction_ids])
    async with async_session() as session:
        tx_list = (
            (
                await session.execute(
                    select(Transaction).where(
                        Transaction.transaction_id.in_(bindparam("transaction_ids", expanding=True))
                    ),
                    {"transaction_ids": transaction_ids},
                )
            )
            .scalars()
            .all()
        )

    tx_inputs = await resolve_inputs_from_db(
        [vars(i) for tx in tx_list for i in (tx.inputs or []) if i],
        PreviousOutpointLookupMode.light if resolve_inputs else PreviousOutpointLookupMode.no,
    )
    tx_outputs = {}
    for o in [vars(o) for tx in tx_list for o in (tx.outputs or []) if o]:
        tx_outputs.setdefault(o["transaction_id"], []).append(o)

    results = []
    for chain_block in chain_blocks:
        transactions = []
        for tx_id in accepted_txs_dict[chain_block["hash"]]:
            inputs = tx_inputs.get(tx_id)
            outputs = tx_outputs.get(tx_id)
            if include_coinbase or inputs:
                transactions.append(VcTxModel(transaction_id=tx_id, inputs=inputs, outputs=outputs))

        if transactions:
            results.append(
                VcBlockModel(
                    hash=chain_block["hash"],
                    blue_score=chain_block["blue_score"],
                    daa_score=chain_block["daa_score"],
                    timestamp=chain_block["timestamp"],
                    transactions=transactions,
                )
            )

    return results
