// Curated excerpts from real public reports, checked 2026-09-09.
// Local-only example; not a live run or a pipeline-validated research artifact.
export const previewQuestion = "Green technology solves climate change.";
export const previewEvidence = [
  {
    title: "Clean energy slows emissions growth",
    direction: "support" as const,
    quote: "Thanks to growing clean energy deployment, emissions are seeing a structural slowdown.",
    context: "IEA, CO2 Emissions in 2023, Executive Summary (2024). This supports mitigation, not a complete solution: global energy-related CO2 emissions still increased in 2023. The report compares deployment of solar, wind, nuclear, heat pumps and electric cars with a counterfactual without their growth. Report licensed CC BY 4.0.",
    sourceLabel: "IEA · 2024",
    sourceUrl: "https://www.iea.org/reports/co2-emissions-in-2023/executive-summary",
  },
  {
    title: "Industry can cut emissions deeply",
    direction: "support" as const,
    quote: "Technologies exist to take all industry sectors to very low or zero emissions",
    context: "IPCC AR6 Working Group III, Technical Summary (2022), industry discussion. This sentence continues with a requirement for five to fifteen years of intensive innovation, commercialisation and policy to ensure uptake. Technical potential does not guarantee deployment.",
    sourceLabel: "IPCC · 2022",
    sourceUrl: "https://www.ipcc.ch/report/ar6/wg3/chapter/technical-summary/",
  },
  {
    title: "Current policy falls short",
    direction: "challenge" as const,
    quote: "Implementing only current policies would lead to up to 2.8°C of warming",
    context: "UNEP Emissions Gap Report 2025, Key Messages, page 1. This excerpt refers to projected global warming over this century under the report's current-policy scenario. It is a conditional 2025 projection, not inevitable warming or a claim that technology cannot help. Full implementation of national pledges gives a different projection.",
    sourceLabel: "UNEP · 2025",
    sourceUrl: "https://wedocs.unep.org/bitstreams/162130ba-17df-4f8d-80be-fed7384c8442/download",
  },
  {
    title: "Some changes cannot be undone",
    direction: "challenge" as const,
    quote: "Some future changes are unavoidable and/or irreversible",
    context: "IPCC AR6 Synthesis Report, Summary for Policymakers (2023), B.3. The sentence continues that deep, rapid and sustained global greenhouse gas emissions reductions can limit these changes. This qualifies the word ‘solves’; it does not argue against mitigation.",
    sourceLabel: "IPCC · 2023",
    sourceUrl: "https://www.ipcc.ch/report/ar6/syr/summary-for-policymakers/",
  },
];
export const previewStates = ["Ready to begin", "Finding evidence", "Reviewing evidence", "Example complete", "Connection interrupted"] as const;
