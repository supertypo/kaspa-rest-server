from sqlalchemy import Column, Integer, BigInteger
from sqlalchemy import SmallInteger, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.types import UserDefinedType
from dbsession import Base
from models.type_decorators.HashColumn import HashColumn
from models.type_decorators.HexColumn import HexColumn


class PgComposite(UserDefinedType):
    def __init__(self, name, fields):
        self.name = name
        self.fields = fields

    def get_col_spec(self, **kw):
        return self.name

    def bind_processor(self, dialect):
        return None

    def result_processor(self, dialect, coltype):
        return None


TransactionInputType = PgComposite(
    "transactions_inputs",
    [
        Column("index", SmallInteger),
        Column("previous_outpoint_hash", HashColumn),
        Column("previous_outpoint_index", SmallInteger),
        Column("signature_script", HexColumn),
        Column("sig_op_count", SmallInteger),
        Column("previous_outpoint_script", HexColumn),
        Column("previous_outpoint_amount", BigInteger),
    ],
)

TransactionOutputType = PgComposite(
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
