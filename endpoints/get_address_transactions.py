# encoding: utf-8
import time
from enum import Enum
from typing import List
from constants import DISABLE_LIMITS, TX_COUNT_LIMIT

from fastapi import Path, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.future import select
from starlette.responses import Response

from constants import ADDRESS_EXAMPLE, REGEX_KASPA_ADDRESS
from dbsession import async_session
from endpoints import sql_db_only
from endpoints.get_transactions import search_for_transactions, TxSearch, TxModel
from models.AddressKnown import AddressKnown
from models.Transaction import TransactionOutput, TransactionInput
from server import app

DESC_RESOLVE_PARAM = (
    "Use this parameter if you want to fetch the TransactionInput previous outpoint details."
    " Light fetches only the adress and amount. Full fetches the whole TransactionOutput and "
    "adds it into each TxInput."
)


class AddressesActiveRequest(BaseModel):
    addresses: list[str] = [ADDRESS_EXAMPLE]


class TxIdResponse(BaseModel):
    address: str
    active: bool


class TransactionCount(BaseModel):
    total: int
    limit_exceeded: bool


class AddressName(BaseModel):
    address: str
    name: str


class PreviousOutpointLookupMode(str, Enum):
    no = "no"
    light = "light"
    full = "full"


@app.post(
    "/addresses/active",
    response_model=List[TxIdResponse],
    response_model_exclude_unset=True,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_addresses_active(addresses_active_request: AddressesActiveRequest):
    """
    This endpoint checks if addresses have had any transaction activity in the past.
    It is specifically designed for HD Wallets to verify historical address activity.
    """
    async with async_session() as s:
        addresses = set(addresses_active_request.addresses)
        result = await s.execute(
            select(TransactionOutput.script_public_key_address)
            .distinct(TransactionOutput.script_public_key_address)
            .filter(TransactionOutput.script_public_key_address.in_(addresses))
            .order_by(TransactionOutput.script_public_key_address)
        )
        addresses_used = set(result.scalars().all())
        addresses_remaining = addresses.difference(addresses_used)

        if addresses_remaining:
            result = await s.execute(
                select(TransactionOutput.script_public_key_address)
                .distinct(TransactionOutput.script_public_key_address)
                .select_from(TransactionInput)
                .join(
                    TransactionOutput,
                    (TransactionInput.previous_outpoint_hash == TransactionOutput.transaction_id)
                    & (TransactionInput.previous_outpoint_index == TransactionOutput.index),
                )
                .filter(TransactionOutput.script_public_key_address.in_(addresses_remaining))
                .order_by(TransactionOutput.script_public_key_address)
            )
            addresses_used.update(result.scalars().all())

    return [
        TxIdResponse(address=address, active=(address in addresses_used))
        for address in addresses_active_request.addresses
    ]


@app.get(
    "/addresses/{kaspaAddress}/full-transactions",
    response_model=List[TxModel],
    response_model_exclude_unset=True,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
    deprecated=True,
)
@sql_db_only
async def get_full_transactions_deprecated(
    response: Response,
    kaspaAddress: str = Path(description=f"Kaspa address as string e.g. {ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS),
    limit: int = Query(description="The number of records to get", ge=1, le=500, default=50),
    offset: int = Query(description="Not usable anymore", ge=0, default=0),
    fields: str = "",
    resolve_previous_outpoints: PreviousOutpointLookupMode = Query(default="no", description=DESC_RESOLVE_PARAM),
):
    """
    DEPRECATED due to db model change.
    """
    if offset != 0:
        return []
    return await get_full_transactions(response, kaspaAddress, limit, 0, 0, fields, resolve_previous_outpoints)


@app.get(
    "/addresses/{kaspaAddress}/full-transactions-page",
    response_model=List[TxModel],
    response_model_exclude_unset=True,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
    deprecated=True,
)
@app.get(
    "/addresses/{kaspaAddress}/transactions",
    response_model=List[TxModel],
    response_model_exclude_unset=True,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_full_transactions(
    response: Response,
    kaspaAddress: str = Path(description=f"Kaspa address as string e.g. {ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS),
    limit: int = Query(
        description="The max number of records to get. "
        "For paging combine with using 'before/after' from oldest previous result. "
        "Use value of X-Next-Page-Before/-After as long as header is present to continue paging. "
        "The actual number of transactions returned for each page can be > limit.",
        ge=1,
        le=500,
        default=50,
    ),
    before: int = Query(
        description="Only include transactions with block time before this (epoch-millis)", ge=0, default=None
    ),
    after: int = Query(
        description="Only include transactions with block time after this (epoch-millis)", ge=0, default=None
    ),
    fields: str = "",
    resolve_previous_outpoints: PreviousOutpointLookupMode = Query(default="no", description=DESC_RESOLVE_PARAM),
):
    """
    Get transactions for a given address.
    """
    queryOutputs = (
        select(TransactionOutput.transaction_id, TransactionOutput.block_time)
        .filter(TransactionOutput.script_public_key_address == kaspaAddress)
        .limit(limit)
    )
    queryInputs = (
        select(TransactionInput.transaction_id, TransactionInput.block_time)
        .join(
            TransactionOutput,
            (TransactionInput.previous_outpoint_hash == TransactionOutput.transaction_id)
            & (TransactionInput.previous_outpoint_index == TransactionOutput.index),
        )
        .filter(TransactionOutput.script_public_key_address == kaspaAddress)
        .limit(limit)
    )
    response.headers["X-Page-Count"] = "0"
    if before and after:
        raise HTTPException(status_code=400, detail="Only one of [before, after] can be present")
    elif before:
        if before <= 1636298787842:  # genesis block_time
            return []
        queryOutputs = queryOutputs.filter(TransactionOutput.block_time < before).order_by(
            TransactionOutput.block_time.desc()
        )
        queryInputs = queryInputs.filter(TransactionInput.block_time < before).order_by(
            TransactionInput.block_time.desc()
        )
    elif after:
        if after > int(time.time() * 1000) + 3600000:  # now + 1 hour
            return []
        queryOutputs = queryOutputs.filter(TransactionOutput.block_time > after).order_by(
            TransactionOutput.block_time.asc()
        )
        queryInputs = queryInputs.filter(TransactionInput.block_time > after).order_by(
            TransactionInput.block_time.asc()
        )
    else:
        queryOutputs = queryOutputs.order_by(TransactionOutput.block_time.desc())
        queryInputs = queryInputs.order_by(TransactionInput.block_time.desc())

    async with async_session() as s:
        tx_within_limit = await s.execute(queryOutputs)
        tx_ids_and_block_times = [(x.transaction_id, x.block_time) for x in tx_within_limit.all()]
        tx_within_limit = await s.execute(queryInputs)
        tx_ids_and_block_times.extend([(x.transaction_id, x.block_time) for x in tx_within_limit.all()])
        if not tx_ids_and_block_times:
            return []

        tx_ids_and_block_times = sorted(tx_ids_and_block_times, key=lambda x: x[1] or 0, reverse=True)
        newest_block_time = tx_ids_and_block_times[0][1]
        oldest_block_time = tx_ids_and_block_times[-1][1]
        tx_ids = {tx_id for tx_id, block_time in tx_ids_and_block_times}

        if len(tx_ids_and_block_times) == limit:
            # To avoid gaps when transactions with the same block_time are at the intersection between pages.
            tx_with_same_block_time = await s.execute(
                select(TransactionOutput.transaction_id)
                .filter(TransactionOutput.script_public_key_address == kaspaAddress)
                .filter(
                    or_(
                        TransactionOutput.block_time == newest_block_time,
                        TransactionOutput.block_time == oldest_block_time,
                    )
                )
            )
            tx_ids.update(tx_with_same_block_time.scalars().all())
            tx_with_same_block_time = await s.execute(
                select(TransactionInput.transaction_id, TransactionInput.block_time)
                .join(
                    TransactionOutput,
                    (TransactionInput.previous_outpoint_hash == TransactionOutput.transaction_id)
                    & (TransactionInput.previous_outpoint_index == TransactionOutput.index),
                )
                .filter(TransactionOutput.script_public_key_address == kaspaAddress)
                .filter(
                    or_(
                        TransactionOutput.block_time == newest_block_time,
                        TransactionOutput.block_time == oldest_block_time,
                    )
                )
            )
            tx_ids.update(tx_with_same_block_time.scalars().all())

    response.headers["X-Page-Count"] = str(len(tx_ids))
    if len(tx_ids) >= limit:
        response.headers["X-Next-Page-After"] = str(newest_block_time)
        response.headers["X-Next-Page-Before"] = str(oldest_block_time)

    return await search_for_transactions(TxSearch(transactionIds=list(tx_ids)), fields, resolve_previous_outpoints)


@app.get(
    "/addresses/{kaspaAddress}/transactions-count",
    response_model=TransactionCount,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_transaction_count_for_address(
    response: Response,
    kaspaAddress: str = Path(description=f"Kaspa address as string e.g. {ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS),
):
    """
    Count the number of transactions associated with this address
    """
    tx_ids = set()
    async with async_session() as s:
        if DISABLE_LIMITS:
            result = await s.execute(
                select(TransactionOutput.transaction_id)
                .distinct()
                .filter(TransactionOutput.script_public_key_address == kaspaAddress)
            )
            tx_ids.update((result.scalars().all()))
            result = await s.execute(
                select(TransactionInput.transaction_id)
                .distinct()
                .join(
                    TransactionOutput,
                    (TransactionInput.previous_outpoint_hash == TransactionOutput.transaction_id)
                    & (TransactionInput.previous_outpoint_index == TransactionOutput.index),
                )
                .filter(TransactionOutput.script_public_key_address == kaspaAddress)
            )
            tx_ids.update(result.scalars().all())
        else:
            result = await s.execute(
                select(TransactionOutput.transaction_id)
                .distinct()
                .filter(TransactionOutput.script_public_key_address == kaspaAddress)
                .limit(1 + TX_COUNT_LIMIT)
            )
            tx_ids.update(result.scalars().all())
            if len(tx_ids) < 1 + TX_COUNT_LIMIT:
                result = await s.execute(
                    select(TransactionInput.transaction_id)
                    .distinct()
                    .join(
                        TransactionOutput,
                        (TransactionInput.previous_outpoint_hash == TransactionOutput.transaction_id)
                        & (TransactionInput.previous_outpoint_index == TransactionOutput.index),
                    )
                    .filter(TransactionOutput.script_public_key_address == kaspaAddress)
                    .limit(1 + TX_COUNT_LIMIT - len(tx_ids))
                )
                tx_ids.update(result.scalars().all())

        tx_count = len(tx_ids)
        limit_exceeded = False
        ttl = 8
        if not DISABLE_LIMITS:
            if tx_count > TX_COUNT_LIMIT:
                tx_count = TX_COUNT_LIMIT
                limit_exceeded = True
                ttl = 86400

    response.headers["Cache-Control"] = f"public, max-age={ttl}"
    return TransactionCount(total=tx_count, limit_exceeded=limit_exceeded)


@app.get(
    "/addresses/{kaspaAddress}/name",
    response_model=AddressName | None,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_name_for_address(
    response: Response,
    kaspaAddress: str = Path(
        description="Kaspa address as string e.g. kaspa:qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqkx9awp4e",
        regex=REGEX_KASPA_ADDRESS,
    ),
):
    """
    Get the name for an address
    """
    async with async_session() as s:
        r = (await s.execute(select(AddressKnown).filter(AddressKnown.address == kaspaAddress))).first()

    response.headers["Cache-Control"] = "public, max-age=600"
    if r:
        return AddressName(address=r.AddressKnown.address, name=r.AddressKnown.name)
    else:
        raise HTTPException(
            status_code=404, detail="Address name not found", headers={"Cache-Control": "public, max-age=600"}
        )
