import type { Settings } from "../preferences/settings";

/** Depth presets write the existing source target, search depth and spend cap. */
export const depthPresets = [
  { id: "Quick", sourceTarget: 5, metadataDepth: 20, maxCost: "0.20", hint: "A fast first look." },
  { id: "Standard", sourceTarget: 10, metadataDepth: 30, maxCost: "0.20", hint: "A balanced search for most claims." },
  { id: "Thorough", sourceTarget: 20, metadataDepth: 50, maxCost: "1.00", hint: "More sources and a higher spend cap." },
] as const;

export function presetOf(settings: Pick<Settings, "sourceTarget" | "metadataDepth" | "maxCost">): string {
  return (
    depthPresets.find(
      (preset) =>
        preset.sourceTarget === settings.sourceTarget &&
        preset.metadataDepth === settings.metadataDepth &&
        Number(preset.maxCost) === Number(settings.maxCost),
    )?.id ?? "Custom"
  );
}
