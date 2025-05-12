# encoding: utf-8
import time
from enum import Enum
from typing import List

from kaspa_script_address import to_script, to_address

from constants import USE_SCRIPT_FOR_ADDRESS, TX_COUNT_LIMIT, ADDRESS_PREFIX

from fastapi import Path, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, values, column, exists
from sqlalchemy.future import select
from starlette.responses import Response

from constants import ADDRESS_EXAMPLE, REGEX_KASPA_ADDRESS
from dbsession import async_session
from endpoints import sql_db_only
from endpoints.get_transactions import search_for_transactions, TxSearch, TxModel
from helper.utils import add_cache_control
from models.AddressKnown import AddressKnown
from models.TxAddrMapping import TxAddrMapping, TxScriptMapping
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


class TransactionsReceivedAndSpent(BaseModel):
    tx_received: str
    tx_spent: str | None
    # received_amount: int = 38240000000


class TransactionForAddressResponse(BaseModel):
    transactions: List[TransactionsReceivedAndSpent]


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


@app.get(
    "/addresses/{kaspaAddress}/full-transactions",
    response_model=List[TxModel],
    response_model_exclude_unset=True,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_full_transactions_for_address(
    response: Response,
    kaspaAddress: str = Path(description=f"Kaspa address as string e.g. {ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS),
    limit: int = Query(description="The number of records to get", ge=1, le=500, default=50),
    offset: int = Query(description="The offset from which to get records", ge=0, default=0),
    fields: str = "",
    resolve_previous_outpoints: PreviousOutpointLookupMode = Query(default="no", description=DESC_RESOLVE_PARAM),
):
    """
    Get all transactions for a given address from database.
    And then get their related full transaction data
    """
    try:
        script = to_script(kaspaAddress)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid address: {kaspaAddress}")

    async with async_session() as s:
        if USE_SCRIPT_FOR_ADDRESS:
            tx_within_limit_offset = await s.execute(
                select(TxScriptMapping.transaction_id, TxScriptMapping.block_time)
                .filter(TxScriptMapping.script_public_key == script)
                .limit(limit)
                .offset(offset)
                .order_by(TxScriptMapping.block_time.desc())
            )
        else:
            tx_within_limit_offset = await s.execute(
                select(TxAddrMapping.transaction_id, TxAddrMapping.block_time)
                .filter(TxAddrMapping.address == kaspaAddress)
                .limit(limit)
                .offset(offset)
                .order_by(TxAddrMapping.block_time.desc())
            )

    tx_ids_in_page = []
    max_block_time = 0
    for tx_id, block_time in tx_within_limit_offset.all():
        tx_ids_in_page.append(tx_id)
        if block_time is not None and block_time > max_block_time:
            max_block_time = block_time

    if offset and max_block_time:
        delta_seconds = time.time() - int(max_block_time) / 1000
        if delta_seconds < 600:
            ttl = 8
        elif delta_seconds < 86400:  # 1 day
            ttl = 60
        else:
            ttl = 600
    else:
        ttl = 8
    response.headers["Cache-Control"] = f"public, max-age={ttl}"

    return await search_for_transactions(TxSearch(transactionIds=tx_ids_in_page), fields, resolve_previous_outpoints)


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
        script_addresses = set()
        for address in addresses:
            try:
                script_addresses.add(to_script(address))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid address: {address}")

        if USE_SCRIPT_FOR_ADDRESS:
            v = values(column("script_public_key", TxScriptMapping.__table__.c.script_public_key.type), name="v").data(
                [(addr,) for addr in script_addresses]
            )
            result = await s.execute(
                select(v.c.script_public_key).where(
                    exists().where(TxScriptMapping.script_public_key == v.c.script_public_key)
                )
            )
            addresses_used = set(to_address(ADDRESS_PREFIX, s) for s in result.scalars().all())
        else:
            v = values(column("address", TxAddrMapping.__table__.c.address.type), name="v").data(
                [(addr,) for addr in addresses]
            )
            result = await s.execute(select(v.c.address).where(exists().where(TxAddrMapping.address == v.c.address)))
            addresses_used = set(result.scalars().all())

    return [
        TxIdResponse(address=address, active=(address in addresses_used))
        for address in addresses_active_request.addresses
    ]


@app.get(
    "/addresses/{kaspaAddress}/full-transactions-page",
    response_model=List[TxModel],
    response_model_exclude_unset=True,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_full_transactions_for_address_page(
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
        description="Only include transactions with block time before this (epoch-millis)", ge=0, default=0
    ),
    after: int = Query(
        description="Only include transactions with block time after this (epoch-millis)", ge=0, default=0
    ),
    fields: str = "",
    resolve_previous_outpoints: PreviousOutpointLookupMode = Query(default="no", description=DESC_RESOLVE_PARAM),
):
    """
    Get all transactions for a given address from database.
    And then get their related full transaction data
    """
    try:
        script = to_script(kaspaAddress)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid address: {kaspaAddress}")

    if USE_SCRIPT_FOR_ADDRESS:
        query = (
            select(TxScriptMapping.transaction_id, TxScriptMapping.block_time)
            .filter(TxScriptMapping.script_public_key == script)
            .limit(limit)
        )
    else:
        query = (
            select(TxAddrMapping.transaction_id, TxAddrMapping.block_time)
            .filter(TxAddrMapping.address == kaspaAddress)
            .limit(limit)
        )

    response.headers["X-Page-Count"] = "0"
    if before != 0 and after != 0:
        raise HTTPException(status_code=400, detail="Only one of [before, after] can be present")
    elif before != 0:
        if before <= 1636298787842:  # genesis block_time
            return []
        if USE_SCRIPT_FOR_ADDRESS:
            query = query.filter(TxScriptMapping.block_time < before).order_by(TxScriptMapping.block_time.desc())
        else:
            query = query.filter(TxAddrMapping.block_time < before).order_by(TxAddrMapping.block_time.desc())
    elif after != 0:
        if after > int(time.time() * 1000) + 3600000:  # now + 1 hour
            return []
        if USE_SCRIPT_FOR_ADDRESS:
            query = query.filter(TxScriptMapping.block_time > after).order_by(TxScriptMapping.block_time.asc())
        else:
            query = query.filter(TxAddrMapping.block_time > after).order_by(TxAddrMapping.block_time.asc())
    else:
        if USE_SCRIPT_FOR_ADDRESS:
            query = query.order_by(TxScriptMapping.block_time.desc())
        else:
            query = query.order_by(TxAddrMapping.block_time.desc())

    async with async_session() as s:
        tx_within_limit_before = await s.execute(query)

        tx_ids_and_block_times = [(x.transaction_id, x.block_time) for x in tx_within_limit_before.all()]
        if not tx_ids_and_block_times:
            return []

        tx_ids_and_block_times = sorted(tx_ids_and_block_times, key=lambda x: x[1], reverse=True)
        newest_block_time = tx_ids_and_block_times[0][1]
        oldest_block_time = tx_ids_and_block_times[-1][1]
        tx_ids = {tx_id for tx_id, block_time in tx_ids_and_block_times}
        if len(tx_ids_and_block_times) == limit:
            # To avoid gaps when transactions with the same block_time are at the intersection between pages.
            if USE_SCRIPT_FOR_ADDRESS:
                tx_with_same_block_time = await s.execute(
                    select(TxScriptMapping.transaction_id)
                    .filter(TxScriptMapping.script_public_key == script)
                    .filter(
                        or_(
                            TxScriptMapping.block_time == newest_block_time,
                            TxScriptMapping.block_time == oldest_block_time,
                        )
                    )
                )
            else:
                tx_with_same_block_time = await s.execute(
                    select(TxAddrMapping.transaction_id)
                    .filter(TxAddrMapping.address == kaspaAddress)
                    .filter(
                        or_(
                            TxAddrMapping.block_time == newest_block_time, TxAddrMapping.block_time == oldest_block_time
                        )
                    )
                )
            tx_ids.update([x for x in tx_with_same_block_time.scalars().all()])

    response.headers["X-Page-Count"] = str(len(tx_ids))
    if len(tx_ids) >= limit:
        response.headers["X-Next-Page-After"] = str(newest_block_time)
        response.headers["X-Next-Page-Before"] = str(oldest_block_time)

    res = await search_for_transactions(TxSearch(transactionIds=list(tx_ids)), fields, resolve_previous_outpoints)
    if before:
        add_cache_control(None, before, response)
    elif after and len(tx_ids) >= limit:
        max_block_time = max((r.get("block_time") for r in res))
        add_cache_control(None, max_block_time, response)
    return res


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
    try:
        script = to_script(kaspaAddress)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid address: {kaspaAddress}")

    async with async_session() as s:
        if not TX_COUNT_LIMIT:
            if USE_SCRIPT_FOR_ADDRESS:
                result = await s.execute(select(func.count()).filter(TxScriptMapping.script_public_key == script))
            else:
                result = await s.execute(select(func.count()).filter(TxAddrMapping.address == kaspaAddress))
        else:
            if USE_SCRIPT_FOR_ADDRESS:
                result = await s.execute(
                    select(func.count()).select_from(
                        select(1)
                        .filter(TxScriptMapping.script_public_key == script)
                        .limit(TX_COUNT_LIMIT + 1)
                        .subquery()
                    )
                )
            else:
                result = await s.execute(
                    select(func.count()).select_from(
                        select(1).filter(TxAddrMapping.address == kaspaAddress).limit(TX_COUNT_LIMIT + 1).subquery()
                    )
                )
        tx_count = result.scalar()

        limit_exceeded = False
        if TX_COUNT_LIMIT and tx_count > TX_COUNT_LIMIT:
            tx_count = TX_COUNT_LIMIT
            limit_exceeded = True

        if tx_count >= 1_000_000:
            ttl = 600
        elif tx_count >= 100_000:
            ttl = 60
        elif tx_count >= 10_000:
            ttl = 20
        else:
            ttl = 8

    response.headers["Cache-Control"] = f"public, max-age={ttl}"
    return TransactionCount(total=tx_count, limit_exceeded=limit_exceeded)


@app.get(
    "/addresses/names",
    response_model=List[AddressName],
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_addresses_names(response: Response):
    """
    Get the name for an address
    """
    response.headers["Cache-Control"] = "public, max-age=60"
    async with async_session() as s:
        rows = (await s.execute(select(AddressKnown))).scalars().all()
        return [{"name": r.name, "address": r.address} for r in rows]


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
    try:
        to_script(kaspaAddress)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid address: {kaspaAddress}")

    async with async_session() as s:
        r = (await s.execute(select(AddressKnown).filter(AddressKnown.address == kaspaAddress))).first()

    response.headers["Cache-Control"] = "public, max-age=600"
    if r:
        return AddressName(address=r.AddressKnown.address, name=r.AddressKnown.name)
    else:
        raise HTTPException(
            status_code=404, detail="Address name not found", headers={"Cache-Control": "public, max-age=600"}
        )
