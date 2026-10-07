"""Deterministic provider syntax; concepts are data, never executable operators."""

from __future__ import annotations

import unicodedata
from urllib.parse import urlencode

from researchassistant.contracts.discovery_v2 import (
    SearchMode,
    V2CompiledQueryAction,
    V2ConceptualQuery,
    V2DiscoveryPolicy,
    V2SanitizedParameter,
    discovery_hash,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.research.discovery_capabilities import get_query_capabilities

QUERY_COMPILER_ID = "source-query-compiler-v2"
MAX_QUERY_BYTES = 3000
MAX_ENCODED_PARAMETERS = 7500


def _term(value: str) -> str:
    if any(unicodedata.category(char).startswith("C") for char in value):
        raise ValueError("query concepts cannot contain control or formatting characters")
    if any(char in value for char in ('"', "\\", "[", "]", "{", "}", "<", ">", "|", ":", "(", ")")):
        raise ValueError("query concepts cannot contain executable syntax or reserved characters")
    normalized = " ".join(unicodedata.normalize("NFC", value).split())
    if not normalized or len(normalized) > 180 or len(normalized.split()) > 14:
        raise ValueError("query concept must be a concise bounded phrase")
    if normalized.upper() in {"AND", "OR", "NOT", "ANDNOT"}:
        raise ValueError("a Boolean operator cannot be a concept")
    return normalized


def _phrase(value: str, field: str = "") -> str:
    term = _term(value)
    return f'{field}"{term}"'


def conceptual_signature(query: V2ConceptualQuery, mode: SearchMode) -> tuple[object, ...]:
    """Compare executable concepts/mode, ignoring diagnostic and unused metadata."""
    groups = [
        tuple(sorted(_term(term).casefold() for term in (group.concept, *group.synonyms)))
        for group in query.required_concepts
    ]
    if query.purpose == "methods" and query.methods:
        groups.append(tuple(sorted(_term(x).casefold() for x in query.methods)))
    elif query.purpose == "outcomes" and query.outcomes:
        groups.append(tuple(sorted(_term(x).casefold() for x in query.outcomes)))
    elif query.purpose == "gap" and (query.methods or query.outcomes):
        groups.append(
            tuple(sorted({_term(x).casefold() for x in (*query.methods, *query.outcomes)}))
        )
    return (mode, tuple(sorted(groups)))


def compile_query(
    conceptual: V2ConceptualQuery,
    *,
    mode: SearchMode | None = None,
    requested_depth: int = 5,
    policy: V2DiscoveryPolicy | None = None,
) -> V2CompiledQueryAction:
    """Compile one bounded single metadata page, with no implicit mode fallback."""
    capabilities = get_query_capabilities(conceptual.provider)
    resolved_mode: SearchMode = (
        mode
        if mode is not None
        else "provider_default"
        if conceptual.provider is DiscoveryProvider.EXA
        else "lexical"
    )
    capabilities.require_search(resolved_mode, executable=True)
    resolved_policy = policy or V2DiscoveryPolicy()
    if isinstance(requested_depth, bool) or not 1 <= requested_depth <= 50:
        raise ValueError("requested query depth must be in 1..50")
    depth = min(requested_depth, resolved_policy.metadata_depth, capabilities.max_metadata_per_page)
    if conceptual.provider is DiscoveryProvider.OPENALEX and resolved_mode == "semantic":
        depth = min(depth, 50)
    groups: list[tuple[str, ...]] = []
    for group in conceptual.required_concepts:
        terms = tuple(_term(x) for x in (group.concept, *group.synonyms))
        if len(terms) > 4:
            raise ValueError("query compiler permits at most three justified aliases per concept")
        if len(terms[0]) <= 4 and terms[0].isupper() and len(terms) == 1:
            raise ValueError("ambiguous acronym-only concept requires a full phrase")
        if len({term.casefold() for term in terms}) != len(terms):
            raise ValueError("normalized aliases must be unique")
        groups.append(terms)
    methods = tuple(_term(x) for x in conceptual.methods)
    outcomes = tuple(_term(x) for x in conceptual.outcomes)
    context_groups: list[tuple[str, tuple[str, ...]]] = []
    # Optional context narrows explicit methods/outcomes and gap lanes; broad lanes retain recall.
    if conceptual.purpose == "methods" and methods:
        context_groups.append(("method", methods))
        groups.append(methods)
    elif conceptual.purpose == "outcomes" and outcomes:
        context_groups.append(("outcome", outcomes))
        groups.append(outcomes)
    elif conceptual.purpose == "gap" and (methods or outcomes):
        alternatives = tuple(dict.fromkeys((*methods, *outcomes)))
        if methods and outcomes:
            label = "method or outcome"
        elif methods:
            label = "method"
        else:
            label = "outcome"
        context_groups.append((label, alternatives))
        groups.append(alternatives)
    provider = conceptual.provider
    parameters: dict[str, str | int | bool]
    if provider is DiscoveryProvider.EXA or resolved_mode == "semantic":
        parts = [
            f"{terms[0]}" + (f" (also called {', '.join(terms[1:])})" if len(terms) > 1 else "")
            for terms in groups
        ]
        required_count = len(conceptual.required_concepts)
        optional_parts = [
            f"{label} evidence involving {' or '.join(terms)}" for label, terms in context_groups
        ]
        parts = parts[:required_count] + optional_parts
        text = "; ".join(parts)
        if provider is DiscoveryProvider.EXA:
            parameters = {"query": text, "type": "auto", "numResults": depth}
        else:
            parameters = {"search.semantic": text, "per_page": depth}
    elif provider is DiscoveryProvider.ARXIV:
        text = " AND ".join(
            "("
            + " OR ".join(_phrase(term, field) for term in terms for field in ("ti:", "abs:"))
            + ")"
            for terms in groups
        )
        parameters = {
            "search_query": text,
            "start": 0,
            "max_results": depth,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    elif provider is DiscoveryProvider.PUBMED:
        text = " AND ".join(
            "(" + " OR ".join(_phrase(term) + "[tiab]" for term in terms) + ")" for terms in groups
        )
        parameters = {"term": text, "db": "pubmed", "retmax": depth, "retmode": "json"}
    elif provider is DiscoveryProvider.OPENALEX:
        text = " AND ".join(
            "(" + " OR ".join(_phrase(term) for term in terms) + ")" for terms in groups
        )
        parameters = {"search": text, "per_page": depth}
    elif provider is DiscoveryProvider.SERPSEARCH:
        text = " ".join(
            "(" + " OR ".join(_phrase(term) for term in terms) + ")"
            if len(terms) > 1
            else _phrase(terms[0])
            for terms in groups
        )
        parameters = {"query": text, "page": 1, "exact_match": True}
    else:
        raise ValueError(f"unsupported query compiler provider: {provider}")
    if resolved_mode == "semantic" and len(text) > 2000:
        raise ValueError("semantic query exceeds documented input limit")
    encoded_limit = 3000 if provider is DiscoveryProvider.OPENALEX else MAX_ENCODED_PARAMETERS
    if (
        len(text.encode("utf-8")) > MAX_QUERY_BYTES
        or len(urlencode(parameters).encode("ascii")) > encoded_limit
    ):
        raise ValueError("compiled query or encoded parameter length exceeds request policy")
    identity = discovery_hash(
        (
            str(conceptual.artifact_id),
            resolved_mode,
            text,
            tuple(parameters.items()),
            requested_depth,
            resolved_policy.model_dump_json(),
        )
    )
    key = f"compiled/{identity}"
    payload = dict(
        run_id=conceptual.run_id,
        artifact_id=discovery_id(conceptual.run_id, "V2CompiledQueryAction", key),
        identity_key=key,
        conceptual_query=conceptual,
        query_text=text,
        parameters=tuple(V2SanitizedParameter(name=k, value=v) for k, v in parameters.items()),
        mode=resolved_mode,
        requested_depth=requested_depth,
        effective_depth=depth,
        compiler_identity=QUERY_COMPILER_ID,
        policy=resolved_policy,
        capabilities=capabilities,
    )
    # Hash exactly the canonical persisted action, before validated construction.
    provisional = V2CompiledQueryAction.model_construct(**payload, fingerprint="0" * 64)
    payload["fingerprint"] = discovery_hash(provisional.model_dump_without_fingerprint())
    return V2CompiledQueryAction(**payload)


def validate_compiled_action(action: V2CompiledQueryAction) -> None:
    """Reject forged/stale settings, parameters, syntax, or executable identities."""
    expected = compile_query(
        action.conceptual_query,
        mode=action.mode,
        requested_depth=action.requested_depth,
        policy=action.policy,
    )
    if action != expected:
        raise ValueError("compiled query differs from deterministic compiler output")
