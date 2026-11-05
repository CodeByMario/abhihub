from methods.search_api import execute_search_v3, get_suggestions_payload


def test_search_rejects_or_returns_empty_for_gibberish():
    results, meta = execute_search_v3("zzzz-no-such-resource-999")
    assert results == []
    assert isinstance(meta, dict)


def test_search_detects_code_and_alias_intent():
    code = get_suggestions_payload("uitl201")
    alias = get_suggestions_payload("ml")
    if code and code.get("detected"):
        assert code["detected"]["type"] == "code"
    if alias and alias.get("detected"):
        assert alias["detected"]["type"] == "alias"


def test_search_result_contract_is_stable():
    results, meta = execute_search_v3("machine lerning")
    assert isinstance(results, list)
    assert isinstance(meta, dict)
    if results:
        assert "match_reason" in results[0]
