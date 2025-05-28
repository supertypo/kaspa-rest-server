# encoding: utf-8
from kaspa import RpcClient, Resolver

from constants import KASPAD_WRPC_URL


async def kaspad_rpc_client() -> RpcClient:
    if KASPAD_WRPC_URL:
        if not hasattr(kaspad_rpc_client, "client"):
            if KASPAD_WRPC_URL == "resolver":
                kaspad_rpc_client.client = RpcClient(resolver=Resolver())
            else:
                kaspad_rpc_client.client = RpcClient(url=KASPAD_WRPC_URL)
        if not kaspad_rpc_client.client.is_connected:
            await kaspad_rpc_client.client.connect()
        return kaspad_rpc_client.client
