from sqlalchemy import Column, Integer, BigInteger, ARRAY
from sqlalchemy import SmallInteger
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql.type_api import UserDefinedType

from dbsession import Base
from models.type_decorators.HashColumn import HashColumn
from models.type_decorators.HexColumn import HexColumn


class TransactionInputType(UserDefinedType):
    def get_col_spec(self):
        return "transactions_inputs"


class TransactionOutputType(UserDefinedType):
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
    _inputs = Column("inputs", ARRAY(TransactionInputType))
    _outputs = Column("outputs", ARRAY(TransactionOutputType))

    @hybrid_property
    def inputs(self):
        if not self._inputs:
            return None
        for i in self._inputs:
            i.transaction_id = self.transaction_id
        return self._inputs

    @hybrid_property
    def outputs(self):
        if self._outputs is None:
            return None
        for o in self._outputs:
            o.transaction_id = self.transaction_id
        return self._outputs
