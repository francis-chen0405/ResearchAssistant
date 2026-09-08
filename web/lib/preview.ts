// Fictional, local-only demonstration. Never sent to the research API.
export const previewQuestion = "Can greener streets make cities cooler?";
export const previewEvidence = [
  { title: "Urban canopy study", kind: "Illustrative study", direction: "support" as const, quote: "Tree-lined streets recorded lower afternoon surface temperatures.", context: "Fictional excerpt showing how an exact source passage would appear. Surface temperature is not the same as air temperature." },
  { title: "A closer look at local conditions", kind: "Illustrative review", direction: "challenge" as const, quote: "Cooling varied with canopy density, climate, and the surrounding built environment.", context: "Fictional excerpt. Real results preserve quotations, source context, and admission limitations." },
];
export const previewStates = ["Ready to begin", "Finding evidence", "Reviewing evidence", "Example complete", "Connection interrupted"] as const;
