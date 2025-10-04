from sqlalchemy import TypeDecorator
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import BIT


class HashArrayColumn(TypeDecorator):
    impl = ARRAY(BIT(256))
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return [bin(int(v, 16))[2:].zfill(256) if isinstance(v, str) else v for v in value]
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return [f"{int(v, 2):064x}" if v else v for v in value]
        return value
