from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    _REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

from evaluations.evaluator import evaluate_corpus, write_evaluation_outputs  # noqa: E402
from evaluations.schema import LiveEvaluationProvider  # noqa: E402

DEFAULT_CORPUS_PATH = Path(__file__).resolve().parent / "cases" / "offline-corpus.json"
DEFAULT_JSON_OUTPUT = Path(__file__).resolve().parent / "output" / "results.json"
DEFAULT_SUMMARY_OUTPUT = Path(__file__).resolve().parent / "output" / "summary.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic Phase 10 offline evaluations.",
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument(
        "--enable-live",
        action="store_true",
        help="Enable optional live comparison; requires an injected provider.",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    live_provider: LiveEvaluationProvider | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = evaluate_corpus(
            args.corpus,
            live_enabled=args.enable_live,
            live_provider=live_provider,
        )
        write_evaluation_outputs(
            report,
            json_path=args.json_output,
            summary_path=args.summary_output,
        )
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        print(f"evaluation failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - exact subclasses are deliberately open-ended
        print(f"unexpected evaluation error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    print(
        f"Phase 10 evaluation {'passed' if report.passed else 'failed'}; "
        f"JSON={args.json_output} summary={args.summary_output}"
    )
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
