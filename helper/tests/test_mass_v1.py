from ..mass_calculation_compute import calc_compute_mass
from ..mass_calculation_storage import calc_storage_mass, utxo_plurality

SPK = "11" * 34


def test_v1_covenant_mass():
    tx = {
        "version": 1,
        "subnetworkId": "00" * 20,
        "payload": "abcd",
        "inputs": [{"signatureScript": "41" * 66, "sequence": 0, "sigOpCount": 0, "computeBudget": 10}] * 2,
        "outputs": [
            {
                "amount": 5000_0000,
                "scriptPublicKey": {"version": 0, "scriptPublicKey": SPK},
                "covenant": {"authorizingInput": 1, "covenantId": "cc" * 32},
            },
            {"amount": 3_4000_0000, "scriptPublicKey": {"version": 0, "scriptPublicKey": SPK}, "covenant": None},
        ],
    }
    inputs = [(utxo_plurality(SPK, False), 3_0000_0000), (utxo_plurality(SPK, True), 1_0000_0000)]
    outputs = [(utxo_plurality(SPK, True), 5000_0000), (utxo_plurality(SPK, False), 3_4000_0000)]
    assert calc_compute_mass(tx) == 3194
    assert calc_storage_mass(inputs, outputs) == 60441
