"""Tests for scripts/lib/decisions.py. Pure, no network, no external files
(schema loading is exercised separately via load_schema against the real
docs/schemas/ files)."""

from lib.decisions import load_schema, parse_and_validate, validate


SATURDAY_SCHEMA = {
    "type": "object",
    "required": ["claims", "drops", "note_reply"],
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["add", "drop", "bid"],
                "properties": {
                    "add": {"type": "string"},
                    "drop": {"type": ["string", "null"]},
                    "bid": {"type": "integer", "minimum": 0},
                },
            },
        },
        "drops": {"type": "array", "items": {"type": "string"}},
        "note_reply": {"type": "string"},
    },
}


def valid_decision():
    return {
        "claims": [{"add": "p_wr9", "drop": "p_wr3", "bid": 12}],
        "drops": [],
        "note_reply": "Fine, I'll bench him. Happy now?",
    }


def test_valid_decision_in_prose_and_fence_parses_and_validates_clean():
    raw = (
        "Sure, here's my Saturday plan for this week:\n\n"
        "```json\n"
        + __import__("json").dumps(valid_decision())
        + "\n```\n\n"
        "Let me know if the bid is too low."
    )
    obj, errors = parse_and_validate(raw, SATURDAY_SCHEMA)
    assert errors == []
    assert obj == valid_decision()


def test_missing_bid_field_returns_helpful_specific_error():
    decision = valid_decision()
    del decision["claims"][0]["bid"]
    raw = "```json\n" + __import__("json").dumps(decision) + "\n```"

    obj, errors = parse_and_validate(raw, SATURDAY_SCHEMA)

    assert obj is None
    assert len(errors) == 1
    assert "bid" in errors[0]
    assert "missing required field" in errors[0]
    # names the exact location, not just "somewhere"
    assert "claims[0]" in errors[0]


def test_braces_inside_string_value_do_not_break_extraction():
    decision = valid_decision()
    decision["note_reply"] = "My analytics say {efficiency: high} this week."
    raw = "Here you go:\n" + __import__("json").dumps(decision) + "\nthanks"

    obj, errors = parse_and_validate(raw, SATURDAY_SCHEMA)

    assert errors == []
    assert obj["note_reply"] == "My analytics say {efficiency: high} this week."


def test_garbage_with_no_json_returns_none_and_helpful_error():
    obj, errors = parse_and_validate(
        "I refuse to output JSON today, deal with it.", SATURDAY_SCHEMA
    )
    assert obj is None
    assert len(errors) == 1
    assert "{" in errors[0] or "JSON" in errors[0]


def test_wrong_type_field_is_flagged():
    decision = valid_decision()
    decision["claims"][0]["bid"] = "5"  # should be an int, not a string
    raw = "```json\n" + __import__("json").dumps(decision) + "\n```"

    obj, errors = parse_and_validate(raw, SATURDAY_SCHEMA)

    assert obj is None
    assert len(errors) == 1
    assert "bid" in errors[0]
    assert "claims[0]" in errors[0]
    assert "integer" in errors[0]


def test_extraction_skips_a_leading_non_json_brace():
    # A stray '{' in prose before the real payload (e.g. a smiley or a
    # markdown artifact) shouldn't derail extraction of the real object.
    raw = "note: {see attached} then:\n" + __import__("json").dumps(valid_decision())
    obj, errors = parse_and_validate(raw, SATURDAY_SCHEMA)
    assert errors == []
    assert obj == valid_decision()


def test_multiple_claims_missing_different_fields_each_reported():
    decision = {
        "claims": [{"add": "p1", "drop": None, "bid": 5}, {"add": "p2"}],
        "drops": [],
        "note_reply": "ok",
    }
    errors = validate(decision, SATURDAY_SCHEMA)
    assert any("claims[1]" in e and "drop" in e for e in errors)
    assert any("claims[1]" in e and "bid" in e for e in errors)


def test_real_saturday_decision_schema_file_loads_and_validates():
    schema = load_schema("saturday-decision")
    obj, errors = parse_and_validate(
        "```json\n" + __import__("json").dumps(valid_decision()) + "\n```",
        schema,
    )
    assert errors == []
    assert obj == valid_decision()


def test_real_sunday_lineup_schema_file_loads_and_validates():
    schema = load_schema("sunday-lineup.json")
    lineup = {
        "starters": {
            "QB": "p_qb1",
            "RB1": "p_rb1",
            "RB2": "p_rb2",
            "WR1": "p_wr1",
            "WR2": "p_wr2",
            "TE": "p_te1",
            "FLEX": "p_rb3",
            "K": "p_k1",
            "DEF": "p_def1",
        },
        "justification": "Studs stay in, obviously.",
    }
    obj, errors = parse_and_validate(
        "Here's the lineup: " + __import__("json").dumps(lineup), schema
    )
    assert errors == []
    assert obj == lineup


def test_real_trade_offer_and_response_schemas_validate():
    offer_schema = load_schema("trade-offer")
    offer = {"to_team": "warriors", "out": ["p1"], "in": ["p2"], "message": "fair?"}
    assert validate(offer, offer_schema) == []

    response_schema = load_schema("trade-response")
    response = {"response": "counter", "counter": {"to_team": "opp", "out": ["p2"], "in": ["p3"]}}
    assert validate(response, response_schema) == []

    bad_response = {"response": "maybe"}
    errors = validate(bad_response, response_schema)
    assert any("response" in e for e in errors)


def test_real_transaction_entry_schema_validates():
    schema = load_schema("transaction-entry")
    entry = {
        "timestamp": "2026-09-05T12:00:00Z",
        "team": "warriors",
        "action": "waiver_claim",
        "players": ["p_wr9", "p_wr3"],
        "bid": 12,
        "reasoning": "Need WR depth after the bye.",
        "status": "applied",
    }
    assert validate(entry, schema) == []

    del entry["bid"]
    errors = validate(entry, schema)
    assert any("bid" in e for e in errors)
