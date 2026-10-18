from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from evaluations.observation_safety import validate_artifact_content, validate_observation_url
from evaluations.research_quality import DEFAULT_MANIFEST, evaluate

SYNTHETIC_CREDENTIAL = "SYNTHETIC_NOT_A_SECRET"


@pytest.mark.parametrize(
    "name",
    [
        "api_key",
        "API-Key",
        "apiKey",
        "Authorization",
        "proxy-authorization",
        "password",
        "access_token",
        "refresh_token",
        "client_secret",
        "Cookie",
        "set-cookie",
        "X-API-Key",
        "X-Auth-Token",
        "X-Amz-Security-Token",
        "private_key",
    ],
)
def test_nested_structured_secret_fields_are_rejected(name: str) -> None:
    payload = json.dumps({"acquisition": [{"metadata": {name: SYNTHETIC_CREDENTIAL}}]}).encode()
    with pytest.raises(ValueError, match="credential content") as caught:
        validate_artifact_content(payload, "application/json")
    assert SYNTHETIC_CREDENTIAL not in str(caught.value)
    assert name not in str(caught.value)


@pytest.mark.parametrize(
    "headers",
    [
        [["Authorization", SYNTHETIC_CREDENTIAL]],
        [{"name": "X-API-Key", "value": SYNTHETIC_CREDENTIAL}],
        [{"key": "Cookie", "value": SYNTHETIC_CREDENTIAL}],
        {"Proxy-Authorization": SYNTHETIC_CREDENTIAL},
    ],
)
def test_captured_header_formats_are_rejected(headers: object) -> None:
    payload = json.dumps({"response": {"headers": headers}}).encode()
    with pytest.raises(ValueError, match="credential content"):
        validate_artifact_content(payload, "application/json; charset=utf-8")


@pytest.mark.parametrize(
    "query",
    [
        {"api_key": SYNTHETIC_CREDENTIAL},
        [["token", SYNTHETIC_CREDENTIAL]],
        [{"name": "key", "value": SYNTHETIC_CREDENTIAL}],
    ],
)
def test_captured_query_parameter_formats_are_rejected(query: object) -> None:
    payload = json.dumps({"request": {"query_parameters": query}}).encode()
    with pytest.raises(ValueError, match="credential content"):
        validate_artifact_content(payload, "application/problem+json")


@pytest.mark.parametrize(
    "url",
    [
        f"https://api.openalex.org/works?api_key={SYNTHETIC_CREDENTIAL}",
        f"https://example.invalid/?q=work&API%5FKEY={SYNTHETIC_CREDENTIAL}",
        f"https://example.invalid/?%2561pi%255fkey={SYNTHETIC_CREDENTIAL}",
        f"https://example.invalid/?q=%23&api_key={SYNTHETIC_CREDENTIAL}",
        f"https://example.invalid/?X-Amz-Signature={SYNTHETIC_CREDENTIAL}",
        f"https://example.invalid/?X-Goog-Credential={SYNTHETIC_CREDENTIAL}",
        f"https://example.invalid/?access_token={SYNTHETIC_CREDENTIAL}",
        f"https://example.invalid/?key={SYNTHETIC_CREDENTIAL}",
        f"https://example.invalid/?token={SYNTHETIC_CREDENTIAL}",
        "https://example.invalid/?api_key=",
        f"https://user:{SYNTHETIC_CREDENTIAL}@example.invalid/work",
        "https://user@example.invalid/work",
        f"//user:{SYNTHETIC_CREDENTIAL}@example.invalid/work",
        f"ftp://user:{SYNTHETIC_CREDENTIAL}@example.invalid/work",
        f"https://example.invalid/?url=https%3A%2F%2Fupstream.invalid%2F%3Fapi_key%3D{SYNTHETIC_CREDENTIAL}",
    ],
)
def test_url_credentials_are_rejected(url: str) -> None:
    with pytest.raises(ValueError, match="credential content") as caught:
        validate_observation_url(url)
    assert SYNTHETIC_CREDENTIAL not in str(caught.value)
    assert "example.invalid" not in str(caught.value)
    with pytest.raises(ValueError, match="credential content"):
        validate_artifact_content(json.dumps({"source_url": url}).encode(), "application/json")


@pytest.mark.parametrize("media_type", ["text/plain", "text/html", "application/xml"])
def test_textual_url_captures_are_rejected(media_type: str) -> None:
    payload = (
        f'Captured <a href="https://example.invalid/?api_key={SYNTHETIC_CREDENTIAL}">work</a>'
    ).encode()
    with pytest.raises(ValueError, match="credential content"):
        validate_artifact_content(payload, media_type)


@pytest.mark.parametrize("name", ["Authorization", "Cookie", "X-Api-Key", "Set-Cookie"])
def test_textual_credential_headers_are_rejected(name: str) -> None:
    payload = f"HTTP/1.1 200 OK\n{name}: {SYNTHETIC_CREDENTIAL}\n\nbody".encode()
    with pytest.raises(ValueError, match="credential content"):
        validate_artifact_content(payload, "text/plain")


def test_form_encoded_credentials_are_rejected() -> None:
    payload = f"q=work&api%5Fkey={SYNTHETIC_CREDENTIAL}".encode()
    with pytest.raises(ValueError, match="credential content"):
        validate_artifact_content(payload, "application/x-www-form-urlencoded")


def test_duplicate_json_members_do_not_hide_credential_urls() -> None:
    payload = (
        '{"url":"https://example.invalid/?api_key='
        + SYNTHETIC_CREDENTIAL
        + '","url":"https://example.invalid/work"}'
    ).encode()
    with pytest.raises(ValueError, match="credential content"):
        validate_artifact_content(payload, "application/json")


def test_duplicate_header_names_fail_closed_before_decoding_discards_them() -> None:
    payload = (
        '{"headers":[{"name":"Authorization","name":"Accept","value":"'
        + SYNTHETIC_CREDENTIAL
        + '"}]}'
    ).encode()
    with pytest.raises(ValueError, match="ambiguous structured content") as caught:
        validate_artifact_content(payload, "application/json")
    assert SYNTHETIC_CREDENTIAL not in str(caught.value)


def test_json_embedded_http_capture_rejects_headers() -> None:
    payload = json.dumps(
        {"capture": f"GET /work HTTP/1.1\nAuthorization: {SYNTHETIC_CREDENTIAL}"}
    ).encode()
    with pytest.raises(ValueError, match="credential content"):
        validate_artifact_content(payload, "application/json")


@pytest.mark.parametrize("media_type", ["text/plain", "application/octet-stream"])
def test_structured_credentials_cannot_bypass_validation_using_media_type(media_type: str) -> None:
    payload = json.dumps({"stage": {"api_key": SYNTHETIC_CREDENTIAL}}).encode()
    with pytest.raises(ValueError, match="credential content"):
        validate_artifact_content(payload, media_type)


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16", "utf-32"])
@pytest.mark.parametrize("media_type", ["text/plain", "application/octet-stream"])
def test_encoded_json_credentials_cannot_bypass_media_sniffing(
    encoding: str, media_type: str
) -> None:
    payload = json.dumps(
        {"stage": {"url": f"https://example.invalid/?api_key={SYNTHETIC_CREDENTIAL}"}}
    ).encode(encoding)
    assert isinstance(json.loads(payload), dict)
    with pytest.raises(ValueError, match="credential content"):
        validate_artifact_content(payload, media_type)


def test_binary_source_snapshot_without_structured_content_is_preserved() -> None:
    payload = b"%PDF-1.4\n\xff\x00binary source bytes"
    validate_artifact_content(payload, "application/pdf")


@pytest.mark.parametrize("media_type", ["application/json", "application/octet-stream"])
@pytest.mark.parametrize(
    "role", ["raw_response", "snapshot", "stage", "request", "judgment", "reference"]
)
def test_evaluator_checks_structured_credentials_for_every_role_and_media(
    tmp_path: Path, role: str, media_type: str
) -> None:
    bundle = tmp_path / "fixture"
    shutil.copytree(DEFAULT_MANIFEST.parent / "fixture_bundle", bundle)
    manifest = bundle / "manifest.json"
    data = json.loads(manifest.read_bytes())
    payload = json.dumps({"synthetic_capture": {"api_key": SYNTHETIC_CREDENTIAL}}).encode()
    (bundle / "synthetic-capture.json").write_bytes(payload)
    data["observations"][0]["artifacts"].append(
        {
            "path": "synthetic-capture.json",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "media_type": media_type,
            "role": role,
        }
    )
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="credential content") as caught:
        evaluate(manifest, replay=True)
    assert SYNTHETIC_CREDENTIAL not in str(caught.value)


def test_plain_source_text_starting_with_a_bracket_is_preserved() -> None:
    validate_artifact_content(b"[1] Source bibliography and paragraph.", "text/plain")


@pytest.mark.parametrize(
    "value",
    [
        "A study discusses authorization, cookies, password and token terminology.",
        "https://example.invalid/work?q=authorization+password+token&cursor=next&page=1",
        "https://example.invalid/api_key/research#authorization",
        "https://example.invalid/users/person@example.invalid",
        "https://example.invalid/?monkey=study&keyword=api_key",
    ],
)
def test_arbitrary_words_and_noncredential_lineage_are_preserved(value: str) -> None:
    payload = json.dumps({"source_text": value, "total_tokens": 20, "token_count": 5}).encode()
    original = bytes(payload)
    validate_artifact_content(payload, "application/json")
    validate_artifact_content(value.encode(), "text/plain")
    assert payload == original


def test_nonsecret_headers_and_pairs_are_preserved() -> None:
    payload = json.dumps(
        {
            "headers": [["Accept", "application/json"], ["Content-Type", "text/plain"]],
            "query_parameters": [{"name": "q", "value": "authorization"}],
            "terms": ["authorization", "password"],
            "metadata": {"name": "key", "value": "publication identifier"},
        }
    ).encode()
    validate_artifact_content(payload, "application/json")


@pytest.mark.parametrize(
    ("payload", "media_type"),
    [
        (b'{"capture":"SYNTHETIC_NOT_A_SECRET",', "application/json"),
        (b"\xffSYNTHETIC_NOT_A_SECRET", "application/json"),
        (b"\xffSYNTHETIC_NOT_A_SECRET", "text/plain"),
    ],
)
def test_invalid_capture_errors_do_not_echo_content(payload: bytes, media_type: str) -> None:
    with pytest.raises(ValueError, match="invalid .* content") as caught:
        validate_artifact_content(payload, media_type)
    assert SYNTHETIC_CREDENTIAL not in str(caught.value)
    assert caught.value.__suppress_context__


def test_invalid_url_capture_errors_do_not_echo_content() -> None:
    with pytest.raises(ValueError, match="invalid URL capture") as caught:
        validate_observation_url(f"https://[SYNTHETIC_NOT_A_SECRET/?q={SYNTHETIC_CREDENTIAL}")
    assert SYNTHETIC_CREDENTIAL not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.parametrize(
    "name",
    [
        "LUNA_API_KEY",
        "OPENAI_API_KEY",
        "EXA_API_KEY",
        "OPENALEX_API_KEY",
        "SERPSEARCH_API_KEY",
        "PUBMED_API_KEY",
        "MIMO_API_KEY",
        "FIRECRAWL_API_KEY",
    ],
)
def test_supported_native_credential_field_names_are_not_captured(name: str) -> None:
    payload = json.dumps({name: SYNTHETIC_CREDENTIAL}).encode()
    with pytest.raises(ValueError, match="credential content"):
        validate_artifact_content(payload, "application/json")
