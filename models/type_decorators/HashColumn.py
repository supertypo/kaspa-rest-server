from sqlalchemy import TypeDecorator
from sqlalchemy.dialects.postgresql import BIT


class HashColumn(TypeDecorator):
    impl = BIT(256)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return bin(int(value, 16))[2:].zfill(256)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return f"{int(value, 2):064x}"
