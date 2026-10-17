from conecta_agent.verifier import Evidence, amounts_in


def evidence(*texts):
    e = Evidence()
    for t in texts:
        e.add_text(t)
    return e


def test_traceable_amount_passes():
    assert evidence('{"maxCredit":49.50}').unsupported("Te devolvemos $49.50.") == []


def test_invented_amount_is_flagged():
    assert evidence('{"maxCredit":49.50}').unsupported("Te devolvemos $50.00.") == ["50.00"]


def test_comma_decimals_are_normalized():
    assert amounts_in("son USD 16,47") == amounts_in("son $16.47")


def test_wrong_currency_is_flagged():
    assert "non-USD currency" in evidence('{"total":99.00}').unsupported("Tu factura es de 99,00 €")


def test_plain_counts_are_not_money():
    assert evidence("{}").unsupported("Te llamamos en 2 horas, tienes 300 Mbps") == []
