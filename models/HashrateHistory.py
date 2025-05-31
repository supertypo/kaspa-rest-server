from sqlalchemy import Column, BigInteger, SmallInteger

from dbsession import Base
from models.type_decorators.HexColumn import HexColumn
from models.type_decorators.HexArrayColumn import HexArrayColumn
from models.type_decorators.ByteColumn import ByteColumn


class HashrateHistory(Base):
    __tablename__ = "hashrate_history"
    blue_score = Column(BigInteger, primary_key=True)
    daa_score = Column(BigInteger)
    timestamp = Column(BigInteger)
    bits = Column(BigInteger)
