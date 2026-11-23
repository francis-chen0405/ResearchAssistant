import { useState } from "react";
import { type Configuration, type ModelOptions, type ServiceDiagnostic } from "@/lib/api";
import { Dialog } from "@/components/dialog";
import { ProviderSetup } from "@/components/provider-setup";
import { Banner, Button, Switch } from "@/components/ui";
import { Icon } from "@/components/icons";
import { MAX_RUN_TOKENS, type Settings } from "./settings";
import { useHistoryImport } from "./use-history-import";
import { ModelSelection } from "./model-selection";
import { useTheme, type ThemeChoice } from "./theme";

export type SettingsSection = "defaults" | "providers" | "models" | "appearance";

const sections: { id: SettingsSection; label: string }[] = [
  { id: "defaults", label: "Research defaults" },
  { id: "providers", label: "Search providers" },
  { id: "models", label: "Models" },
  { id: "appearance", label: "Appearance" },
];

function Segmented<T extends string | number>({
  label,
  value,
  options,
  onChange,
  disabled,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  disabled?: boolean;
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          type="button"
          key={String(option.value)}
          aria-pressed={value === option.value}
          disabled={disabled}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function AdvancedPanel({
  settings,
  configuration,
  modelOptions,
  active,
  initialSection,
  lessMotion,
  onLessMotion,
  onSettings,
  onImportedDatabase,
  onClose,
  onService,
  onProvidersSaved,
}: {
  settings: Settings;
  configuration: Configuration | null;
  modelOptions: ModelOptions;
  active: boolean;
  initialSection?: SettingsSection;
  lessMotion: boolean;
  onLessMotion: (value: boolean) => void;
  onSettings: (settings: Settings) => void;
  onImportedDatabase: (database: string) => void;
  onClose: () => void;
  onService: (action: "start" | "stop") => void;
  onProvidersSaved: (message: string) => Promise<void>;
}) {
  const [section, setSection] = useState<SettingsSection>(
    initialSection ?? (configuration && !configuration.configured ? "providers" : "defaults"),
  );
  const [theme, setTheme] = useTheme();
  const { importing, importMessage, importDatabase } = useHistoryImport(settings.dbPath, active, onImportedDatabase);
  const update = <K extends keyof Settings>(key: K, value: Settings[K]) => onSettings({ ...settings, [key]: value });
  const setupNeeded = Boolean(configuration && !configuration.configured);
  return (
    <Dialog title="Settings" onClose={onClose} wide>
      <div className="settings-layout">
        <nav className="settings-nav" aria-label="Settings sections">
          {sections.map((item) => (
            <button
              type="button"
              key={item.id}
              aria-current={section === item.id ? "page" : undefined}
              className="settings-nav-item"
              onClick={() => setSection(item.id)}
            >
              {item.label}
              {item.id === "providers" && setupNeeded && <span className="attention-dot" aria-hidden="true" title="Needs attention" />}
            </button>
          ))}
        </nav>
        <div className="settings-body">
          {active && (
            <Banner tone="info" title="Settings are locked while research runs">
              <p>Changes would not apply to the run in progress. They unlock when it finishes or is cancelled.</p>
            </Banner>
          )}

          {section === "defaults" && (
            <section className="settings-section" aria-labelledby="settings-defaults">
              <h3 id="settings-defaults">Research defaults</h3>
              <p className="subtle">Direction and spend cap are chosen on the New research page for each run.</p>
              <div className="setting">
                <div className="setting-copy">
                  <strong>Sources per side, per round</strong>
                  <span>How many readable sources to aim for. Unreadable sources are replaced within the run limits.</span>
                </div>
                <Segmented
                  label="Sources to examine"
                  value={settings.sourceTarget}
                  options={([5, 10, 20, 30] as const).map((value) => ({ value, label: String(value) }))}
                  onChange={(value) => update("sourceTarget", value)}
                  disabled={active}
                />
              </div>
              <div className="setting">
                <div className="setting-copy">
                  <strong>Search depth</strong>
                  <span>How many results to request for ranking. Providers may return fewer.</span>
                </div>
                <Segmented
                  label="Metadata search depth"
                  value={settings.metadataDepth}
                  options={([10, 20, 30, 50] as const).map((value) => ({ value, label: String(value) }))}
                  onChange={(value) => update("metadataDepth", value)}
                  disabled={active}
                />
              </div>
              <Switch
                label="Expand from strong papers"
                description="Follow citations from strong scholarly papers to find related work."
                checked={settings.seedExpansionEnabled}
                onChange={(value) => update("seedExpansionEnabled", value)}
                disabled={active}
              />
              <Switch
                label="Crossref metadata enrichment"
                description="Check DOI details for sources found. Crossref provides metadata only, not evidence."
                checked={settings.useCrossref}
                onChange={(value) => update("useCrossref", value)}
                disabled={active}
              />
              <div className="setting">
                <div className="setting-copy">
                  <strong>Scholarly search style</strong>
                  <span>Automatic picks a supported style within the same request budget.</span>
                </div>
                <div className="select">
                  <select
                    aria-label="Scholarly search style"
                    value={settings.scholarlySearchMode}
                    disabled={active}
                    onChange={(event) => update("scholarlySearchMode", event.target.value as Settings["scholarlySearchMode"])}
                  >
                    <option value="lexical">Keyword based</option>
                    <option value="semantic" disabled={!settings.useOpenAlex}>Meaning based (OpenAlex)</option>
                    <option value="auto">Automatic</option>
                  </select>
                  <Icon name="chevronDown" />
                </div>
              </div>
              <details className="disclosure advanced-details">
                <summary><span className="disclosure-summary">Advanced limits & history import</span></summary>
                <div className="disclosure-body settings-grid">
                  <label className="field">
                    <span>Token ceiling</span>
                    <input type="number" min="1" max={MAX_RUN_TOKENS} value={settings.maxTokens} disabled={active}
                      onChange={(event) => update("maxTokens", Number(event.target.value))} />
                  </label>
                  <label className="field">
                    <span>Call ceiling</span>
                    <input type="number" min="1" max="160" value={settings.maxCalls} disabled={active}
                      onChange={(event) => update("maxCalls", Number(event.target.value))} />
                  </label>
                  <div className="field">
                    <label htmlFor="resume-run-id">
                      <span>Run ID <span>optional</span></span>
                      <input id="resume-run-id" type="text" value={settings.runId} disabled={active || importing} aria-describedby="run-id-hint"
                        onChange={(event) => update("runId", event.target.value)}
                        placeholder="Created automatically" />
                    </label>
                    <small className="field-hint" id="run-id-hint">To resume a specific run, use Resume on that run&rsquo;s page.</small>
                  </div>
                  <label className="field full">
                    <span>SQLite database</span>
                    <input type="text" value={settings.dbPath} disabled={active || importing}
                      onChange={(event) => update("dbPath", event.target.value)} />
                  </label>
                  <div className="full row">
                    <Button disabled={active || importing || !settings.dbPath} onClick={() => void importDatabase()}>
                      {importing ? "Importing saved research…" : "Import this database into app storage"}
                    </Button>
                    {importMessage && <p role="status">{importMessage}</p>}
                  </div>
                </div>
              </details>
              <PageReader service={configuration?.service ?? null} active={active} onService={onService} />
            </section>
          )}

          {section === "providers" && (
            <section className="settings-section" aria-labelledby="settings-providers">
              <h3 id="settings-providers">Search providers and keys</h3>
              <ProviderSetup
                configuration={configuration}
                selectedProviders={{
                  use_serpsearch: settings.useSerpSearch,
                  use_exa: settings.useExa,
                  use_openalex: settings.useOpenAlex,
                  use_arxiv: settings.useArxiv,
                  use_pubmed: settings.usePubmed,
                  use_brave: settings.useBrave,
                  use_serper: settings.useSerper,
                }}
                stageModels={settings.stageModels}
                settings={settings}
                onSettings={onSettings}
                locked={active}
                onSaved={onProvidersSaved}
              />
            </section>
          )}

          {section === "models" && (
            <section className="settings-section" aria-labelledby="settings-models">
              <h3 id="settings-models">Models</h3>
              <p className="subtle">Each research step can use a different model. The defaults suit most claims.</p>
              <ModelSelection
                idPrefix="stage-model"
                settings={settings}
                modelOptions={modelOptions}
                onSettings={onSettings}
                disabled={active}
              />
            </section>
          )}

          {section === "appearance" && (
            <section className="settings-section" aria-labelledby="settings-appearance">
              <h3 id="settings-appearance">Appearance</h3>
              <Switch label="Reduce motion" description="Pause automatic examples and reduce movement for this session." checked={lessMotion} onChange={onLessMotion} />
              <div className="setting">
                <div className="setting-copy">
                  <strong>Theme</strong>
                  <span>System follows your computer&rsquo;s light or dark setting.</span>
                </div>
                <Segmented<ThemeChoice>
                  label="Theme"
                  value={theme}
                  options={[{ value: "system", label: "System" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }]}
                  onChange={setTheme}
                />
              </div>
            </section>
          )}
        </div>
      </div>
    </Dialog>
  );
}

/** The local page reader (Wigolo), described in plain words. */
export function PageReader({
  service,
  active,
  onService,
}: {
  service: ServiceDiagnostic | null;
  active: boolean;
  onService: (action: "start" | "stop") => void;
}) {
  const ready = Boolean(service?.wigolo_ready);
  const state = ready ? "Ready" : !service ? "Not responding" : service.state === "starting" ? "Starting" : "Stopped";
  return (
    <div className="setting page-reader">
      <div className="setting-copy">
        <strong>Page reader: {state}</strong>
        <span>The local tool that opens and reads source pages. It starts automatically when research begins.</span>
      </div>
      <Button size="sm" disabled={active || service?.state === "wrong_service"} onClick={() => onService(ready ? "stop" : "start")}>
        {ready ? "Stop page reader" : "Start page reader"}
      </Button>
    </div>
  );
}
