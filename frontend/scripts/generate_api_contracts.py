"""Generate renderer wire types from live backend schemas, without starting I/O.

OpenAPI owns route response types. The model-options route has a freeform HTTP
schema; its existing ModelOptionsPayload model supplies the concrete wire schema.
No routes, backend models, or dependency locks are modified by this generator.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, get_args

from pydantic import BaseModel

from researchassistant.api.application import create_app
from researchassistant.api.live_contracts import LiveRunSnapshot, ResearchTrailItem
from researchassistant.api.live_service import LiveResearchController
from researchassistant.api.runtime import ApiRuntime
from researchassistant.api.service_manager import WigoloServiceManager
from researchassistant.contracts.discovery_v2 import V2PreviewResult
from researchassistant.contracts.models import V2FinalResearchOutput
from researchassistant.providers.model_choices import ModelOptionsPayload

OUTPUT = Path(__file__).resolve().parents[1] / "lib/generated/api-contracts.ts"


def backend_contract() -> dict[str, Any]:
    runtime = ApiRuntime(
        controller=LiveResearchController(environment={}),
        services=WigoloServiceManager(base_environment={}),
        environment={},
    )
    app = create_app(runtime, load_keychain_on_start=False)
    document = app.openapi()
    supplemental = ModelOptionsPayload.model_json_schema(
        mode="serialization", ref_template="#/components/schemas/{model}"
    )
    definitions = supplemental.pop("$defs", {})
    schemas = document["components"]["schemas"]
    for name, schema in definitions.items():
        # Serialization and validation may differ for Decimal. The catalog's
        # supplemental schemas are used only if OpenAPI does not own the name.
        schemas.setdefault(name, schema)
    schemas["ModelOptionsPayload"] = supplemental
    # Wrap serializers can advertise an unstructured dict in serialization
    # OpenAPI. Their existing validation models describe the historical fields.
    # Traverse their field types too, so nested previews/spans are not weakened.
    seen: set[type[BaseModel]] = set()

    def include_model(annotation: Any) -> None:
        if not isinstance(annotation, type) or not issubclass(annotation, BaseModel):
            for argument in get_args(annotation):
                include_model(argument)
            return
        if annotation in seen:
            return
        seen.add(annotation)
        for field in annotation.model_fields.values():
            include_model(field.annotation)
        name = annotation.__name__
        existing = schemas.get(name, {})
        if existing.get("properties") or existing.get("type") != "object" and existing:
            return
        schema = annotation.model_json_schema(
            mode="validation", ref_template="#/components/schemas/{model}"
        )
        for nested_name, nested in schema.pop("$defs", {}).items():
            current = schemas.get(nested_name, {})
            if not current or current.get("type") == "object" and not current.get("properties"):
                schemas[nested_name] = nested
        schemas[name] = schema

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
            if path == "/api/model-options":
                schema = {"$ref": "#/components/schemas/ModelOptionsPayload"}
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
