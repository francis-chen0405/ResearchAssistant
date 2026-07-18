from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

from orchestrator import (
    FixturePipelineError,
    inspect_provider_run,
    request_run_cancellation,
    run_fixture_pipeline,
)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "run-fixture":
        return _run_fixture_command(args.fixture_dir, args.output_dir)
    if args.command == "inspect-run":
        return _inspect_run_command(args.db_path, args.run_id)
    if args.command == "cancel-run":
        return _cancel_run_command(args.db_path, args.run_id, args.reason)
    parser.print_help()
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Debate Research Agent System CLI")
    subparsers = parser.add_subparsers(dest="command")
    run_fixture = subparsers.add_parser(
        "run-fixture",
        help="Run a deterministic offline fixture pipeline.",
    )
    run_fixture.add_argument("fixture_dir", type=Path)
    run_fixture.add_argument("--output-dir", type=Path, default=None)
    inspect_run = subparsers.add_parser(
        "inspect-run",
        help="Inspect a partial or terminal Phase 9 provider run.",
    )
    inspect_run.add_argument("db_path", type=Path)
    inspect_run.add_argument("run_id", type=UUID)
    cancel_run = subparsers.add_parser(
        "cancel-run",
        help="Request cancellation at the next Phase 9 stage boundary.",
    )
    cancel_run.add_argument("db_path", type=Path)
    cancel_run.add_argument("run_id", type=UUID)
    cancel_run.add_argument("--reason", default="cancellation requested by user")
    return parser


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
    except Exception as exc:
        print(f"run inspection error: {exc}", file=sys.stderr)
        return 1
    print(f"run_id: {result.run_id}")
    print(f"status: {result.status.value}")
    print(f"current stage: {result.current_stage.value}")
    print(f"model calls: {result.model_calls_used}")
    print(f"retrieval attempts: {result.retrieval_attempts_used}")
    print(f"rendered hash: {result.rendered_brief_hash or 'none'}")
    if result.failure_reason:
        print(f"reason: {result.failure_reason}")
    return 0


def _cancel_run_command(db_path: Path, run_id: UUID, reason: str) -> int:
    try:
        request = request_run_cancellation(db_path, run_id, reason=reason)
    except Exception as exc:
        print(f"cancellation request error: {exc}", file=sys.stderr)
        return 1
    print(f"run_id: {request.run_id}")
    print(f"cancellation requested at: {request.requested_at.isoformat()}")
    print(f"reason: {request.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
