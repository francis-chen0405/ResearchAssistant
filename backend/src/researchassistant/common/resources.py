"""Canonical executable resources for source, installed and frozen runtimes."""

import sys
from importlib.resources import files
from importlib.resources.abc import Traversable

PROMPT_NAMES = (
    "analyst.md",
    "extractor.md",
    "gap_analysis.md",
    "planner.md",
    "reviewer.md",
    "scout.md",
    "search_agent.md",
    "search_agent_v2.md",
    "search_agent_v3.md",
    "source_selection.md",
    "source_selection_v3.md",
    "synthesizer.md",
    "v2_evidence_analyst.md",
    "v2_evidence_analyst_v9.md",
    "v2_initial_planner.md",
    "v2_initial_planner_v2.md",
    "v2_scout.md",
    "v2_scout_v2.md",
)


def _resource_root() -> Traversable:
    if getattr(sys, "frozen", False):
        from researchassistant.runtime.application_runtime import (
            _default_source_root,
            source_directory,
        )

        return source_directory(_default_source_root()) / "researchassistant"
    return files("researchassistant")


def prompt_directory() -> Traversable:
    return _resource_root().joinpath("prompts")


def prompt_resource(name: str) -> Traversable:
    if name not in PROMPT_NAMES:
        raise ValueError(f"unknown executable prompt: {name}")
    return prompt_directory().joinpath(name)


def pdf_font_resource() -> Traversable:
    return _resource_root().joinpath("evidence/fonts/unifont-15.0.01.ttf")
