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
