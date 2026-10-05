from app.ai.guardrails import check_obj, check_text, numbers_in


def test_flags_invented_numbers_and_allows_known():
    allowed = numbers_in({"cmp": 1240.0, "stop": 1185.0, "rsi": 63.2, "rev_growth": 0.184})
    _, flags = check_text("Entry near ₹1,240 with stop ₹1,185; RSI 63.2; revenue grew 18.4%", allowed)
    assert flags == []
    _, flags = check_text("Target ₹1,999 looks likely", allowed)
    assert any("1,999" in f for f in flags)


def test_certainty_language_neutralised():
    text, flags = check_text("This trade is guaranteed and risk-free", set())
    assert "guarantee" not in text.lower() and "risk-free" not in text.lower()
    assert len(flags) >= 2


def test_check_obj_nested():
    out, flags = check_obj({"a": ["Price 1240"], "b": {"c": "PE 99.9"}}, {1240.0})
    assert out["a"][0] == "Price 1240" and any("99.9" in f for f in flags)
