from sqlalchemy import TypeDecorator, BLOB
from sqlalchemy.dialects.postgresql import BYTEA, ARRAY


class HexArrayColumn(TypeDecorator):
    impl = ARRAY(BYTEA)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "mysql":
            return dialect.type_descriptor(BLOB)
        return dialect.type_descriptor(ARRAY(BYTEA))

    def process_result_value(self, value, dialect):
        if dialect.name == "mysql":
            return [value[i : i + 32].hex() for i in range(0, len(value), 32)] if value else []
        return [v.hex() for v in value] if value else []
