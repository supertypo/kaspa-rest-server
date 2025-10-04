from sqlalchemy import Column

from dbsession import Base
from models.type_decorators.HashColumn import HashColumn
from models.type_decorators.HexColumn import HexColumn


class TransactionAcceptance(Base):
    __tablename__ = "transactions_acceptances"
    transaction_id = Column(HashColumn, primary_key=True)
    block_hash = Column(HashColumn)
