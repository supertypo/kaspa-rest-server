# encoding: utf-8
import logging
import os
import re
from asyncio import wait_for
from typing import List

from fastapi import Path, HTTPException
from kaspa_script_address import to_script, to_address
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.future import select
from starlette.responses import Response

from constants import REGEX_KASPA_ADDRESS, ADDRESS_EXAMPLE, ADDRESS_PREFIX, SCRIPTS_UTXOS_LIMIT, USE_SCRIPT_FOR_ADDRESS
from dbsession import async_session
from kaspad.KaspadRpcClient import kaspad_rpc_client
from models.ScriptUtxoCount import ScriptUtxoCount
from server import app, kaspad_client

_logger = logging.getLogger(__name__)
_utxo_count_table_exists: bool | None = None


class OutpointModel(BaseModel):
    transactionId: str = "ef62efbc2825d3ef9ec1cf9b80506876ac077b64b11a39c8ef5e028415444dc9"
    index: int = 0


class ScriptPublicKeyModel(BaseModel):
    scriptPublicKey: str = "20c5629ce85f6618cd3ed1ac1c99dc6d3064ed244013555c51385d9efab0d0072fac"


class UtxoModel(BaseModel):
    amount: str = ("11501593788",)
    scriptPublicKey: ScriptPublicKeyModel
    blockDaaScore: str = "18867232"
    isCoinbase: bool = False


class UtxoResponse(BaseModel):
    address: str = ADDRESS_EXAMPLE
    outpoint: OutpointModel
    utxoEntry: UtxoModel


@app.get(
    "/addresses/{kaspaAddress}/utxos",
    response_model=List[UtxoResponse],
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
async def get_utxos_for_address(
    response: Response,
    kaspaAddress: str = Path(description=f"Kaspa address as string e.g. {ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS),
):
    """
    Lists all open utxo for a given kaspa address.

    Returns HTTP 507 if the address holds more than `SCRIPTS_UTXOS_LIMIT` UTXOs.
    """
    try:
        to_script(kaspaAddress)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid address: {kaspaAddress}")

    over_limit = await _get_over_limit_addresses([kaspaAddress])
    if over_limit:
        raise HTTPException(
            status_code=507,
            detail=f"Address UTXO count exceeds the limit of {SCRIPTS_UTXOS_LIMIT}",
        )

    utxos = await get_utxos([kaspaAddress])

    ttl = 8
    if len(utxos) > 100_000:
        ttl = 3600
    elif len(utxos) > 10_000:
        ttl = 600
    elif len(utxos) > 1_000:
        ttl = 20

    response.headers["Cache-Control"] = f"public, max-age={ttl}"
    return (utxo for utxo in utxos if utxo["address"] == kaspaAddress)


class UtxoRequest(BaseModel):
    addresses: list[str] = [ADDRESS_EXAMPLE]


@app.post(
    "/addresses/utxos",
    response_model=List[UtxoResponse],
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
async def get_utxos_for_addresses(body: UtxoRequest):
    """
    Lists all open utxo for a given list of kaspa addresses.

    Addresses that hold more than `SCRIPTS_UTXOS_LIMIT` UTXOs are silently omitted from the response.
    """
    if body.addresses is None:
        return []

    for kaspaAddress in body.addresses:
        try:
            if not re.search(REGEX_KASPA_ADDRESS, kaspaAddress):
                raise ValueError
            to_script(kaspaAddress)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid address: {kaspaAddress}")

    over_limit = await _get_over_limit_addresses(body.addresses)
    allowed = [a for a in body.addresses if a not in over_limit]
    if not allowed:
        return []

    return await get_utxos(allowed)


async def get_utxos(addresses):
    rpc_client = await kaspad_rpc_client()
    request = {"addresses": addresses}
    if rpc_client:
        utxos = await wait_for(rpc_client.get_utxos_by_addresses(request), 60)
        for utxo in utxos["entries"]:
            spk = utxo["utxoEntry"]["scriptPublicKey"].lstrip("0")
            if len(spk) % 2 == 1:
                spk = "0" + spk
            utxo["utxoEntry"]["scriptPublicKey"] = {"scriptPublicKey": spk}
    else:
        resp = await kaspad_client.request("getUtxosByAddressesRequest", request, timeout=60)
        if resp.get("error"):
            raise HTTPException(500, resp["error"])
        utxos = resp["getUtxosByAddressesResponse"]

    return utxos["entries"]


async def _get_over_limit_addresses(addresses: list[str]) -> set[str]:
    """
    Returns the subset of *addresses* whose UTXO count exceeds SCRIPTS_UTXOS_LIMIT
    according to the script_utxo_counts table.  Returns an empty set when the table
    does not exist or the primary DB is not configured.
    """
    if not os.getenv("SQL_URI"):
        return set()

    global _utxo_count_table_exists
    async with async_session() as s:
        if _utxo_count_table_exists is None:
            result = await s.execute(
                text(
                    "SELECT EXISTS ("
                    "SELECT FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'script_utxo_counts'"
                    ");"
                )
            )
            _utxo_count_table_exists = result.scalar()
            if _utxo_count_table_exists:
                _logger.info("script_utxo_counts helper table detected")
            else:
                _logger.info("script_utxo_counts helper table NOT found – UTXO count limiting disabled")

        if not _utxo_count_table_exists:
            return set()

        if USE_SCRIPT_FOR_ADDRESS:
            result = await s.execute(
                select(ScriptUtxoCount.script_public_key).where(
                    ScriptUtxoCount.script_public_key.in_([to_script(addr) for addr in addresses]),
                    ScriptUtxoCount.count > SCRIPTS_UTXOS_LIMIT,
                )
            )
            return {to_address(ADDRESS_PREFIX, spk) for spk in result.scalars()}
        else:
            result = await s.execute(
                select(ScriptUtxoCount.script_public_key_address).where(
                    ScriptUtxoCount.script_public_key_address.in_(addresses),
                    ScriptUtxoCount.count > SCRIPTS_UTXOS_LIMIT,
                )
            )
            return set(result.scalars())
