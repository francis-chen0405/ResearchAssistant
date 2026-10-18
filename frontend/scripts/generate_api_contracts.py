"""Generate renderer wire types from live backend schemas, without starting I/O.

OpenAPI owns route response types. Validation schemas supplement wrap serializers
with opaque serialization schemas, using isolated references for their definitions.
No routes, backend models, or dependency locks are modified by this generator.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from researchassistant.api.application import create_app
from researchassistant.api.live_contracts import LiveRunSnapshot, ResearchTrailItem
from researchassistant.api.live_service import LiveResearchController
from researchassistant.api.runtime import ApiRuntime
from researchassistant.api.service_manager import WigoloServiceManager
from researchassistant.contracts.discovery_v2 import V2PreviewResult
from researchassistant.contracts.models import V2FinalResearchOutput

OUTPUT = Path(__file__).resolve().parents[1] / "lib/generated/api-contracts.ts"


def backend_contract() -> dict[str, Any]:
    runtime = ApiRuntime(
        controller=LiveResearchController(environment={}),
        services=WigoloServiceManager(base_environment={}),
        environment={},
    )
    app = create_app(runtime, load_keychain_on_start=False)
    document = app.openapi()
    schemas = document["components"]["schemas"]

    # Wrap serializers can advertise an unstructured dict in serialization
    # OpenAPI. Their existing validation models describe the historical fields.
    # Scope every supplemental definition to its owning root. Short names alone
    # cannot identify models: HTTP and research both have a ValidationError.
    def include_model(model: type[BaseModel]) -> None:
        schema = model.model_json_schema(
            mode="validation", ref_template="#/components/schemas/{model}"
        )
        definitions = schema.pop("$defs", {})
        names = {
            name: f"Supplemental__{model.__module__}.{model.__qualname__}__{name}"
            for name in definitions
        }

        def rewrite(value: Any, *, require_owned: bool = True) -> Any:
            if isinstance(value, list):
                return [rewrite(item, require_owned=require_owned) for item in value]
            if isinstance(value, dict):
                result = {
                    key: rewrite(item, require_owned=require_owned) for key, item in value.items()
                }
                reference = result.get("$ref")
                if isinstance(reference, str):
                    name = reference.rsplit("/", 1)[-1]
                    if name not in names:
                        if require_owned:
                            raise ValueError(f"Unowned supplemental schema reference: {reference}")
                    else:
                        result["$ref"] = f"#/components/schemas/{names[name]}"
                return result
            return value

        def opaque(current: dict[str, Any]) -> bool:
            return not current or (
                current.get("type") == "object" and not current.get("properties")
            )

        for name, definition in definitions.items():
            scoped = names[name]
            rewritten = rewrite(definition)
            if scoped in schemas and schemas[scoped] != rewritten:
                raise ValueError(f"Conflicting supplemental schema identifier: {scoped}")
            schemas[scoped] = rewritten
            existing = schemas.get(name, {})
            if opaque(existing):
                schemas[name] = {"$ref": f"#/components/schemas/{scoped}"}
            elif existing.get("properties") and set(existing["properties"]) == set(
                definition.get("properties", {})
            ):
                # Keep structured serialization fields (notably Decimal), but
                # bind their nested refs to this model's own definitions. A
                # different short-name shape, such as HTTP ValidationError,
                # retains its independent OpenAPI definition.
                schemas[name] = rewrite(existing, require_owned=False)
        existing = schemas.get(model.__name__, {})
        if opaque(existing) or "$ref" in existing:
            schemas[model.__name__] = rewrite(schema)

    for model in (V2FinalResearchOutput, ResearchTrailItem, V2PreviewResult, LiveRunSnapshot):
        include_model(model)
    return document


def ts_type(schema: dict[str, Any]) -> str:
    """Translate only the JSON Schema constructs present in backend contracts.

    Unsupported structural constructs fail rather than quietly weakening a type.
    Numeric/string bounds remain server validation, not TypeScript guarantees.
    """
    if "$ref" in schema:
        return f"ApiSchemas[{json.dumps(schema['$ref'].rsplit('/', 1)[1])}]"
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(item) for item in schema["enum"])
    for keyword, separator in (("anyOf", " | "), ("oneOf", " | "), ("allOf", " & ")):
        if keyword in schema:
            return "(" + separator.join(ts_type(item) for item in schema[keyword]) + ")"
    if any(key in schema for key in ("not", "if", "then", "else", "patternProperties")):
        raise ValueError(f"Unsupported structural schema: {schema}")
    kind = schema.get("type")
    if isinstance(kind, list):
        return "(" + " | ".join(ts_type({**schema, "type": item}) for item in kind) + ")"
    if kind in ("number", "integer"):
        return "number"
    if kind in ("string", "boolean", "null"):
        return kind
    if kind == "array":
        if "prefixItems" in schema:
            return "[" + ", ".join(ts_type(item) for item in schema["prefixItems"]) + "]"
        return f"Array<{ts_type(schema.get('items', {}))}>"
    if kind == "object" or "properties" in schema:
        required = set(schema.get("required", []))
        fields = [
            f"{json.dumps(name)}{'' if name in required else '?'}: {ts_type(prop)};"
            for name, prop in schema.get("properties", {}).items()
        ]
        additional = schema.get("additionalProperties", True)
        record = None
        if additional is not False:
            value_type = ts_type(additional) if isinstance(additional, dict) else "unknown"
            record = f"Record<string, {value_type}>"
        if not fields:
            return record or "Record<string, never>"
        obj = "{\n    " + "\n    ".join(fields) + "\n  }"
        return f"({obj} & {record})" if record else obj
    if kind is None:
        # OpenAPI's `object` Python values intentionally have an empty schema.
        return "unknown"
    raise ValueError(f"Unsupported schema type: {kind}")


def render_contract(document: dict[str, Any]) -> str:
    lines = [
        "// Generated by frontend/scripts/generate_api_contracts.py. Do not edit.",
        "// Defaults/nullable fields follow OpenAPI. Bounds are validated by the backend.",
        "export type ApiSchemas = {",
    ]
    for name, schema in sorted(document["components"]["schemas"].items()):
        lines.append(f"  {json.dumps(name)}: {ts_type(schema)};")
    lines.extend(["};", "", "export type ApiResponses = {"])
    for path, methods in sorted(document["paths"].items()):
        for method, operation in sorted(methods.items()):
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            schema = (
                operation["responses"]["200"]
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
            )
            lines.append(f"  {json.dumps(method.upper() + ' ' + path)}: {ts_type(schema)};")
    lines.extend(["};", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Fail if committed renderer types differ"
    )
    args = parser.parse_args()
    generated = render_contract(backend_contract())
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != generated:
            parser.exit(
                1,
                "Renderer API types are stale. "
                "Run python frontend/scripts/generate_api_contracts.py.\n",
            )
        print("Renderer API contracts match live backend schemas.")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(generated)
        print(f"Generated {OUTPUT}")


if __name__ == "__main__":
    main()
