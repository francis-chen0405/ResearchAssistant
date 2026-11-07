"""Conservative claim and study-design cues for metadata triage."""

from __future__ import annotations

import re
from dataclasses import dataclass

_WORD = re.compile(r"[^\W_]+")
_SCOPE = re.compile(r"\b(?:among|in|within|for)\s+", re.I)
_COMPARATOR = re.compile(r"\b(?:compared (?:with|to)|versus|vs\.?|relative to|than)\s+", re.I)
_EFFECT = re.compile(
    r"\b(?:caus\w*|reduc\w*|decreas\w*|increas\w*|rais\w*|lower\w*|improv\w*|"
    r"prevent\w*|affect\w*|worsen\w*|chang\w*|predict\w*|"
    r"(?:is|are) (?:positively |negatively )?(?:associated|linked|correlated) with|"
    r"(?:is|are) (?:more|less|higher|lower|better|worse)\b)\s+",
    re.I,
)
_EFFECT_OF = re.compile(r"\b(?:effects?|impacts?|influence) of (.+?) on (.+)", re.I)
_DESIGN = re.compile(
    r"\b(?:randomi[sz]\w*|quasi.experiment\w*|controlled (?:study|trial|comparison)|"
    r"natural experiment|difference.in.differences|regression discontinuity|"
    r"interrupted time series|matched (?:groups?|cohort|controls?)|"
    r"(?:retrospective|prospective|longitudinal|population.based) (?:study|cohort|analysis)|"
    r"systematic review|meta.analysis|field experiment)\b",
    re.I,
)
_OBSERVATION = re.compile(
    r"\b(?:we (?:collected|analy[sz]ed|measured|surveyed|compared|estimated|evaluated)|"
    r"our (?:survey|sample|analysis)|(?:linked|administrative|hospital|police|registry) "
    r"(?:records|data)|(?:official|administrative|surveillance) (?:statistics|data)|"
    r"annual (?:statistical|surveillance|monitoring) report|"
    r"(?:population|national) census|statistical (?:release|tables?)|"
    r"(?:case.control|cohort|cross.sectional|survey) (?:study|data|analysis))\b",
    re.I,
)
_COMPARISON_DESIGN = re.compile(
    r"\b(?:placebo|control(?:led)? (?:group|sites?|trial|comparison)|untreated|"
    r"comparison (?:group|sites?)|before and after|pre.post|baseline|counterfactual|"
    r"difference.in.differences|interrupted time series|regression discontinuity)\b",
    re.I,
)
_COMMENTARY = re.compile(
    r"^(?:opinion|commentary|editorial|perspective|letter to the editor)\b|"
    r"\b(?:this (?:opinion|commentary|editorial|essay)|opinion piece)\b",
    re.I,
)
_STOP = frozenset(
    "a an the and or of to in on for with by is are was were be been that this it as at from "
    "does do can may will would should did not no more less than among within has have had "
    "effect effects impact impacts association relationship significantly significant "
    "higher lower increased decreased reduces reduce decreased compared associated".split()
)


def _terms(text: str) -> frozenset[str]:
    def stem(word: str) -> str:
        if len(word) > 5 and word.endswith("ies"):
            return word[:-3] + "y"
        if len(word) > 4 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
            return word[:-1]
        return word

    return frozenset(stem(word) for word in _WORD.findall(text.casefold()) if word not in _STOP)


@dataclass(frozen=True)
class ClaimFacets:
    exposure: frozenset[str]
    outcome: frozenset[str]
    setting: frozenset[str]
    comparison: frozenset[str]
    comparative: bool

    @classmethod
    def from_claim(cls, exact_claim: str) -> ClaimFacets:
        claim = exact_claim[:8000].strip()
        comparison = _COMPARATOR.split(claim, maxsplit=1)
        main = comparison[0]
        comparator = comparison[1] if len(comparison) == 2 else ""
        if not main and "," in comparator:
            comparator, main = comparator.split(",", 1)
        setting = frozenset()
        if main.casefold().startswith(("in ", "among ", "within ")) and "," in main:
            context, main = main.split(",", 1)
            setting = _terms(context)
        effect = _EFFECT_OF.search(main)
        if effect:
            exposure, outcome = effect.groups()
        else:
            verb = next(
                (match for match in _EFFECT.finditer(main) if _terms(main[: match.start()])),
                None,
            )
            exposure, outcome = (main[: verb.start()], main[verb.end() :]) if verb else ("", main)
        if not setting and (scope := _SCOPE.search(outcome)):
            setting = _terms(outcome[scope.end() :])
            outcome = outcome[: scope.start()]
        if not setting and (scope := _SCOPE.search(comparator)):
            setting = _terms(comparator[scope.end() :])
            comparator = comparator[: scope.start()]
        named_comparison = _terms(comparator)
        return cls(
            _terms(exposure),
            _terms(outcome),
            setting,
            named_comparison,
            bool(effect or exposure or named_comparison),
        )

    def fit(
        self, *, title: str | None, abstract: str | None, snippet: str | None, source_type: str
    ) -> tuple[float | None, float | None]:
        text = " ".join((title or "", abstract or "", snippet or ""))[:8000]
        if not text.strip():
            return None, None
        terms = _terms(text)
        # A missing mention in title-only metadata is uncertainty. A snippet can
        # give positive signals, but still does not establish what the study omitted.
        unknown = 0.5 if not abstract else 0.15
        matches = [
            (weight, max(unknown, len(facet & terms) / len(facet)))
            for facet, weight in ((self.exposure, 3), (self.outcome, 4), (self.setting, 3))
            if facet
        ]
        if self.comparison:
            matches.append((3, max(unknown, len(self.comparison & terms) / len(self.comparison))))
        if self.comparative:
            comparison_cue = _COMPARATOR.search(text) or _COMPARISON_DESIGN.search(text)
            matches.append((2, 1.0 if comparison_cue else unknown))
        total = sum(weight for weight, _ in matches)
        directness = sum(weight * fit for weight, fit in matches) / total if total else None
        if source_type in {"news", "blog", "magazine", "opinion", "editorial", "commentary"} or (
            _COMMENTARY.search(title or "") or _COMMENTARY.search(abstract or "")
        ):
            method = 0.05
        elif _DESIGN.search(text):
            method = 1.0
        elif _OBSERVATION.search(text):
            method = 0.8
        else:
            method = None
        return directness, method
