# encoding: utf-8
from typing import List

from fastapi import HTTPException
from kaspa_script_address import to_script, to_address
from pydantic import BaseModel
from sqlalchemy import values, column, exists
from sqlalchemy.future import select

from constants import ADDRESS_EXAMPLE
from constants import USE_SCRIPT_FOR_ADDRESS, ADDRESS_PREFIX
from dbsession import async_session
from endpoints import sql_db_only
from models.TxAddrMapping import TxAddrMapping, TxScriptMapping
from server import app


class AddressesActiveRequest(BaseModel):
    addresses: list[str] = [ADDRESS_EXAMPLE]


class AddressesActiveResponse(BaseModel):
    address: str
    active: bool


@app.post(
    "/addresses/active",
    response_model=List[AddressesActiveResponse],
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
        AddressesActiveResponse(address=address, active=(address in addresses_used))
        for address in addresses_active_request.addresses
    ]
