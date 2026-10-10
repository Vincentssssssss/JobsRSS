from app.api.routes.jobs import _parse_llm_verdicts


def test_parse_llm_verdicts_supports_multiple_values():
    assert _parse_llm_verdicts("strong_fit,possible_fit") == [
        "strong_fit",
        "possible_fit",
    ]


def test_parse_llm_verdicts_deduplicates_and_normalizes():
    assert _parse_llm_verdicts(" Possible_Fit , strong_fit ,possible_fit ") == [
        "possible_fit",
        "strong_fit",
    ]


def test_parse_llm_verdicts_ignores_invalid_values():
    assert _parse_llm_verdicts("foo,bar") == []
    assert _parse_llm_verdicts(None) == []
