# encoding: utf-8
import logging
from collections import defaultdict
from typing import List

from fastapi import Query, HTTPException
from kaspa_script_address import to_address
from pydantic import BaseModel
from sqlalchemy import between, bindparam
from sqlalchemy.future import select
from starlette.responses import Response

from constants import ADDRESS_PREFIX
from dbsession import async_session, async_session_blocks
from endpoints import sql_db_only
from endpoints.get_virtual_chain_blue_score import current_blue_score_data
from helper.PublicKeyType import get_public_key_type
from helper.utils import add_cache_control
from models.Block import Block
from models.Transaction import TransactionInput, TransactionOutput
from models.TransactionAcceptance import TransactionAcceptance
from server import app

_logger = logging.getLogger(__name__)


class VcTxInput(BaseModel):
    previous_outpoint_hash: str
    previous_outpoint_index: int
    previous_outpoint_address: str | None
    previous_outpoint_amount: int | None


class VcTxOutput(BaseModel):
    amount: int
    script_public_key_address: str
    script_public_key_type: str


class VcTxModel(BaseModel):
    transaction_id: str
    inputs: List[VcTxInput] | None
    outputs: List[VcTxOutput] | None


class VcBlockModel(BaseModel):
    hash: str
    blue_score: int
    daa_score: int | None
    timestamp: int | None
    transactions: List[VcTxModel] | None


@app.get(
    "/v2/virtual-chain/transactions",
    response_model=List[VcBlockModel],
    tags=["Kaspa virtual chain"],
    response_model_exclude_unset=True,
)
@sql_db_only
async def get_virtual_chain_transactions(
    response: Response,
    blue_score_gte: int = Query(..., ge=0, alias="blueScoreGte"),
    limit: int = Query(default=10, enum=[10, 100]),
    include_coinbase: bool = Query(default=True, alias="includeCoinbase"),
):
    """
    EXPERIMENTAL - EXPECT BREAKING CHANGES: Get virtual chain transactions by blue score.
    """
    if limit not in [10, 100]:
        raise HTTPException(400, "'limit' must be in [10, 100]")
    if blue_score_gte % 10 != 0:
        raise HTTPException(400, "'blueScoreGte' must be divisible by 10")
    blue_score_lt = blue_score_gte + limit

    add_cache_control(blue_score_lt, None, response)
    if 0 < current_blue_score_data["blue_score"] < blue_score_gte:
        return []

    async with async_session_blocks() as session_blocks:
        accepted_txs = await session_blocks.execute(
            select(
                TransactionAcceptance.transaction_id,
                Block.hash,
                Block.blue_score,
                Block.daa_score,
                Block.timestamp,
            )
            .select_from(Block)
            .join(TransactionAcceptance, Block.hash == TransactionAcceptance.block_hash)
            .where(between(Block.blue_score, blue_score_gte, blue_score_lt - 1))
            .order_by(Block.blue_score)
        )
        accepted_txs = accepted_txs.mappings().all()

    if not accepted_txs:
        return []

    transaction_ids = []
    chain_blocks_dict = defaultdict(list)
    for accepted_tx in accepted_txs:
        transaction_ids.append(accepted_tx["transaction_id"])
        key = (accepted_tx["hash"], accepted_tx["blue_score"], accepted_tx["daa_score"], accepted_tx["timestamp"])
        chain_blocks_dict[key].append(accepted_tx["transaction_id"])
    del accepted_txs

    async with async_session() as session:
        tx_inputs = await session.execute(
            select(
                TransactionInput.transaction_id,
                TransactionInput.index,
                TransactionInput.previous_outpoint_hash,
                TransactionInput.previous_outpoint_index,
                TransactionInput.previous_outpoint_script,
                TransactionInput.previous_outpoint_amount,
            )
            .where(TransactionInput.transaction_id.in_(bindparam("transaction_ids", expanding=True)))
            .order_by(TransactionInput.transaction_id, TransactionInput.index),
            {"transaction_ids": transaction_ids},
        )
        tx_inputs = tx_inputs.mappings().all()

    tx_inputs_dict = defaultdict(list)
    for tx_input in tx_inputs:
        tx_input = dict(tx_input)
        tx_input["previous_outpoint_address"] = to_address(ADDRESS_PREFIX, tx_input["previous_outpoint_script"])
        tx_inputs_dict[tx_input["transaction_id"]].append(tx_input)
    del tx_inputs

    if not include_coinbase:
        transaction_ids = [tx_id for tx_id in transaction_ids if tx_id in tx_inputs_dict]
    if not transaction_ids:
        return []

    async with async_session() as session:
        tx_outputs = await session.execute(
            select(
                TransactionOutput.transaction_id,
                TransactionOutput.index,
                TransactionOutput.amount,
                TransactionOutput.script_public_key,
            )
            .where(TransactionOutput.transaction_id.in_(bindparam("transaction_ids", expanding=True)))
            .order_by(TransactionOutput.transaction_id, TransactionOutput.index),
            {"transaction_ids": transaction_ids},
        )
        tx_outputs = tx_outputs.mappings().all()

    tx_outputs_dict = defaultdict(list)
    for tx_output in tx_outputs:
        tx_output = dict(tx_output)
        tx_output["script_public_key_address"] = to_address(ADDRESS_PREFIX, tx_output["script_public_key"])
        tx_output["script_public_key_type"] = get_public_key_type(tx_output["script_public_key"])
        tx_outputs_dict[tx_output["transaction_id"]].append(tx_output)
    del tx_outputs

    results = []
    for (block_hash, blue_score, daa_score, timestamp), tx_ids in chain_blocks_dict.items():
        transactions = []
        for tx_id in tx_ids:
            inputs = [VcTxInput(**inp) for inp in tx_inputs_dict[tx_id]] or None
            outputs = [VcTxOutput(**out) for out in tx_outputs_dict[tx_id]] or None
            if include_coinbase or inputs:
                transactions.append(VcTxModel(transaction_id=tx_id, inputs=inputs, outputs=outputs))

        if transactions:
            results.append(
                VcBlockModel(
                    hash=block_hash,
                    blue_score=blue_score,
                    daa_score=daa_score,
                    timestamp=timestamp,
                    transactions=transactions,
                )
            )

    return results
