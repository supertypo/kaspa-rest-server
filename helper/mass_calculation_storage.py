# encoding: utf-8

# Storage mass constant
C = 10**12


def utxo_plurality(script_public_key: str, has_covenant: bool) -> int:
    return (63 + len(script_public_key) // 2 + (32 if has_covenant else 0) + 99) // 100


def calc_storage_mass(inputs, outputs):
    """
    Calculates the storage mass for the provided (plurality, amount) input/output collections
    """
    ins_plurality = sum(p for p, _ in inputs)
    outs_plurality = sum(p for p, _ in outputs)
    P = sum(C * p * p // v for p, v in outputs)
    if outs_plurality == 1 or (len(inputs) <= 2 and (ins_plurality <= 1 or outs_plurality == ins_plurality == 2)):
        N = sum(C * p * p // v for p, v in inputs)
    else:
        N = ins_plurality * (C // max(sum(v for _, v in inputs) // ins_plurality, 1))
    return max(P - N, 0)
