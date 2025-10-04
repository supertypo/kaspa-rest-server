from sqlalchemy import Column

from dbsession import Base
from models.type_decorators.HashColumn import HashColumn


class BlockParent(Base):
    __tablename__ = "block_parent"
    block_hash = Column(HashColumn, primary_key=True)
    parent_hash = Column(HashColumn, primary_key=True)
