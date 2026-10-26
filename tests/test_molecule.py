import pytest

from satori.__main__ import EXAMPLES
from satori.molecule import canonical_smiles, describe, lipinski, parse_smiles


def test_aspirin_properties():
    props = describe(parse_smiles(EXAMPLES["aspirin"]))
    assert props["molecular_weight"] == pytest.approx(180.16, abs=0.01)
    assert props["h_bond_donors"] == 1
    assert props["rings"] == 1
    assert 0 < props["qed"] < 1


def test_canonical_smiles_ignores_spelling():
    a = canonical_smiles(parse_smiles("CC(=O)O"))
    b = canonical_smiles(parse_smiles("OC(C)=O"))
    assert a == b


@pytest.mark.parametrize("name", ["aspirin", "caffeine", "ibuprofen"])
def test_common_drugs_pass_lipinski(name):
    passes, _ = lipinski(describe(parse_smiles(EXAMPLES[name])))
    assert passes


def test_cyclosporine_fails_lipinski():
    passes, violations = lipinski(describe(parse_smiles(EXAMPLES["cyclosporine"])))
    assert not passes
    assert any(v.startswith("molecular_weight") for v in violations)


@pytest.mark.parametrize("bad", ["not-a-molecule", "", "C1CC"])
def test_invalid_smiles_raises(bad):
    with pytest.raises(ValueError):
        parse_smiles(bad)
