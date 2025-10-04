from sqlalchemy import Column, Integer, BigInteger
from sqlalchemy import SmallInteger, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy_utils import CompositeType

from dbsession import Base
from models.type_decorators.HashColumn import HashColumn
from models.type_decorators.HexColumn import HexColumn


TransactionInputType = CompositeType(
    "transactions_inputs",
    [
        Column("index", SmallInteger),
        Column("previous_outpoint_hash", HexColumn),
        Column("previous_outpoint_index", SmallInteger),
        Column("signature_script", HexColumn),
        Column("sig_op_count", SmallInteger),
        Column("previous_outpoint_script", HexColumn),
        Column("previous_outpoint_amount", BigInteger),
    ],
)


TransactionOutputType = CompositeType(
    "transactions_outputs",
    [
        Column("index", SmallInteger),
        Column("amount", BigInteger),
        Column("script_public_key", HexColumn),
        Column("script_public_key_address", String),
    ],
)


class Transaction(Base):
    __tablename__ = "transactions"
    transaction_id = Column(HashColumn, primary_key=True)
    subnetwork_id = Column(SmallInteger)
    hash = Column(HashColumn)
    mass = Column(Integer)
    payload = Column(HexColumn)
    block_time = Column(BigInteger)
    inputs = Column(ARRAY(TransactionInputType))
    outputs = Column(ARRAY(TransactionOutputType))
