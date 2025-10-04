from dataclasses import dataclass, field

from kaspa_script_address import to_address

from constants import ADDRESS_PREFIX
from helper.PublicKeyType import get_public_key_type


def bit256_to_hex(value):
    if value is None:
        return None
    return f"{int(value, 2):064x}"


def bytea_to_hex(value):
    if value is None:
        return None
    return value.hex()


@dataclass
class TransactionInput:
    transaction_id: str | None = field(default=None, init=False)
    index: int
    previous_outpoint_hash: str
    previous_outpoint_index: int
    signature_script: str | None
    sig_op_count: int | None
    previous_outpoint_script: str | None
    previous_outpoint_address: str | None = field(default=None, init=False)
    previous_outpoint_amount: int | None

    def __post_init__(self):
        self.previous_outpoint_hash = bit256_to_hex(self.previous_outpoint_hash)
        self.signature_script = bytea_to_hex(self.signature_script)
        self.previous_outpoint_script = bytea_to_hex(self.previous_outpoint_script)
        if self.previous_outpoint_script:
            self.previous_outpoint_address = to_address(ADDRESS_PREFIX, self.previous_outpoint_script)


@dataclass
class TransactionOutput:
    transaction_id: str | None = field(default=None, init=False)
    index: int
    amount: int
    script_public_key: str | None
    script_public_key_address: str | None
    script_public_key_type: str | None = field(default=None, init=False)

    def __post_init__(self):
        self.script_public_key = bytea_to_hex(self.script_public_key)
        if self.script_public_key:
            self.script_public_key_type = get_public_key_type(self.script_public_key)
            if not self.script_public_key_address:
                self.script_public_key_address = to_address(ADDRESS_PREFIX, self.script_public_key)
