"""Reject recognized credentials without rewriting frozen observation bytes.

This validates structured credential names and URL captures, not arbitrary prose
or unknown credential formats. Rejections never include captured content.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from urllib.parse import parse_qsl, unquote, urlsplit

_SECRET_NAMES = frozenset(
    {
        "apikey",
        "lunaapikey",
        "openaiapikey",
        "exaapikey",
        "openalexapikey",
        "serpsearchapikey",
        "pubmedapikey",
        "mimoapikey",
        "firecrawlapikey",
        "xapikey",
        "authorization",
        "proxyauthorization",
        "password",
        "passwd",
        "accesstoken",
        "refreshtoken",
        "authtoken",
        "xauthtoken",
        "bearertoken",
        "token",
        "idtoken",
        "apitoken",
        "xapitoken",
        "clientsecret",
        "secret",
        "secretkey",
        "privatekey",
        "cookie",
        "setcookie",
        "awsaccesskeyid",
        "awssecretaccesskey",
        "sessiontoken",
        "xamzcredential",
        "xamzsignature",
        "xamzsecuritytoken",
        "xgoogcredential",
        "xgoogsignature",
    }
)
_QUERY_SECRET_NAMES = _SECRET_NAMES | {"key", "token", "auth", "signature"}
_PAIR_CONTAINERS = frozenset(
    {
        "headers",
        "requestheaders",
        "responseheaders",
        "httpheaders",
        "params",
        "parameters",
        "query",
        "queryparams",
        "queryparameters",
    }
)
_URL = re.compile(r"(?:[a-z][a-z0-9+.-]*://|(?<![\w:])//)[^\s<>\"']+", re.IGNORECASE)
_CREDENTIAL_HEADER = re.compile(
    r"^\s*(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-auth-token)\s*:",
    re.IGNORECASE | re.MULTILINE,
)


def _decoded(value: str) -> str:
    # Nested URL captures can percent-encode both URLs and their parameter names.
    while (decoded := unquote(value)) != value:
        value = decoded
    return value


def _name(value: str) -> str:
    return re.sub(r"[-_\s]", "", _decoded(value).casefold())


def _url_variants(value: str) -> Iterator[str]:
    # Check the original first: decoding %23 or %26 changes URL delimiters.
    yield value
    while (decoded := unquote(value)) != value:
        value = decoded
        yield value


def _reject() -> None:
    raise ValueError("observation artifact contains credential content")


def validate_observation_url(value: str) -> None:
    """Validate URL-bearing strings, including embedded or encoded URL captures."""
    pending = [value]
    checked: set[str] = set()
    while pending:
        captured = pending.pop()
        if captured in checked:
            continue
        checked.add(captured)
        for variant in _url_variants(captured):
            for match in _URL.finditer(variant):
                try:
                    url = urlsplit(match.group())
                except ValueError:
                    raise ValueError(
                        "observation artifact contains an invalid URL capture"
                    ) from None
                if "@" in url.netloc:
                    _reject()
                for key, item in parse_qsl(url.query, keep_blank_values=True):
                    if _name(key) in _QUERY_SECRET_NAMES:
                        _reject()
                    if _URL.search(_decoded(item)):
                        pending.append(item)


def _inspect(value: object, *, pairs: bool = False) -> None:
    if isinstance(value, dict):
        names = {_name(str(key)): item for key, item in value.items()}
        # HAR-style headers/parameters also use {name: ..., value: ...} entries.
        if "value" in names:
            for key in ("name", "key"):
                name = names.get(key)
                secret_names = _QUERY_SECRET_NAMES if pairs else _SECRET_NAMES
                if isinstance(name, str) and _name(name) in secret_names:
                    _reject()
        for key, item in value.items():
            name = _name(str(key))
            if name in _SECRET_NAMES or (pairs and name in _QUERY_SECRET_NAMES):
                _reject()
            _inspect(item, pairs=name in _PAIR_CONTAINERS)
    elif isinstance(value, list):
        if pairs and len(value) == 2 and isinstance(value[0], str):
            if _name(value[0]) in _QUERY_SECRET_NAMES:
                _reject()
        for item in value:
            _inspect(item, pairs=pairs)
    elif isinstance(value, str):
        validate_observation_url(value)
        if _CREDENTIAL_HEADER.search(value):
            _reject()


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    # Validate even duplicate JSON members that an ordinary decoder discards.
    for key, item in pairs:
        _inspect({key: item})
    value = dict(pairs)
    if len(value) != len(pairs):
        raise ValueError("observation artifact contains ambiguous structured content")
    return value


def validate_artifact_content(payload: bytes, media_type: str) -> None:
    """Reject unsafe JSON/text artifacts before their exact bytes are persisted."""
    kind = media_type.split(";", 1)[0].strip().casefold()
    declared_json = kind == "application/json" or kind.endswith("+json")
    # Decode recognizable JSON regardless of its declared media or byte encoding.
    # Prose and binary source snapshots fall through when they are not JSON.
    try:
        value = json.loads(payload, object_pairs_hook=_json_object)
        _inspect(value)
    except (UnicodeError, json.JSONDecodeError):
        if declared_json:
            raise ValueError("observation artifact contains invalid structured content") from None
    except RecursionError:
        raise ValueError("observation artifact contains invalid structured content") from None
    else:
        return
    if kind.startswith("text/") or kind in {
        "application/xml",
        "application/xhtml+xml",
        "application/x-www-form-urlencoded",
    }:
        try:
            text = payload.decode("utf-8")
        except UnicodeError:
            raise ValueError("observation artifact contains invalid textual content") from None
        validate_observation_url(text)
        if _CREDENTIAL_HEADER.search(text):
            _reject()
        if kind == "application/x-www-form-urlencoded":
            for key, _ in parse_qsl(text, keep_blank_values=True):
                if _name(key) in _QUERY_SECRET_NAMES:
                    _reject()
