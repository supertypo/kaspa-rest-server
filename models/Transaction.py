from sqlalchemy import Column, Integer, BigInteger
from sqlalchemy import SmallInteger
from sqlalchemy.dialects.postgresql import JSONB

from dbsession import Base
from models.type_decorators.HashColumn import HashColumn
from models.type_decorators.HexColumn import HexColumn


class Transaction(Base):
    __tablename__ = "transactions_json"
    transaction_id = Column(HashColumn, primary_key=True)
    subnetwork_id = Column(SmallInteger)
    hash = Column(HashColumn)
    mass = Column(Integer)
    payload = Column(HexColumn)
    block_time = Column(BigInteger)
    _inputs = Column("inputs", JSONB)
    _outputs = Column("outputs", JSONB)

    @property
    def inputs(self):
        if not self._inputs:
            return self._inputs
        for item in self._inputs:
            for k in ("signature_script", "previous_outpoint_script"):
                v = item.get(k)
                if isinstance(v, str) and v.startswith("\\x"):
                    item[k] = v.replace("\\x", "")
        return self._inputs

    @property
    def outputs(self):
        if not self._outputs:
            return self._outputs
        for item in self._outputs:
            spk = item.get("script_public_key")
            if isinstance(spk, str) and spk.startswith("\\x"):
                item["script_public_key"] = spk.replace("\\x", "")
        return self._outputs
