# MVP-6.7 — Repository-Wide Type Contract Enforcement

## Authority and Boundary

MVP-6.5 and MVP-6.6 are complete prerequisites. The user explicitly authorized MVP-6.7
to resolve the remaining contradiction between the repository convention requiring type
hints on every function signature and untyped test/helper signatures. This is the final
planned contradiction-audit remediation phase. No phase after MVP-6.7 is authorized.

This phase changes annotations, a dependency-free regression test, and phase records
only. It does not change runtime behavior, acceptance criteria, provider behavior,
evidence policy, persistence, budgets, exit codes, fingerprints, or Pydantic schemas.

## Enforced Repository Contract

- Every repository-owned Python `def` and `async def` has an explicit return annotation.
- Every positional-only, positional-or-keyword, keyword-only, variadic positional, and
  variadic keyword parameter has an explicit annotation.
- Only conventional receiver parameters named `self` or `cls` may remain unannotated.
- The rule covers production code, tests, fixtures, callbacks, local helpers, nested
  functions, class methods, static methods, generators, and async functions.
- Lambdas are outside this function-signature rule. Suppression comments and broad
  `Any` annotations are not substitutes for accurate contracts.
- Functions returning no value use `-> None`; generators use an appropriate iterator or
  generator return type.

## Dependency-Free Enforcement

`tests/test_type_contracts.py` deterministically discovers Python files beneath the
repository root while excluding only recognized virtual-environment, cache, vendor,
coverage, and build-output directories. It sorts repository-relative paths, parses each
file with `ast.parse`, visits `ast.FunctionDef` and `ast.AsyncFunctionDef` recursively,
and checks every parameter category plus return annotations.

The test reports every violation in one run with repository-relative path, source line,
discoverable qualified name, and the missing parameter or return annotation. Parse
failures are actionable test diagnostics. It does not call Git, depend on operating-
system directory order, or add a checker dependency.

## Regression-First Inventory and Corrections

The independent AST inventory found 61 repository-owned Python files and 1,195 function
definitions before the enforcement test was added. It reported 11 missing annotations
across seven signatures in five test files. The new regression test was added first and
demonstrated that complete failure list before any signature was corrected.

Corrections are limited to:

- `tests/test_mvp1.py`: pytest monkeypatch fixture plus nested variadic callback.
- `tests/test_mvp3a_pipeline.py`: provider-pipeline helper configuration and result.
- `tests/test_mvp6_3_security.py`: nested byte-stream iterator return.
- `tests/test_phase4.py`: pytest temporary-path fixture.
- `tests/test_phase8.py`: fake-provider request/result and request-builder result.

The corrections use `pytest.MonkeyPatch`, `pathlib.Path`, project configuration/result
models, `LLMRequest`, `BaseModel | dict[str, object]`, and `Iterator[bytes]`. The two old
`type: ignore[no-untyped-def]` suppressions on affected signatures were removed. Function
bodies, fixture parameter names, decorator order, monkeypatch behavior, assertions, and
expected values are unchanged.

## Verification and Completion Record

MVP-6.7 is complete only after the isolated enforcement test, every focused affected
suite, full pytest suite, all offline evaluations, Ruff lint/format, independent AST
scan, in-memory Python compilation, launcher syntax, suppression/diff/artifact audits,
and `git diff --check` pass. Exact final results are recorded in `STATUS.md` and
`HANDOFF.md`.

No dependency, SQLite migration, provider call, provider spending, generated tracked
artifact, fixture mutation, or commit is part of this phase. Runtime behavior and test
acceptance criteria remain unchanged. Completion closes the contradiction-audit
remediation sequence; no later phase has started or been authorized.
