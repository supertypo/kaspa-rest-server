# encoding: utf-8
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from fastapi.params import Query
from fastapi_utils.tasks import repeat_every
from pydantic import BaseModel
from sqlalchemy import select, text, func
from starlette.responses import Response

from dbsession import async_session_blocks
from endpoints.get_virtual_chain_blue_score import get_virtual_selected_parent_blue_score
from helper.difficulty_calculation import bits_to_difficulty
from models.Block import Block
from models.HashrateHistory import HashrateHistory
from server import app

_logger = logging.getLogger(__name__)


class HashrateHistoryResponse(BaseModel):
    daaScore: int
    blueScore: int
    timestamp: int
    date_time: str
    bits: int
    difficulty: int
    hashrate_kh: int


_hashrate_table_exists = False
_hashrate_history_updated = False


@app.get("/info/hashrate/history", response_model=list[HashrateHistoryResponse], tags=["Kaspa network info"])
async def get_hashrate_history(response: Response, limit: Optional[int] = Query(default=None, enum=[10])):
    """
    Returns historical hashrate in KH/s with a resolution of ~3 hours between samples.
    """
    if not _hashrate_table_exists or not _hashrate_history_updated:
        raise HTTPException(status_code=503, detail="Hashrate history is not available")
    if limit == 10:
        response.headers["Cache-Control"] = "public, max-age=600"
    elif limit:
        raise HTTPException(status_code=400, detail="Invalid limit")
    else:
        response.headers["Cache-Control"] = "public, max-age=3600"

    async with async_session_blocks() as s:
        stmt = select(HashrateHistory).order_by(HashrateHistory.daa_score.desc())
        if limit:
            stmt = stmt.limit(limit)
        result = await s.execute(stmt)
        return [
            {
                "daaScore": sample.daa_score,
                "blueScore": sample.blue_score,
                "timestamp": sample.timestamp,
                "date_time": datetime.fromtimestamp(sample.timestamp / 1000, tz=timezone.utc).isoformat(
                    timespec="milliseconds"
                ),
                "bits": sample.bits,
                "difficulty": (difficulty := bits_to_difficulty(sample.bits)),
                "hashrate_kh": (difficulty * 2 * (1 if sample.blue_score < 108554145 else 10)) / 1_000,
            }
            for sample in result.scalars().all()
        ]


async def create_hashrate_history_table():
    global _hashrate_table_exists

    async with async_session_blocks() as s:
        await acquire_hashrate_history_lock(s)
        try:
            check_table_exists_sql = text(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = '{HashrateHistory.__tablename__}'
                );
            """)
            result = await s.execute(check_table_exists_sql)
            _hashrate_table_exists = result.scalar()

            if _hashrate_table_exists:
                _logger.debug("Hashrate history: Table already exists")
                return

            _logger.warning("Hashrate history table does not exist, attempting to create it")
            create_table_sql = f"""
                CREATE TABLE IF NOT EXISTS {HashrateHistory.__tablename__} (
                    daa_score BIGINT PRIMARY KEY,
                    blue_score BIGINT,
                    timestamp BIGINT,
                    bits BIGINT
                );
            """
            await s.execute(text(create_table_sql))
            create_index_sql = f"""
                CREATE INDEX IF NOT EXISTS {HashrateHistory.__tablename__}_blue_score_idx ON {HashrateHistory.__tablename__} (blue_score);
            """
            await s.execute(text(create_index_sql))
            await s.commit()
            _hashrate_table_exists = True
        except Exception as e:
            _logger.exception(e)
            _logger.error(
                f"Hashrate history: Failed to create table, create it manually: \n{create_table_sql}{create_index_sql}"
            )
        finally:
            await release_hashrate_history_lock(s)


@repeat_every(seconds=1800)
async def update_hashrate_history():
    global _hashrate_history_updated
    sample_interval_hours = 3
    batch_size = 1000

    if not _hashrate_table_exists:
        _logger.warning(f"Hashrate history: Skipping sampling as table '{HashrateHistory.__tablename__}' doesn't exist")
        return

    _logger.info("Hashrate history: Sampling hashrate history")
    sample_count = 0
    batch = []
    async with async_session_blocks() as s:
        await acquire_hashrate_history_lock(s)
        try:
            result = await s.execute(select(func.max(HashrateHistory.blue_score)))
            max_blue_score = result.scalar_one_or_none() or 0
            bps = 1 if max_blue_score < 108554145 else 10  # Crescendo
            next_blue_score = 0
            if max_blue_score > 0:
                next_blue_score = max_blue_score + (bps * 3600 * sample_interval_hours)

            current_blue_score = await get_virtual_selected_parent_blue_score()
            while int(current_blue_score["blueScore"]) > next_blue_score:
                result = await s.execute(
                    select(Block)
                    .where(Block.blue_score > next_blue_score)
                    .order_by(Block.blue_score, Block.daa_score)
                    .limit(1 if next_blue_score > 1236000 else 2)  # blue_score was reset 2021-11-22
                )
                blocks = result.scalars().all()
                if not blocks:
                    break
                if len(blocks) == 2:
                    if abs(blocks[0].daa_score - blocks[1].daa_score) < 100_000:
                        blocks = [blocks[0]]  # keep both only if they are on different sides of the reset
                for block in blocks:
                    if block.blue_score and block.daa_score and block.timestamp and block.bits:
                        batch.append(
                            HashrateHistory(
                                blue_score=block.blue_score,
                                daa_score=block.daa_score,
                                timestamp=block.timestamp,
                                bits=block.bits,
                            )
                        )
                        if len(batch) >= batch_size:
                            s.add_all(batch)
                            await s.commit()
                            batch.clear()
                        sample_count += 1
                        t = datetime.fromtimestamp(block.timestamp / 1000, tz=timezone.utc).isoformat(
                            timespec="seconds"
                        )
                        _logger.info(
                            f"Sampled: daa={block.daa_score}, blue_score={block.blue_score}, timestamp={t}, bits={block.bits}"
                        )
                block = blocks[0]
                if block.blue_score < 6550000:  # sample more in the period before complete dataset
                    next_blue_score = block.blue_score + 3600
                else:
                    bps = 1 if block.blue_score < 108554145 else 10
                    next_blue_score = block.blue_score + (bps * 3600 * sample_interval_hours)
            if batch:
                s.add_all(batch)
                await s.commit()
        except Exception as e:
            _logger.exception(e)
            _logger.error("Hashrate history: Sampling failed")
        finally:
            await release_hashrate_history_lock(s)
    _hashrate_history_updated = True
    _logger.info(f"Hashrate history: Sampling complete, {sample_count} samples committed")


async def acquire_hashrate_history_lock(s):
    try:
        result = await s.execute(text("SELECT pg_try_advisory_lock(123100)"))
        if not result.scalar():
            _logger.debug("Hashrate history: waiting for advisory lock")
            await s.execute(text("SELECT pg_advisory_lock(123100)"))
        _logger.debug("Hashrate history: Acquired advisory lock (123100)")
    except Exception as e:
        _logger.exception(e)
        _logger.error("Hashrate history: unable to acquire advisory lock (123100)")
        raise e


async def release_hashrate_history_lock(s):
    await s.execute(text("SELECT pg_advisory_unlock(123100)"))
