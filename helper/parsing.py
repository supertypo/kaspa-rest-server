def split_bytes(source: bytes, size: int = 32):
    """
    Splits bytes, returns a list
    """
    return [source[i : i + size].hex() for i in range(0, len(source), size)] if source else []
