import {
  STAGE_MODEL_KEYS,
  type InterfaceSettings,
  type ModelOption,
  type StageModelKey,
  type StageModels,
} from "@/lib/api";

export type MainView = "home" | "research" | "history";

export type Settings = InterfaceSettings & { runId: string };

export const defaultModelOptions: ModelOption[] = [
  {
    id: "gpt-6-luna-high",
    label: "GPT-6 Luna · High",
    provider: "openai",
    input_per_million: "",
    output_per_million: "",
  },
  {
    id: "gpt-6-luna-xhigh",
    label: "GPT-6 Luna · XHigh",
    provider: "openai",
    input_per_million: "",
    output_per_million: "",
  },
  {
    id: "mimo-v2.6-pro",
    label: "MiMo v2.6 · Pro",
    provider: "mimo",
    input_per_million: "",
    output_per_million: "",
  },
  {
    id: "mimo-v2.6-flash",
    label: "MiMo v2.6 · Flash",
    provider: "mimo",
    input_per_million: "",
    output_per_million: "",
  },
  {
    id: "gpt-6-sol-high",
    label: "GPT-6 Sol · High",
    provider: "openai",
    input_per_million: "",
    output_per_million: "",
  },
  {
    id: "gpt-5.6-terra-high",
    label: "GPT-5.6 Terra · High",
    provider: "openai",
    input_per_million: "",
    output_per_million: "",
  },
];

export const stageLabels: Record<StageModelKey, string> = {
  planner: "Planning",
  scout: "Scouting",
  gap_analysis: "Gap analysis",
  search_agent: "Search planning",
  source_selection: "Source selection",
  extractor: "Exact extraction",
  analyst: "Evidence analysis",
};

export function mergeStageModels(
  current: Partial<StageModels> | undefined,
  defaults: StageModels,
): StageModels {
  return STAGE_MODEL_KEYS.reduce((result, key) => {
    result[key] = current?.[key] ?? defaults[key];
    return result;
  }, {} as StageModels);
}

export function providerRequirement(stageModels: StageModels): string {
  const usesMiMo = Object.values(stageModels).some((choice) =>
    choice.startsWith("mimo-"),
  );
  const usesOpenAI = Object.values(stageModels).some((choice) =>
    choice.startsWith("gpt-"),
  );
  if (usesMiMo && usesOpenAI)
    return "MiMo and OpenAI keys required for the selected stages.";
  if (usesMiMo) return "A MiMo key is required for the selected stages.";
  return "An OpenAI key is required for the selected stages.";
}

export function budgetOptions(current: string): string[] {
  const values = ["0.20", "0.50", "1.00", "2.00", "5.00", "10.00", "20.00"];
  const numeric = Number(current);
  if (
    Number.isFinite(numeric) &&
    numeric > 0 &&
    numeric <= 20 &&
    !values.includes(current)
  )
    values.push(current);
  return values;
}
