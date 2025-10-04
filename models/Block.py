from sqlalchemy import Column, BigInteger, SmallInteger

from dbsession import Base
from models.type_decorators.ByteColumn import ByteColumn
from models.type_decorators.HashArrayColumn import HashArrayColumn
from models.type_decorators.HashColumn import HashColumn
from models.type_decorators.HexColumn import HexColumn


class Block(Base):
    __tablename__ = "blocks"
    hash = Column(HashColumn, primary_key=True)
    accepted_id_merkle_root = Column(HashColumn)
    merge_set_blues_hashes = Column(HashArrayColumn)
    merge_set_reds_hashes = Column(HashArrayColumn)
    selected_parent_hash = Column(HashColumn)
    bits = Column(BigInteger)
    blue_score = Column(BigInteger)
    blue_work = Column(HexColumn)
    daa_score = Column(BigInteger)
    hash_merkle_root = Column(HashColumn)
    nonce = Column(ByteColumn)
    pruning_point = Column(HashColumn)
    timestamp = Column(BigInteger)
    utxo_commitment = Column(HashColumn)
    version = Column(SmallInteger)
