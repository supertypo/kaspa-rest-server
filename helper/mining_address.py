# encoding: utf-8


def get_miner_payload_from_block(block: dict):
    for tx in block.get("transactions", []):
        if tx["subnetworkId"] == "0100000000000000000000000000000000000000":
            return tx["payload"]

    raise LookupError("Could not find mining payload.")


def retrieve_mining_info_from_payload(payload: str):
    payload  # b9b5220500000000d7ab55270200000000002220cdcb53d7708f03ffa58c989ad41ecd1b91e3f30a34bbd91f593aacdb5e0b2fd8ac302e31342e312f322f302f637878782f

    get_miner_payload_from_block()

    pass
