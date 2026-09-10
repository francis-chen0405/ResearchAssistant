# Climate technology preview sources

Checked 2026-09-09. The home preview tests the user-provided claim “Green technology
solves climate change.” Four manually curated cards use short exact excerpts from
public assessments, not fictional research. Their supporting/challenging placement is
editorial: support concerns mitigation potential, while challenge qualifies the broad
word “solves.” These are not artifacts admitted by the live research pipeline.
The preview remains local, labelled Example, and makes no provider calls. Its displayed
budget/usage is simulated, not the cost of this source review.

| Card | Source and locator | Scope and qualification |
| --- | --- | --- |
| Clean energy slows emissions growth | [IEA, CO2 Emissions in 2023, Executive Summary (2024)](https://www.iea.org/reports/co2-emissions-in-2023/executive-summary), fourth bullet | Historical global energy-related CO2 growth slowed; it did not stop. CC BY 4.0 report. |
| Industry can cut emissions deeply | [IPCC AR6 WGIII Technical Summary (2022)](https://www.ipcc.ch/report/ar6/wg3/chapter/technical-summary/), industry discussion | The excerpt describes potential. Its sentence continues with five to fifteen years of innovation, commercialisation and policy needed for uptake. |
| Current policy falls short | [UNEP Emissions Gap Report 2025, Key Messages](https://wedocs.unep.org/bitstreams/162130ba-17df-4f8d-80be-fed7384c8442/download), page 1 | The current-policy warming projection is conditional and dated to 2025; national pledges and net-zero scenarios yield other projections. |
| Some changes cannot be undone | [IPCC AR6 Synthesis Report, Summary for Policymakers (2023)](https://www.ipcc.ch/report/ar6/syr/summary-for-policymakers/), B.3 | The sentence also explains that deep, rapid, sustained greenhouse gas reductions can limit these changes. It does not argue against mitigation. |

`web/lib/preview.ts` stores the excerpts, dates, links and context. Cards expose source
links and expandable qualifications. No paid live research was run to create them.
