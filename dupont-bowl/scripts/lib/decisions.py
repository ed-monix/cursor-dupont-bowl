"""Parse and validate AI-agent decision JSON for DuPont Bowl (TASKS.md 2.4).

Agents reply in free-form prose that wraps a single JSON object -- often in a
```json fence, sometimes with commentary before and/or after. This module:

    1. extracts the first parseable JSON *object* from that raw text
       (`_extract_first_json_object`), tracking string literals so braces
       inside e.g. a `note_reply` string don't confuse the brace matcher;
    2. validates the parsed object against one of the JSON Schema documents
       in `docs/schemas/` using a small hand-rolled checker -- NOT the
       `jsonschema` package, which is outside this repo's allowed deps
       (`requests`, `flask`, `pytest` only; see TASKS.md header). The checker
       understands the subset of JSON Schema the docs/schemas/*.json files
       actually use: `type` (single or a list, e.g. `["string", "null"]`),
       `required`, `properties`, `items`, `additionalProperties` (as a
       sub-schema), and `enum` -- recursively, so nesting deeper than one
       level is still checked as long as it's expressed with those keywords.
       Anything fancier ($ref, allOf/oneOf, pattern, formats, ...) is simply
       not present in this repo's schemas and isn't supported.

Both stdlib only, no network.
"""

from __future__ import annotations

import json
import os

_SCHEMAS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
    "schemas",
)


def load_schema(name: str) -> dict:
    """Load docs/schemas/<name>.json. `name` may include or omit '.json'."""
    filename = name if name.endswith(".json") else f"{name}.json"
    path = os.path.join(_SCHEMAS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# JSON extraction: find the first balanced-brace region that parses as a
# JSON object, scanning past any earlier '{' that turns out not to work.
# ---------------------------------------------------------------------------

def _find_matching_brace(text: str, start: int):
    """Given text[start] == '{', return the index of its matching '}',
    correctly skipping over braces inside string literals (honoring
    backslash escapes). Returns None if the braces never balance."""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def _extract_first_json_object(raw_text: str):
    """Find the first '{' in raw_text, walk forward to its balanced '}',
    and try to json.loads() that slice. If it isn't valid JSON (or isn't a
    JSON object), advance to the next '{' and retry, so stray/prose braces
    before the real payload don't sink the whole extraction.

    Returns (obj: dict, None) on success, or (None, error_message: str).
    """
    if not raw_text:
        return None, "agent reply was empty -- expected a JSON object"

    search_from = 0
    tried_any = False
    while True:
        start = raw_text.find("{", search_from)
        if start == -1:
            break
        tried_any = True
        end = _find_matching_brace(raw_text, start)
        if end is None:
            # Braces never balance from here on; no later '{' will fare
            # better on this same unterminated run, but keep it simple and
            # correct: stop looking.
            break
        candidate = raw_text[start : end + 1]
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            search_from = start + 1
            continue
        if isinstance(parsed, dict):
            return parsed, None
        search_from = start + 1

    if not tried_any:
        return None, "no '{' found in agent reply -- expected a JSON object"
    return None, (
        "found '{' in agent reply but no balanced region parsed as a JSON "
        "object -- check for truncated output or mismatched braces"
    )


# ---------------------------------------------------------------------------
# Hand-rolled schema validation (stdlib only -- no jsonschema dependency).
# ---------------------------------------------------------------------------

_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
    "null": lambda v: v is None,
}


def _json_type_name(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _type_matches(value, type_spec) -> bool:
    types = type_spec if isinstance(type_spec, list) else [type_spec]
    return any(_TYPE_CHECKS.get(t, lambda v: True)(value) for t in types)


def _validate(value, schema: dict, path: str) -> list[str]:
    """Recursively check `value` against `schema`, returning human-readable
    error strings (empty list if it's clean). `path` is a JSON-path-ish
    breadcrumb ("$.claims[0].bid") used to make errors specific."""
    errors: list[str] = []

    if "type" in schema and not _type_matches(value, schema["type"]):
        errors.append(
            f"{path}: expected type {schema['type']!r}, got "
            f"{_json_type_name(value)} ({value!r})"
        )
        # Base type is wrong; checking required/properties against the
        # wrong shape would just produce noise on top of this error.
        return errors

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} not one of {schema['enum']!r}")

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required field '{key}'")

        properties = schema.get("properties", {})
        for key, subschema in properties.items():
            if key in value:
                errors.extend(_validate(value[key], subschema, f"{path}.{key}"))

        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            for key, subvalue in value.items():
                if key not in properties:
                    errors.extend(_validate(subvalue, additional, f"{path}.{key}"))

    elif isinstance(value, list):
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for i, item in enumerate(value):
                errors.extend(_validate(item, items_schema, f"{path}[{i}]"))

    return errors


def validate(obj, schema: dict) -> list[str]:
    """Validate `obj` against a JSON-Schema-style `schema` dict using the
    hand-rolled checker above. Returns a list of human-readable error
    strings (empty if valid)."""
    return _validate(obj, schema, "$")


def parse_and_validate(raw_text: str, schema: dict):
    """Extract the first JSON object from an agent's free-form reply and
    validate it against `schema`.

    Returns (obj, errors):
        - (dict, [])        on success.
        - (None, [str, ...]) if no JSON object could be extracted, or if it
          extracted but failed validation. Every error string is written to
          be pasted directly into a retry prompt (names the offending field
          and, for type errors, what was expected vs. found).
    """
    obj, extract_error = _extract_first_json_object(raw_text)
    if obj is None:
        return None, [extract_error]

    errors = validate(obj, schema)
    if errors:
        return None, errors

    return obj, []
