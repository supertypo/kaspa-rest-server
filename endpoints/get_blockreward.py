# encoding: utf-8
from fastapi import HTTPException
from pydantic import BaseModel

from helper.deflationary_table import calc_block_reward
from kaspad.KaspadRpcClient import kaspad_rpc_client
from server import app, kaspad_client


class BlockRewardResponse(BaseModel):
    blockreward: float = 12000132


@app.get("/info/blockreward", response_model=BlockRewardResponse | str, tags=["Kaspa network info"])
async def get_blockreward(stringOnly: bool = False):
    """
    Returns the current blockreward in KAS/block
    """
    rpc_client = await kaspad_rpc_client()
    if rpc_client:
        bdi = await rpc_client.get_block_dag_info()
    else:
        resp = await kaspad_client.request("getBlockDagInfoRequest")
        if resp.get("error"):
            raise HTTPException(500, resp["error"])
        bdi = resp["getBlockDagInfoResponse"]

    daa_score = int(bdi["virtualDaaScore"])
    reward_info = calc_block_reward(daa_score)
    reward = reward_info["current"]

    if not stringOnly:
        return {"blockreward": reward}
    else:
        return f"{reward:.2f}"
