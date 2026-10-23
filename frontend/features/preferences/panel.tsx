import {
  type Configuration,
  type ServiceDiagnostic,
} from "@/lib/api";
import { Dialog } from "@/components/dialog";
import { type Settings, budgetOptions } from "./settings";
import { readableStage } from "../shared/presentation";
import { useHistoryImport } from "./use-history-import";

export function AdvancedPanel({
  settings,
  configuration,
  active,
  onSettings,
  onImportedDatabase,
  onClose,
  onService,
}: {
  settings: Settings;
  configuration: Configuration | null;
  active: boolean;
  onSettings: (settings: Settings) => void;
  onImportedDatabase: (database: string) => void;
  onClose: () => void;
  onService: (action: "start" | "stop") => void;
}) {
  const { importing, importMessage, importDatabase } = useHistoryImport(
    settings.dbPath,
    active,
    onImportedDatabase,
  );
  const update = <K extends keyof Settings>(key: K, value: Settings[K]) =>
    onSettings({ ...settings, [key]: value });
  const sources = [
    [
      "useSerpSearch",
      "SERP Search",
      "Best for familiar Google results across the wider web, including current pages and everyday sources.",
    ],
    [
      "useExa",
      "Exa",
      "Best for finding relevant pages by meaning, not just exact keywords.",
    ],
    [
      "useOpenAlex",
      "OpenAlex",
      "Best for academic studies, papers, and other scholarly research.",
    ],
    [
      "useArxiv",
      "arXiv",
      "Best for research preprints. arXiv does not require an API key.",
    ],
    [
      "usePubmed",
      "PubMed",
      "Best for biomedical literature. It works without a key; a key raises its request allowance.",
    ],
  ] as const;
  const selectedCount = sources.filter(([key]) => settings[key]).length;
  const directionCount =
    Number(settings.supportEnabled) + Number(settings.challengeEnabled);
  return (
    <Dialog title="Research preferences" onClose={onClose}>
      <p className="panel-intro">
        Choose the research direction, discovery providers, and local limits. At
        least one source is required.
      </p>
      <section className="research-options">
        <div className="option-copy">
          <strong>Support</strong>
          <span>Look for evidence that supports the claim.</span>
        </div>
        <button
          type="button"
          role="switch"
          aria-label="Support research"
          aria-checked={settings.supportEnabled}
          className={`switch ${settings.supportEnabled ? "on" : ""}`}
          disabled={active || (directionCount === 1 && settings.supportEnabled)}
          onClick={() => update("supportEnabled", !settings.supportEnabled)}
        >
          <i />
        </button>
        <div className="option-copy">
          <strong>Challenge</strong>
          <span>Look for evidence that challenges or limits the claim.</span>
        </div>
        <button
          type="button"
          role="switch"
          aria-label="Challenge research"
          aria-checked={settings.challengeEnabled}
          className={`switch ${settings.challengeEnabled ? "on" : ""}`}
          disabled={
            active || (directionCount === 1 && settings.challengeEnabled)
          }
          onClick={() => update("challengeEnabled", !settings.challengeEnabled)}
        >
          <i />
        </button>
        {sources.map(([key, label, copy]) => (
          <div className="option-row" key={key}>
            <div className="option-copy">
              <strong>{label}</strong>
              <span>{copy}</span>
            </div>
            <button
              type="button"
              role="switch"
              aria-label={label}
              aria-checked={settings[key]}
              className={`switch ${settings[key] ? "on" : ""}`}
              disabled={active || (selectedCount === 1 && settings[key])}
              onClick={() => update(key, !settings[key])}
            >
              <i />
            </button>
          </div>
        ))}
        <div className="option-row">
          <div className="option-copy">
            <strong>Crossref metadata</strong>
            <span>
              Verify DOI bibliographic details for discovered sources. Crossref
              is metadata only, not evidence.
            </span>
          </div>
          <button
            type="button"
            role="switch"
            aria-label="Crossref metadata enrichment"
            aria-checked={settings.useCrossref}
            className={`switch ${settings.useCrossref ? "on" : ""}`}
            disabled={active}
            onClick={() => update("useCrossref", !settings.useCrossref)}
          >
            <i />
          </button>
        </div>
        <div className="option-copy">
          <strong>Sources to examine</strong>
          <span>
            Set the readable-source target per direction in each round.
            Unavailable sources are replaced within the run limits.
          </span>
        </div>
        <div
          className="source-target"
          role="group"
          aria-label="Sources to examine"
        >
          {([5, 10, 20, 30] as const).map((value) => (
            <button
              type="button"
              key={value}
              className={settings.sourceTarget === value ? "active" : ""}
              disabled={active}
              onClick={() => update("sourceTarget", value)}
            >
              {value}
            </button>
          ))}
        </div>
        <div className="option-row">
          <div className="option-copy">
            <strong>Metadata search depth</strong>
            <span>
              Request a larger pool for ranking; providers may return fewer
              items.
            </span>
          </div>
          <div
            className="source-target"
            role="group"
            aria-label="Metadata search depth"
          >
            {([10, 20, 50] as const).map((value) => (
              <button
                type="button"
                key={value}
                className={settings.metadataDepth === value ? "active" : ""}
                disabled={active}
                onClick={() => update("metadataDepth", value)}
              >
                {value}
              </button>
            ))}
          </div>
        </div>
        <div className="option-row">
          <div className="option-copy">
            <strong>Expand from strong papers</strong>
            <span>
              Use linked scholarly works as additional discovery candidates.
            </span>
          </div>
          <button
            type="button"
            role="switch"
            aria-label="Expand from strong papers"
            aria-checked={settings.seedExpansionEnabled}
            className={`switch ${settings.seedExpansionEnabled ? "on" : ""}`}
            disabled={active}
            onClick={() =>
              update("seedExpansionEnabled", !settings.seedExpansionEnabled)
            }
          >
            <i />
          </button>
        </div>
        <label className="option-row">
          <span className="option-copy">
            <strong>Scholarly search style</strong>
            <span>
              Automatic chooses a supported search style within the same request
              budget.
            </span>
          </span>
          <select
            aria-label="Scholarly search style"
            value={settings.scholarlySearchMode}
            disabled={active}
            onChange={(event) =>
              update(
                "scholarlySearchMode",
                event.target.value as Settings["scholarlySearchMode"],
              )
            }
          >
            <option value="lexical">Keyword based</option>
            <option value="semantic">Meaning based</option>
            <option value="auto">Automatic</option>
          </select>
        </label>
      </section>
      <details className="advanced-details">
        <summary>Advanced limits & history import</summary>
        <div className="settings-grid">
          <label>
            Token ceiling
            <input
              type="number"
              min="1"
              max="500000"
              value={settings.maxTokens}
              onChange={(event) =>
                update("maxTokens", Number(event.target.value))
              }
            />
          </label>
          <label>
            Model cost ceiling
            <select
              value={settings.maxCost}
              onChange={(event) => update("maxCost", event.target.value)}
            >
              {budgetOptions(settings.maxCost).map((value) => (
                <option key={value} value={value}>
                  ${Number(value).toFixed(2)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Call ceiling
            <input
              type="number"
              min="1"
              max="160"
              value={settings.maxCalls}
              onChange={(event) =>
                update("maxCalls", Number(event.target.value))
              }
            />
          </label>
          <label>
            Run ID <span>optional</span>
            <input
              type="text"
              value={settings.runId}
              disabled={importing}
              onChange={(event) => update("runId", event.target.value)}
              placeholder="Created automatically"
            />
          </label>
          <label className="full">
            SQLite database
            <input
              type="text"
              value={settings.dbPath}
              disabled={active || importing}
              onChange={(event) => update("dbPath", event.target.value)}
            />
          </label>
        </div>
        <button
          type="button"
          disabled={active || importing || !settings.dbPath}
          onClick={() => void importDatabase()}
        >
          {importing ? "Importing saved research…" : "Import this database into app storage"}
        </button>
        {importMessage && <p role="status">{importMessage}</p>}
      </details>
      <ServiceCard
        service={configuration?.service ?? null}
        active={active}
        onService={onService}
      />
      <p className="security-note">
        Directions determine the scope of research. A disabled direction is not
        searched or inferred in the result.
      </p>
    </Dialog>
  );
}

export function ServiceCard({
  service,
  active,
  onService,
}: {
  service: ServiceDiagnostic | null;
  active: boolean;
  onService: (action: "start" | "stop") => void;
}) {
  const ready = Boolean(service?.wigolo_ready);
  return (
    <section className="service-card">
      <div>
        <span className={`status-dot ${ready ? "ready" : "setup"}`} />
        <p>Local acquisition</p>
        <strong>
          {ready
            ? "Ready"
            : service
              ? readableStage(service.state)
              : "Unavailable"}
        </strong>
      </div>
      <p>{service?.message ?? "The local API is not responding."}</p>
      <button
        type="button"
        disabled={active || service?.state === "wrong_service"}
        onClick={() => onService(ready ? "stop" : "start")}
      >
        {ready ? "Stop owned service" : "Start local service"}
      </button>
    </section>
  );
}
