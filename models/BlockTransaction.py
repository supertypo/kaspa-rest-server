from sqlalchemy import Column

from dbsession import Base
from models.type_decorators.HashColumn import HashColumn


class BlockTransaction(Base):
    __tablename__ = "blocks_transactions"
    block_hash = Column(HashColumn, primary_key=True)
    transaction_id = Column(HashColumn, primary_key=True)
