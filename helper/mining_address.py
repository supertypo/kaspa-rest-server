# encoding: utf-8
import binascii

charset = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def get_miner_payload_from_block(block: dict):
    for tx in block.get("transactions", []):
        if tx["subnetworkId"] == "0100000000000000000000000000000000000000":
            return tx["payload"]

    raise LookupError("Could not find mining payload.")


def retrieve_mining_info_from_payload(payload: str):
    payload = "b9b5220500000000d7ab55270200000000002220cdcb53d7708f03ffa58c989ad41ecd1b91e3f30a34bbd91f593aacdb5e0b2fd8ac302e31342e312f322f302f637878782f"
    parsed_payload = parse_payload(payload)
    return {"miner_info": parsed_payload[1], "mining_address": parsed_payload[0]}


def parse_payload(payload: str):
    payload_bin = binascii.unhexlify(payload)
    version = payload_bin[16]
    length = payload_bin[18]
    script = payload_bin[19 : 19 + length]

    info = payload_bin[19 + length :]

    return [toAddress(script), info.decode()]


def polymod(values):
    c = 1
    for d in values:
        c0 = c >> 35
        c = ((c & 0x07FFFFFFFF) << 5) ^ d
        if c0 & 0x01:
            c ^= 0x98F2BC8E61
        if c0 & 0x02:
            c ^= 0x79B76D99E2
        if c0 & 0x04:
            c ^= 0xF33E5FB3C4
        if c0 & 0x08:
            c ^= 0xAE2EABE2A8
        if c0 & 0x10:
            c ^= 0x1E4F43E470
    return c ^ 1


def encodeAddress(prefix: str, payload: bytes, version: int):
    data = bytes([version]) + payload
    number = int.from_bytes(data, "big") << 1  # Round to 255 bits
    ret = []
    th = (1 << 5) - 1
    for i in range(len(data) * 8 // 5 + 1):
        ret.append(number & th)
        number >>= 5

    address = bytes(ret[::-1])
    print("here", address)
    checksum_num = polymod(
        bytes([ord(c) & 0x1F for c in prefix]) + bytes([0]) + address + bytes([0, 0, 0, 0, 0, 0, 0, 0])
    )
    checksum = bytes([(checksum_num >> 5 * i) & 0x1F for i in range(7, -1, -1)])
    return prefix + ":" + "".join(charset[b] for b in address + checksum)


def toAddress(script):
    if script[0] == 0xAA and script[1] <= 0x76:
        return encodeAddress("kaspa", script[2 : (2 + script[1])], 0x08)
    if script[0] < 0x76:
        return encodeAddress("kaspa", script[1 : (1 + script[0])], 0x0)
    raise NotImplementedError(script.hex())


print(
    toAddress(
        b" \xcd\xcbS\xd7p\x8f\x03\xff\xa5\x8c\x98\x9a\xd4\x1e\xcd\x1b\x91\xe3\xf3\n4\xbb\xd9\x1fY:\xac\xdb^\x0b/\xd8\xac"
    )
)
