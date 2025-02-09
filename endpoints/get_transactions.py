# encoding: utf-8

import logging
from collections import defaultdict
from enum import Enum
from typing import List

from fastapi import Path, HTTPException, Query
from pydantic import BaseModel, parse_obj_as
from sqlalchemy.future import select

from dbsession import async_session, async_session_blocks
from endpoints import filter_fields, sql_db_only
from models.Block import Block
from models.BlockTransaction import BlockTransaction
from models.Subnetwork import Subnetwork
from models.Transaction import Transaction, TransactionOutput, TransactionInput
from models.TransactionAcceptance import TransactionAcceptance
from server import app, kaspad_client

_logger = logging.getLogger(__name__)

DESC_RESOLVE_PARAM = (
    "Use this parameter if you want to fetch the TransactionInput previous outpoint details."
    " Light fetches only the address and amount. Full fetches the whole TransactionOutput and "
    "adds it into each TxInput."
)


class TxOutput(BaseModel):
    transaction_id: str
    index: int
    amount: int
    script_public_key: str
    script_public_key_address: str
    script_public_key_type: str
    accepting_block_hash: str | None

    class Config:
        orm_mode = True


class TxInput(BaseModel):
    transaction_id: str
    index: int
    previous_outpoint_hash: str
    previous_outpoint_index: str
    previous_outpoint_resolved: TxOutput | None
    previous_outpoint_address: str | None
    previous_outpoint_amount: int | None
    signature_script: str
    sig_op_count: str

    class Config:
        orm_mode = True


class TxModel(BaseModel):
    subnetwork_id: str | None
    transaction_id: str | None
    hash: str | None
    mass: str | None
    payload: str | None
    block_hash: List[str] | None
    block_time: int | None
    is_accepted: bool | None
    accepting_block_hash: str | None
    accepting_block_blue_score: int | None
    accepting_block_time: int | None
    inputs: List[TxInput] | None
    outputs: List[TxOutput] | None

    class Config:
        orm_mode = True


class TxSearch(BaseModel):
    transactionIds: List[str]


class PreviousOutpointLookupMode(str, Enum):
    no = "no"
    light = "light"
    full = "full"


@app.get(
    "/transactions/{transactionId}",
    response_model=TxModel,
    tags=["Kaspa transactions"],
    response_model_exclude_unset=True,
)
@sql_db_only
async def get_transaction(
    transactionId: str = Path(regex="[a-f0-9]{64}"),
    blockHash: str = Query(None, description="Specify a containing block (if known) for faster lookup"),
    inputs: bool = True,
    outputs: bool = True,
    resolve_previous_outpoints: PreviousOutpointLookupMode = Query(
        default=PreviousOutpointLookupMode.no, description=DESC_RESOLVE_PARAM
    ),
):
    """
    Get details for a given transaction id
    """
    async with async_session_blocks() as session_blocks:
        async with async_session() as session:
            transaction = None
            if blockHash:
                block_hashes = [blockHash]
                transaction = await get_transaction_from_kaspad([blockHash], transactionId, inputs, outputs)
                if transaction:
                    logging.debug(f"Found transaction {transactionId} in kaspad")
            else:
                block_hashes = (
                    (
                        await session_blocks.execute(
                            select(BlockTransaction.block_hash).filter(BlockTransaction.transaction_id == transactionId)
                        )
                    )
                    .scalars()
                    .all()
                )
                if block_hashes:
                    logging.debug(f"Found block_hashes for {transactionId} in database")
                    transaction = await get_transaction_from_kaspad(block_hashes, transactionId, inputs, outputs)
                    if transaction:
                        logging.debug(f"Found transaction {transactionId} in kaspad")

            if not transaction:
                tx = await session.execute(
                    select(Transaction, Subnetwork)
                    .join(Subnetwork, Transaction.subnetwork_id == Subnetwork.id)
                    .filter(Transaction.transaction_id == transactionId)
                )
                tx = tx.first()

                if tx:
                    logging.debug(f"Found transaction {transactionId} in database")
                    transaction = {
                        "subnetwork_id": tx.Subnetwork.subnetwork_id,
                        "transaction_id": tx.Transaction.transaction_id,
                        "hash": tx.Transaction.hash,
                        "mass": tx.Transaction.mass,
                        "payload": tx.Transaction.payload,
                        "block_hash": block_hashes,
                        "block_time": tx.Transaction.block_time,
                    }

                    if inputs and resolve_previous_outpoints not in ["light", "full"]:
                        tx_inputs = await session.execute(
                            select(TransactionInput).filter(TransactionInput.transaction_id == transactionId)
                        )
                        tx_inputs = tx_inputs.scalars().all()
                        transaction["inputs"] = (
                            parse_obj_as(List[TxInput], sorted(tx_inputs, key=lambda x: x.index)) if tx_inputs else None
                        )

                    if outputs:
                        tx_outputs = await session.execute(
                            select(TransactionOutput).filter(TransactionOutput.transaction_id == transactionId)
                        )
                        tx_outputs = tx_outputs.scalars().all()
                        transaction["outputs"] = (
                            parse_obj_as(List[TxOutput], sorted(tx_outputs, key=lambda x: x.index))
                            if tx_outputs
                            else None
                        )

            if transaction:
                accepted_transaction_id, accepting_block_hash = (
                    await session.execute(
                        select(
                            TransactionAcceptance.transaction_id,
                            TransactionAcceptance.block_hash,
                        ).filter(TransactionAcceptance.transaction_id == transactionId)
                    )
                ).one_or_none() or (None, None)
                transaction["is_accepted"] = accepted_transaction_id is not None

                if accepting_block_hash:
                    accepting_block_blue_score, accepting_block_time = (
                        await session_blocks.execute(
                            select(
                                Block.blue_score,
                                Block.timestamp,
                            ).filter(Block.hash == accepting_block_hash)
                        )
                    ).one_or_none() or (None, None)
                    transaction["accepting_block_hash"] = accepting_block_hash
                    transaction["accepting_block_blue_score"] = accepting_block_blue_score
                    transaction["accepting_block_time"] = accepting_block_time
                    if not accepting_block_blue_score:
                        accepting_block = await get_block_from_kaspad(accepting_block_hash)
                        if accepting_block and accepting_block["header"]:
                            transaction["accepting_block_blue_score"] = accepting_block["header"]["blueScore"]
                            transaction["accepting_block_time"] = accepting_block["header"]["timestamp"]

                if inputs and resolve_previous_outpoints in ["light", "full"]:
                    tx_inputs = await session.execute(
                        select(TransactionInput, TransactionOutput)
                        .outerjoin(
                            TransactionOutput,
                            (TransactionOutput.transaction_id == TransactionInput.previous_outpoint_hash)
                            & (TransactionOutput.index == TransactionInput.previous_outpoint_index),
                        )
                        .filter(TransactionInput.transaction_id == transactionId)
                    )
                    tx_inputs = tx_inputs.all()

                    for tx_in, tx_prev_output in tx_inputs:
                        if tx_prev_output:
                            tx_in.previous_outpoint_amount = tx_prev_output.amount
                            tx_in.previous_outpoint_address = tx_prev_output.script_public_key_address
                            if resolve_previous_outpoints == "full":
                                tx_in.previous_outpoint_resolved = tx_prev_output

                    tx_inputs = [x[0] for x in tx_inputs]
                    transaction["inputs"] = (
                        parse_obj_as(List[TxInput], sorted(tx_inputs, key=lambda x: x.index)) if tx_inputs else None
                    )

    if transaction:
        return transaction
    else:
        raise HTTPException(
            status_code=404, detail="Transaction not found", headers={"Cache-Control": "public, max-age=3"}
        )


@app.post(
    "/transactions/search", response_model=List[TxModel], tags=["Kaspa transactions"], response_model_exclude_unset=True
)
@sql_db_only
async def search_for_transactions(
    txSearch: TxSearch,
    fields: str = "",
    resolve_previous_outpoints: PreviousOutpointLookupMode = Query(
        default=PreviousOutpointLookupMode.no, description=DESC_RESOLVE_PARAM
    ),
):
    """
    Get block information for a given block id
    """
    if len(txSearch.transactionIds) > 1000:
        raise HTTPException(422, "Too many transaction ids")

    if resolve_previous_outpoints in ["light", "full"] and len(txSearch.transactionIds) > 50:
        raise HTTPException(422, "Temporary issue: Transaction ids count is limited to 50 for light and full searches.")

    fields = fields.split(",") if fields else []

    async with async_session() as session:
        tx_list = (
            await session.execute(
                select(
                    Transaction,
                    Subnetwork,
                    TransactionAcceptance.transaction_id.label("accepted_transaction_id"),
                    TransactionAcceptance.block_hash.label("accepting_block_hash"),
                )
                .join(Subnetwork, Transaction.subnetwork_id == Subnetwork.id)
                .outerjoin(TransactionAcceptance, Transaction.transaction_id == TransactionAcceptance.transaction_id)
                .filter(Transaction.transaction_id.in_(txSearch.transactionIds))
                .order_by(Transaction.block_time.desc())
            )
        ).all()

        async with async_session_blocks() as session_blocks:
            accepting_block_hashes = [row.accepting_block_hash for row in tx_list if row.accepting_block_hash]
            tx_acceptances = await session_blocks.execute(
                select(
                    Block.hash.label("accepting_block_hash"),
                    Block.blue_score.label("accepting_block_blue_score"),
                    Block.timestamp.label("accepting_block_time"),
                ).filter(Block.hash.in_(accepting_block_hashes))
            )
            tx_acceptances = {row.accepting_block_hash: row for row in tx_acceptances.all()}

            tx_blocks = await session_blocks.execute(
                select(BlockTransaction).filter(BlockTransaction.transaction_id.in_(txSearch.transactionIds))
            )
            tx_blocks_dict = defaultdict(list)
            for row in tx_blocks.scalars().all():
                tx_blocks_dict[row.transaction_id].append(row.block_hash)
            tx_blocks = tx_blocks_dict

        if not fields or "inputs" in fields:
            if resolve_previous_outpoints in ["light", "full"]:
                tx_inputs = await session.execute(
                    select(TransactionInput, TransactionOutput)
                    .outerjoin(
                        TransactionOutput,
                        (TransactionOutput.transaction_id == TransactionInput.previous_outpoint_hash)
                        & (TransactionOutput.index == TransactionInput.previous_outpoint_index),
                    )
                    .filter(TransactionInput.transaction_id.in_(txSearch.transactionIds))
                    .order_by(TransactionInput.transaction_id, TransactionInput.index)
                )

                tx_inputs_dict = defaultdict(list)
                for tx_input, tx_prev_output in tx_inputs.all():
                    if tx_prev_output:
                        tx_input.previous_outpoint_amount = tx_prev_output.amount
                        tx_input.previous_outpoint_address = tx_prev_output.script_public_key_address
                        if resolve_previous_outpoints == "full":
                            tx_input.previous_outpoint_resolved = tx_prev_output
                    else:
                        tx_input.previous_outpoint_amount = None
                        tx_input.previous_outpoint_address = None
                        if resolve_previous_outpoints == "full":
                            tx_input.previous_outpoint_resolved = None
                    tx_inputs_dict[tx_input.transaction_id].append(tx_input)
            else:
                tx_inputs = await session.execute(
                    select(TransactionInput)
                    .filter(TransactionInput.transaction_id.in_(txSearch.transactionIds))
                    .order_by(TransactionInput.transaction_id, TransactionInput.index)
                )
                tx_inputs_dict = defaultdict(list)
                for tx_input in tx_inputs.scalars().all():
                    tx_inputs_dict[tx_input.transaction_id].append(tx_input)
            tx_inputs = tx_inputs_dict
        else:
            tx_inputs = {}

        if not fields or "outputs" in fields:
            tx_outputs = await session.execute(
                select(TransactionOutput)
                .filter(TransactionOutput.transaction_id.in_(txSearch.transactionIds))
                .order_by(TransactionOutput.transaction_id, TransactionOutput.index)
            )
            tx_outputs_dict = defaultdict(list)
            for tx_output in tx_outputs.scalars().all():
                tx_outputs_dict[tx_output.transaction_id].append(tx_output)
            tx_outputs = tx_outputs_dict
        else:
            tx_outputs = {}

    block_cache = {}
    results = []
    for tx in tx_list:
        accepting_block_blue_score = None
        accepting_block_time = None
        accepting_block = tx_acceptances.get(tx.accepting_block_hash)
        if accepting_block:
            accepting_block_blue_score = accepting_block.accepting_block_blue_score
            accepting_block_time = accepting_block.accepting_block_time
        else:
            if tx.accepting_block_hash:
                if tx.accepting_block_hash not in block_cache:
                    block_cache[tx.accepting_block_hash] = await get_block_from_kaspad(tx.accepting_block_hash)
                accepting_block = block_cache[tx.accepting_block_hash]
                if accepting_block:
                    accepting_block_blue_score = accepting_block.get("header", {}).get("blueScore")
                    accepting_block_time = accepting_block.get("header", {}).get("timestamp")

        result = filter_fields(
            {
                "subnetwork_id": tx.Subnetwork.subnetwork_id,
                "transaction_id": tx.Transaction.transaction_id,
                "hash": tx.Transaction.hash,
                "mass": tx.Transaction.mass,
                "payload": tx.Transaction.payload,
                "block_hash": tx_blocks.get(tx.Transaction.transaction_id),
                "block_time": tx.Transaction.block_time,
                "is_accepted": True if tx.accepted_transaction_id else False,
                "accepting_block_hash": tx.accepting_block_hash,
                "accepting_block_blue_score": accepting_block_blue_score,
                "accepting_block_time": accepting_block_time,
                "outputs": tx_outputs.get(tx.Transaction.transaction_id),
                "inputs": tx_inputs.get(tx.Transaction.transaction_id),
            },
            fields,
        )
        results.append(result)
    return results


async def get_transaction_from_kaspad(block_hashes, transactionId, includeInputs, includeOutputs):
    resp = await kaspad_client.request("getBlockRequest", params={"hash": block_hashes[0], "includeTransactions": True})
    if "block" in resp["getBlockResponse"] and "transactions" in resp["getBlockResponse"]["block"]:
        for tx in resp["getBlockResponse"]["block"]["transactions"]:
            if tx["verboseData"]["transactionId"] == transactionId:
                return {
                    "subnetwork_id": tx["subnetworkId"],
                    "transaction_id": tx["verboseData"]["transactionId"],
                    "hash": tx["verboseData"]["hash"],
                    "mass": tx["verboseData"]["computeMass"]
                    if tx["verboseData"].get("computeMass", "0") != "0"
                    else None,
                    "payload": tx["payload"] if tx["payload"] else None,
                    "block_hash": block_hashes,
                    "block_time": tx["verboseData"]["blockTime"],
                    "inputs": [
                        {
                            "transaction_id": tx["verboseData"]["transactionId"],
                            "index": tx_in_idx,
                            "previous_outpoint_hash": tx_in["previousOutpoint"]["transactionId"],
                            "previous_outpoint_index": tx_in["previousOutpoint"]["index"],
                            "signature_script": tx_in["signatureScript"],
                            "sig_op_count": tx_in["sigOpCount"],
                        }
                        for tx_in_idx, tx_in in enumerate(tx["inputs"])
                    ]
                    if includeInputs and tx["inputs"]
                    else None,
                    "outputs": [
                        {
                            "transaction_id": tx["verboseData"]["transactionId"],
                            "index": tx_out_idx,
                            "amount": tx_out["amount"],
                            "script_public_key": tx_out["scriptPublicKey"]["scriptPublicKey"],
                            "script_public_key_address": tx_out["verboseData"]["scriptPublicKeyAddress"],
                            "script_public_key_type": tx_out["verboseData"]["scriptPublicKeyType"],
                        }
                        for tx_out_idx, tx_out in enumerate(tx["outputs"])
                    ]
                    if includeOutputs and tx["outputs"]
                    else None,
                }


async def get_block_from_kaspad(block_hash):
    if block_hash:
        resp = await kaspad_client.request("getBlockRequest", params={"hash": block_hash, "includeTransactions": False})
        return resp.get("getBlockResponse", {}).get("block")
