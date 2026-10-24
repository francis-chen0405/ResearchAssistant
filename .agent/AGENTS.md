# Repository instructions

Read [conventions](../docs/project/CONVENTIONS.md), [architecture](../docs/project/ARCHITECTURE.md)
and [decisions](../docs/project/DECISIONS.md) before changes. The current user request
defines scope; [the plan index](PLANS.md) links follow-up owners and any active plan.
[STATUS](../docs/project/STATUS.md) owns current behavior, limits and next priorities.
Use [the test map](../tests/README.md) for focused checks and full-suite discovery.
Routine changes need no new plan, verification report, audit, snapshot or history entry.
Put validation in the commit or PR description and final response. Update STATUS only
when behavior, a material limitation, acceptance state or the next priority changes.
For complex or risky work, maintain one lightweight active plan; record durable choices
in the existing decisions document. Dedicated reports need a continuing purpose or an
explicit user request. Verification requirements and runtime evidence remain mandatory.
Keep active requirements and unresolved findings in the working tree. Historical
snapshots retired by the documentation cleanup are recoverable through Git; see
[history recovery](../docs/history.md#recovering-retired-snapshots). Retain other
completed task records at their existing paths until separately reviewed.

<!-- codebase-memory-mcp:start -->
# Codebase Knowledge Graph (codebase-memory-mcp)

When a project is indexed, use codebase-memory-mcp as an advisory structural map.
Prefer graph tools for discovery and dependency tracing, but do not treat the graph
as the source of truth: check index freshness and verify important conclusions
against live source files, the current git diff, and relevant tests.

After branch switches or large repository changes, run `index_status` and refresh
with `index_repository` when the graph is stale or incomplete.

## Priority Order
1. `search_graph` — find functions, classes, routes, variables by pattern
2. `trace_path` — trace who calls a function or what it calls
3. `get_code_snippet` — read specific function/class source code
4. `query_graph` — run Cypher queries for complex patterns
5. `get_architecture` — high-level project summary

## When to fall back to grep/glob
- Searching for string literals, error messages, config values
- Searching non-code files (Dockerfiles, shell scripts, configs)
- When MCP tools return insufficient results
- Verifying graph findings before consequential edits or conclusions

## Examples
- Find a handler: `search_graph(name_pattern=".*OrderHandler.*")`
- Who calls it: `trace_path(function_name="OrderHandler", direction="inbound")`
- Read source: `get_code_snippet(qualified_name="pkg/orders.OrderHandler")`
<!-- codebase-memory-mcp:end -->
