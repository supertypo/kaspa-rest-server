from sqlalchemy import Column, Integer, BigInteger, ARRAY, String
from sqlalchemy import SmallInteger

from kaspa_script_address import to_address
from constants import ADDRESS_PREFIX
from dbsession import Base
from helper.PublicKeyType import get_public_key_type
from models.AddressColumn import AddressColumn
from models.type_decorators.HashColumn import HashColumn
from models.type_decorators.HexColumn import HexColumn

from sqlalchemy.types import UserDefinedType



# TransactionInputType = UserDefinedType(
#     "transactions_inputs",
#     [
#         Column("index", SmallInteger),
#         Column("previous_outpoint_hash", HashColumn),
#         Column("previous_outpoint_index", SmallInteger),
#         Column("signature_script", HexColumn),
#         Column("sig_op_count", SmallInteger),
#         Column("previous_outpoint_script", HexColumn),
#         Column("previous_outpoint_amount", BigInteger),
#     ],
# )
#
# TransactionOutputType = UserDefinedType(
#     "transactions_outputs",
#     [
#         Column("index", SmallInteger),
#         Column("amount", BigInteger),
#         Column("script_public_key", HexColumn),
#         Column("script_public_key_address", String),
#     ],
# )

class TransactionsInputsType(UserDefinedType):
    def get_col_spec(self):
        return "transactions_inputs"

class TransactionsOutputsType(UserDefinedType):
    def get_col_spec(self):
        return "transactions_outputs"


class Transaction(Base):
    __tablename__ = "transactions"
    transaction_id = Column(HashColumn, primary_key=True)
    subnetwork_id = Column(SmallInteger)
    hash = Column(HashColumn)
    mass = Column(Integer)
    payload = Column(HexColumn)
    block_time = Column(BigInteger)
    inputs = Column(ARRAY(String))
    outputs = Column(ARRAY(String))
