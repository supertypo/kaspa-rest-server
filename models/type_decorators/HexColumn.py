from sqlalchemy import TypeDecorator, BLOB


class HexColumn(TypeDecorator):
    impl = BLOB
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return bytes.fromhex(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return value.hex()
        return value
