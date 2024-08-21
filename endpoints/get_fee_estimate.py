# encoding: utf-8

from fastapi import HTTPException
from typing import List
from server import app, kaspad_client
from pydantic import BaseModel, Field


class FeeEstimateBucket(BaseModel):
    feerate: int = 1
    estimatedSeconds: float = 0.004


class FeeEstimateResponse(BaseModel):
    priorityBucket: FeeEstimateBucket = Field(..., description="Top-priority feerate")
    normalBuckets: List[FeeEstimateBucket] = Field(
        ..., description="Normal priority feerate values. The first value of this vector is guaranteed to exist."
    )
    lowBuckets: List[FeeEstimateBucket] = Field(
        ..., description="Low priority feerate values. The first value of this vector is guaranteed to exist."
    )


@app.get("/info/fee-estimate", response_model=FeeEstimateResponse, tags=["Kaspa network info"])
async def get_fee_estimate():
    """
    Get fee estimate from Kaspad.

    For all buckets, feerate values represent fee/mass of a transaction in `sompi/gram` units.
    Given a feerate value recommendation, calculate the required fee by
    taking the transaction mass and multiplying it by feerate: `fee = feerate * mass(tx)`
    """
    resp = await kaspad_client.request("getFeeEstimateRequest")
    if resp is None:
        raise HTTPException(status_code=501, detail="Kaspad does not support fee estimate")
    return resp["getFeeEstimateResponse"]["estimate"]
