from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from enum import IntEnum
from hashlib import sha256
from os import environ, urandom
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError

from orchestrator import (
    ClaimMismatchError,
    FingerprintMismatchError,
    FixturePipelineError,
    ProviderPipelineResult,
    ProviderRunStatus,
    inspect_provider_run,
    request_run_cancellation,
    run_fixture_pipeline,
    run_mvp3b_pipeline,
)
from providers.config import (
    ProviderConfigurationError,
    RunCeilings,
    WigoloConfig,
)
from providers.mimo_factory import MimoProviderFactoryConfig
from store import open_read_only_store, read_provider_run_contract


class CLIExitCode(IntEnum):
    """Stable MVP-4 process exit codes."""

    RELEASED = 0
    BLOCKED = 10
    FAILED = 11
    CANCELLED = 12
    CONFIGURATION_ERROR = 20
    INVALID_INPUT = 21


class CLIArgumentError(ValueError):
    """Invalid command-line input without argparse's process-level exit."""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CLIArgumentError(message)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except CLIArgumentError as exc:
        print(f"invalid input: {exc}", file=sys.stderr)
        return CLIExitCode.INVALID_INPUT

    if args.command == "run-fixture":
        return _run_fixture_command(args.fixture_dir, args.output_dir)
    if args.command == "run":
        return _run_live_command(args, environment=environ)
    if args.command == "inspect-run":
        return _inspect_run_command(args.db_path, args.run_id)
    if args.command == "cancel-run":
        return _cancel_run_command(args.db_path, args.run_id, args.reason)
    parser.print_help()
    return CLIExitCode.INVALID_INPUT


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(description="Debate Research Agent System CLI")
    subparsers = parser.add_subparsers(dest="command")
    run_fixture = subparsers.add_parser(
        "run-fixture",
        help="Run a deterministic offline fixture pipeline.",
    )
    run_fixture.add_argument("fixture_dir", type=Path)
    run_fixture.add_argument("--output-dir", type=Path, default=None)
    live_run = subparsers.add_parser(
        "run",
        help="Run or compatibly resume the approved live provider pipeline.",
    )
    live_run.add_argument("claim", help="Exact public, non-sensitive claim to research.")
    live_run.add_argument("--db-path", type=Path, required=True)
    live_run.add_argument("--run-id", type=UUID, default=None)
    live_run.add_argument("--max-tokens", type=int, required=True)
    live_run.add_argument("--max-cost-usd", required=True)
    live_run.add_argument("--max-llm-calls", type=int, default=160)
    inspect_run = subparsers.add_parser(
        "inspect-run",
        help="Inspect a partial or terminal provider run.",
    )
    inspect_run.add_argument("db_path", type=Path)
    inspect_run.add_argument("run_id", type=UUID)
    cancel_run = subparsers.add_parser(
        "cancel-run",
        help="Persist cancellation for observation at a cooperative boundary.",
    )
    cancel_run.add_argument("db_path", type=Path)
    cancel_run.add_argument("run_id", type=UUID)
    cancel_run.add_argument("--reason", default="cancellation requested by user")
    return parser


def _run_live_command(args: argparse.Namespace, *, environment: Mapping[str, str]) -> int:
    try:
        claim = _validate_exact_claim(args.claim)
        ceilings = _parse_run_ceilings(
            max_tokens=args.max_tokens,
            max_cost_usd=args.max_cost_usd,
            max_llm_calls=args.max_llm_calls,
        )
    except (ValueError, PydanticValidationError) as exc:
        print(f"invalid input: {exc}", file=sys.stderr)
        return CLIExitCode.INVALID_INPUT

    try:
        wigolo = WigoloConfig(base_url=environment.get("WIGOLO_BASE_URL", "http://127.0.0.1:8000"))
        factory_config = MimoProviderFactoryConfig.from_environment(
            environment,
            repository_revision=repository_identity(),
            wigolo=wigolo,
            ceilings=ceilings,
        )
    except (ProviderConfigurationError, PydanticValidationError, ValueError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return CLIExitCode.CONFIGURATION_ERROR

    run_id = args.run_id or UUID(bytes=urandom(16), version=4)
    db_path = args.db_path.resolve()
    _print_launch_summary(db_path, run_id, claim, factory_config)
    try:
        result = run_mvp3b_pipeline(
            claim,
            db_path=db_path,
            factory_config=factory_config,
            run_id=run_id,
        )
    except ClaimMismatchError as exc:
        print(f"invalid input: {exc}", file=sys.stderr)
        return CLIExitCode.INVALID_INPUT
    except FingerprintMismatchError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return CLIExitCode.CONFIGURATION_ERROR
    except (ProviderConfigurationError, PydanticValidationError, TypeError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return CLIExitCode.CONFIGURATION_ERROR
    except ValueError as exc:
        print(f"invalid input: {exc}", file=sys.stderr)
        return CLIExitCode.INVALID_INPUT
    except Exception as exc:
        print(f"run failed before a terminal result: {type(exc).__name__}: {exc}", file=sys.stderr)
        return CLIExitCode.FAILED
    return _print_provider_result(result)


def _validate_exact_claim(value: str) -> str:
    if not value.strip():
        raise ValueError("claim must not be empty")
    if value != value.strip():
        raise ValueError("claim must not contain leading or trailing whitespace")
    return value


def _parse_run_ceilings(
    *,
    max_tokens: int,
    max_cost_usd: str,
    max_llm_calls: int,
) -> RunCeilings:
    try:
        cost = Decimal(max_cost_usd)
    except InvalidOperation as exc:
        raise ValueError("max cost must be a decimal number") from exc
    return RunCeilings(
        max_tokens=max_tokens,
        max_cost_usd=cost,
        max_llm_calls=max_llm_calls,
    )


def repository_identity() -> str:
    """Hash the executable repository surface without runtime databases or secrets."""
    root = Path(__file__).resolve().parent
    candidates = [
        root / "cli.py",
        root / "models.py",
        root / "orchestrator.py",
        root / "store.py",
        root / "utils.py",
        root / "pyproject.toml",
    ]
    for directory, pattern in (("agents", "*.py"), ("providers", "*.py"), ("prompts", "*.md")):
        candidates.extend(sorted((root / directory).glob(pattern)))
    digest = sha256()
    found = False
    for path in sorted(set(candidates)):
        if not path.is_file():
            continue
        found = True
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        payload = path.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    if not found:
        raise ProviderConfigurationError("repository identity surface is unavailable")
    return f"source-sha256:{digest.hexdigest()}"


def _print_launch_summary(
    db_path: Path,
    run_id: UUID,
    claim: str,
    config: MimoProviderFactoryConfig,
) -> None:
    print(f"database: {db_path}")
    print(f"run_id: {run_id}")
    print(f"claim: {claim}")
    print(
        "approved provider stack: Exa Search auto discovery + Wigolo 0.2.1 primary "
        "acquisition + optional Firecrawl fallback + direct Xiaomi MiMo"
    )
    print(f"exa discovery endpoint: {config.exa.base_url}")
    print(f"wigolo endpoint: {config.wigolo.base_url}")
    if config.firecrawl is None:
        print("firecrawl acquisition fallback: disabled")
    else:
        print("firecrawl acquisition fallback: enabled")
        print(f"firecrawl endpoint: {config.firecrawl.base_url}")
    print(f"mimo endpoint: {config.mimo.base_url}")
    print("model alias: mimo-v2.5-pro")
    print(f"pinned model id: {config.mimo.model}")
    print(f"repository identity: {config.repository_revision}")
    print(f"token budget: {config.ceilings.max_tokens}")
    print(f"cost budget usd: {config.ceilings.max_cost_usd}")
    print(f"physical llm call budget: {config.ceilings.max_llm_calls}")


def _print_provider_result(result: ProviderPipelineResult) -> int:
    print(f"status: {result.status.value}")
    if result.status is ProviderRunStatus.RELEASED:
        print(f"rendered hash: {result.rendered_brief_hash}")
        print("final brief:")
        assert result.final_brief is not None
        print(result.final_brief, end="" if result.final_brief.endswith("\n") else "\n")
        return CLIExitCode.RELEASED
    if result.status is ProviderRunStatus.BLOCKED:
        print("rendered hash: none")
        print("validation errors:")
        assert result.validation_result is not None
        for error in result.validation_result.errors:
            print(f"- {error.code.value} at {error.location}: {error.message}")
        return CLIExitCode.BLOCKED
    if result.status is ProviderRunStatus.FAILED:
        print(f"failed stage: {result.current_stage.value}")
        print(f"reason: {result.failure_reason}")
        return CLIExitCode.FAILED
    if result.status is ProviderRunStatus.CANCELLED:
        print(f"observed cooperative boundary: {result.current_stage.value}")
        print(f"reason: {result.failure_reason}")
        print("An active request was allowed to finish before cancellation was observed.")
        return CLIExitCode.CANCELLED
    print(f"current stage: {result.current_stage.value}")
    return CLIExitCode.RELEASED


def _run_fixture_command(fixture_dir: Path, output_dir: Path | None) -> int:
    try:
        result = run_fixture_pipeline(fixture_dir, output_dir=output_dir)
    except FixturePipelineError as exc:
        print(f"fixture pipeline error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"unexpected pipeline error: {exc}", file=sys.stderr)
        return 1

    print(f"run_id: {result.run_id}")
    print(f"result: {result.status}")
    print(f"database: {result.db_path}")
    print(f"audit: {result.audit_path}")
    if result.status == "released":
        print(f"rendered hash: {result.rendered_brief_hash}")
        print("final brief:")
        print(result.final_brief, end="" if result.final_brief.endswith("\n") else "\n")
    else:
        print("rendered hash: none")
        print("validation errors:")
        for error in result.validation_result.errors:
            print(f"- {error.code.value} at {error.location}: {error.message}")
    return 0


def _inspect_run_command(db_path: Path, run_id: UUID) -> int:
    try:
        result = inspect_provider_run(db_path, run_id)
        try:
            with open_read_only_store(db_path) as store:
                contract = read_provider_run_contract(store.connection, run_id)
        except KeyError:
            contract = None
    except Exception as exc:
        print(f"run inspection error: {exc}", file=sys.stderr)
        return CLIExitCode.INVALID_INPUT
    print(f"database: {db_path.resolve()}")
    print(f"run_id: {result.run_id}")
    print(f"claim: {result.raw_claim}")
    print(f"status: {result.status.value}")
    print(f"current stage: {result.current_stage.value}")
    print("checkpoints:")
    if not result.checkpoints:
        print("- none")
    for checkpoint in result.checkpoints:
        suffix = f"; reason={checkpoint.failure_reason}" if checkpoint.failure_reason else ""
        print(
            f"- {checkpoint.stage_key}: {checkpoint.status.value}; "
            f"updated={checkpoint.updated_at.isoformat()}{suffix}"
        )
    print("retrieval attempts:")
    retrieval_outcomes = []
    if result.researcher_result is not None:
        for side in (result.researcher_result.supporting, result.researcher_result.opposing):
            if side.retrieval_batch is not None:
                retrieval_outcomes.extend(side.retrieval_batch.outcomes)
    if not retrieval_outcomes:
        print("- none")
    for outcome in retrieval_outcomes:
        retrieval = outcome.retrieval
        details = [
            f"round={retrieval.query_round}",
            f"rank={retrieval.search_rank}",
            f"url={retrieval.source_url}",
            f"status={outcome.scrape_status.value}",
            f"attempts={outcome.attempts_made}",
        ]
        if outcome.failure_code:
            details.append(f"failure={outcome.failure_code}: {outcome.failure_message or ''}")
        print(f"- {'; '.join(details)}")
    print("model attempts:")
    if not result.model_attempts:
        print("- none")
    for attempt in result.model_attempts:
        details = [
            f"stage={attempt.stage}",
            f"model={attempt.model_alias}",
            f"attempt={attempt.attempt_number}",
            f"status={attempt.status.value}",
        ]
        if attempt.pinned_model_snapshot:
            details.append(f"pinned={attempt.pinned_model_snapshot}")
        if attempt.failure_code:
            details.append(f"failure={attempt.failure_code}: {attempt.failure_reason}")
        print(f"- {'; '.join(details)}")
    print("researcher failures:")
    researcher_failures = []
    if result.researcher_result is not None:
        researcher_failures = [
            *result.researcher_result.supporting.failures,
            *result.researcher_result.opposing.failures,
        ]
    if not researcher_failures:
        print("- none")
    for failure in researcher_failures:
        print(f"- {failure.stage}; {failure.code}: {failure.message}")
    print("validation errors:")
    if result.validation_result is None or not result.validation_result.errors:
        print("- none")
    else:
        for error in result.validation_result.errors:
            print(f"- {error.code.value} at {error.location}: {error.message}")
    print("usage:")
    print(f"- physical model calls: {result.model_calls_used}")
    print(f"- retrieval attempts: {result.retrieval_attempts_used}")
    print(
        f"- total tokens: {result.total_tokens if result.total_tokens is not None else 'unknown'}"
    )
    print(
        "- total cost usd: "
        f"{result.total_cost_usd if result.total_cost_usd is not None else 'unknown'}"
    )
    if contract is None:
        print("provider identity: unavailable (legacy provider run)")
    else:
        print(f"provider identity: {contract.provider_identity}")
        print(f"adapter identity: {contract.adapter_identity}")
        print(f"model identity: {contract.model_identity}")
        print(f"prompt identity: {contract.prompt_identity}")
        print(f"schema identity: {contract.schema_identity}")
        print(f"normalization identity: {contract.normalization_identity}")
        print(f"policy identity: {contract.policy_identity}")
        print(f"repository identity: {contract.repository_revision}")
        print(f"fingerprint: {contract.fingerprint_sha256}")
    if result.failure_reason:
        print(f"reason: {result.failure_reason}")
    print(f"rendered hash: {result.rendered_brief_hash or 'none'}")
    if result.final_brief is not None:
        print("final brief:")
        print(result.final_brief, end="" if result.final_brief.endswith("\n") else "\n")
    return _exit_for_status(result.status)


def _cancel_run_command(db_path: Path, run_id: UUID, reason: str) -> int:
    try:
        request = request_run_cancellation(db_path, run_id, reason=reason)
    except Exception as exc:
        print(f"cancellation request error: {exc}", file=sys.stderr)
        return CLIExitCode.INVALID_INPUT
    print(f"run_id: {request.run_id}")
    print("persisted: yes")
    print(f"cancellation requested at: {request.requested_at.isoformat()}")
    print(f"reason: {request.reason}")
    print("The request will be observed cooperatively; an active call may run to its deadline.")
    return CLIExitCode.RELEASED


def _exit_for_status(status: ProviderRunStatus) -> int:
    return {
        ProviderRunStatus.RELEASED: CLIExitCode.RELEASED,
        ProviderRunStatus.BLOCKED: CLIExitCode.BLOCKED,
        ProviderRunStatus.FAILED: CLIExitCode.FAILED,
        ProviderRunStatus.CANCELLED: CLIExitCode.CANCELLED,
        ProviderRunStatus.RUNNING: CLIExitCode.RELEASED,
    }[status]


if __name__ == "__main__":
    raise SystemExit(main())
