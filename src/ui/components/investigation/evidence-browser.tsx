"use client";

import { Filter, ListTree, Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import type { EvidenceView, Investigation, LogEvidence } from "@/lib/investigation-contract";
import { formatUtc } from "@/lib/format-utc";
import styles from "./evidence.module.css";

type EvidenceBrowserProps = {
  investigation: Investigation;
  view: EvidenceView;
  selectedEvidenceId: string | null;
  templateId: string | null;
  service: string | null;
  onViewChange: (view: EvidenceView) => void;
  onSelectEvidence: (id: string | null) => void;
  onSelectTemplate: (id: string | null) => void;
  onSelectService: (service: string | null) => void;
};

const views: EvidenceView[] = ["timeline", "logs", "patterns"];
const levels: Array<LogEvidence["level"]> = ["info", "warn", "error", "critical"];

function Metadata({ investigation }: { investigation: Investigation }) {
  const { source } = investigation;
  return (
    <section className={styles.metadata} aria-label="Evidence source metadata">
      <div><span>Source</span><strong>{source.mode} · {source.dataset}</strong></div>
      <div><span>UTC range</span><strong>{formatUtc(source.start)} — {formatUtc(source.end)}</strong></div>
      <div><span>Coverage</span><strong>{source.coverage}</strong></div>
      <p>{source.queryDescription}</p>
    </section>
  );
}

function Inspector({ evidence, selectedEvidenceId, onClear }: { evidence: LogEvidence | undefined; selectedEvidenceId: string | null; onClear: () => void }) {
  if (!selectedEvidenceId) return null;
  if (!evidence) {
    return <section className={styles.inspector} aria-label="Evidence inspector"><h3>Evidence unavailable</h3><p>The selected evidence ID <code>{selectedEvidenceId}</code> is not available in this investigation.</p><button type="button" onClick={onClear}>Clear selection</button></section>;
  }

  return (
    <section className={styles.inspector} aria-label={`Evidence inspector for ${evidence.id}`}>
      <div className={styles.inspectorHead}>
        <div><span className={styles.kicker}>RAW EVENT INSPECTOR</span><h3>{evidence.id}</h3></div>
        <button type="button" onClick={onClear}><X size={14} /> Clear selection</button>
      </div>
      <dl className={styles.eventFacts}>
        <div><dt>Timestamp</dt><dd>{formatUtc(evidence.timestamp)}</dd></div>
        <div><dt>Severity</dt><dd><span className={`${styles.level} ${styles[`level_${evidence.level}`]}`}>{evidence.level}</span></dd></div>
        <div><dt>Service</dt><dd>{evidence.service}</dd></div>
        <div><dt>Entity</dt><dd>{evidence.entity.kind}: {evidence.entity.id}</dd></div>
        <div><dt>Template</dt><dd>{evidence.templateId}</dd></div>
        <div><dt>Source</dt><dd>{evidence.source.file}:{evidence.source.line}</dd></div>
        <div><dt>Redacted</dt><dd>{evidence.redacted ? "Yes" : "No"}</dd></div>
      </dl>
      <div className={styles.inspectorBlock}><span>Message</span><p>{evidence.message}</p></div>
      <div className={styles.inspectorBlock}><span>Why relevant</span><p>{evidence.correlationBasis}</p></div>
      <details className={styles.details} open>
        <summary>Raw event</summary><pre>{evidence.raw}</pre>
      </details>
      <details className={styles.details}>
        <summary>Parsed fields</summary>
        <dl className={styles.fields}>{Object.entries(evidence.fields).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
      </details>
    </section>
  );
}

export function EvidenceBrowser({ investigation, view, selectedEvidenceId, templateId, service, onViewChange, onSelectEvidence, onSelectTemplate, onSelectService }: EvidenceBrowserProps) {
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState<LogEvidence["level"] | "all">("all");
  const services = useMemo(() => [...new Set(investigation.evidence.map((item) => item.service))].sort(), [investigation.evidence]);
  const selectedEvidence = investigation.evidence.find((item) => item.id === selectedEvidenceId);
  const boundedEvidence = useMemo(() => [...investigation.evidence]
    .filter((item) => !service || item.service === service)
    .filter((item) => !templateId || item.templateId === templateId)
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp)), [investigation.evidence, service, templateId]);
  const filteredEvidence = useMemo(() => {
    const search = query.trim().toLowerCase();
    return boundedEvidence.filter((item) => {
      const searchable = [item.id, item.message, item.raw, item.entity.kind, item.entity.id].join(" ").toLowerCase();
      return (level === "all" || item.level === level) && (!search || searchable.includes(search));
    });
  }, [boundedEvidence, level, query]);
  const templateCounts = useMemo(() => new Map(boundedEvidence.map((item) => [item.templateId, boundedEvidence.filter((candidate) => candidate.templateId === item.templateId).length])), [boundedEvidence]);

  function resetFilters() {
    setQuery("");
    setLevel("all");
    onSelectTemplate(null);
  }

  return (
    <section className={styles.browser} aria-label="Evidence browser">
      <header className={styles.header}>
        <div><span className={styles.kicker}>EVIDENCE BROWSER</span><h2>Source-backed event record</h2></div>
        <div className={styles.viewTabs} aria-label="Evidence views">
          {views.map((item) => <button type="button" key={item} aria-pressed={view === item} className={view === item ? styles.activeTab : ""} onClick={() => onViewChange(item)}>{item}</button>)}
        </div>
      </header>
      <Metadata investigation={investigation} />
      {(templateId || service) && <div className={styles.activeFilters} aria-label="Active evidence filters">
        {templateId && <span>Template: {templateId}</span>}
        {service && <span>Service: {service}</span>}
        <button type="button" onClick={resetFilters}><X size={13} /> Clear filters</button>
      </div>}

      {view === "timeline" && <section className={styles.timeline} aria-label="Evidence timeline">
        <p className={styles.note}>Events are correlated by entity/request and time. This timeline is not a causal graph.</p>
        {boundedEvidence.map((item) => <button type="button" key={item.id} className={`${styles.timelineEvent} ${selectedEvidenceId === item.id ? styles.selected : ""}`} onClick={() => onSelectEvidence(item.id)}>
          <time>{formatUtc(item.timestamp)}</time><span className={`${styles.dot} ${styles[`dot_${item.role}`]}`} aria-hidden="true" /><span className={styles.eventCopy}><span><span className={`${styles.level} ${styles[`level_${item.level}`]}`}>{item.level}</span> {item.service} · {item.role.replace("_", " ")}</span><strong>{item.message}</strong><small>{item.entity.kind}: {item.entity.id}</small></span>
        </button>)}
        {!boundedEvidence.length && <p className={styles.empty}>No matching events. <button type="button" onClick={resetFilters}>Reset filters</button></p>}
      </section>}

      {view === "logs" && <section className={styles.logs} aria-label="Log explorer">
        <div className={styles.controls}>
          <label className={styles.search}><Search size={15} /><span>Search logs</span><input name="evidence-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="message, raw event, ID, entity" /></label>
          <label>Severity<select name="evidence-severity" value={level} onChange={(event) => setLevel(event.target.value as LogEvidence["level"] | "all")}><option value="all">All severities</option>{levels.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <label>Service<select name="evidence-service" value={service ?? ""} onChange={(event) => onSelectService(event.target.value || null)}><option value="">All services</option>{services.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <button type="button" className={styles.reset} onClick={resetFilters}><Filter size={14} /> Reset</button>
        </div>
        <p className={styles.results} aria-live="polite">Showing {filteredEvidence.length} of {boundedEvidence.length} available bounded evidence records · coverage: {investigation.source.coverage}</p>
        {filteredEvidence.length ? <div className={styles.logList}>{filteredEvidence.map((item) => <button type="button" key={item.id} className={`${styles.logRow} ${selectedEvidenceId === item.id ? styles.selected : ""}`} onClick={() => onSelectEvidence(item.id)}><time>{formatUtc(item.timestamp)}</time><span className={`${styles.level} ${styles[`level_${item.level}`]}`}>{item.level}</span><span className={styles.logService}>{item.service}</span><code>{item.id}</code><pre>{item.raw}</pre></button>)}</div> : <p className={styles.empty}>No matching events. <button type="button" onClick={resetFilters}>Reset filters</button></p>}
      </section>}

      {view === "patterns" && <section className={styles.patterns} aria-label="Stable event templates">
        <p className={styles.note}>Template counts describe the currently bounded evidence only, not the full source dataset.</p>
        {investigation.templates.map((template) => {
          const count = templateCounts.get(template.id) ?? 0;
          const patternServices = [...new Set(boundedEvidence.filter((item) => item.templateId === template.id).map((item) => item.service))];
          return <button type="button" className={styles.pattern} key={template.id} onClick={() => onSelectTemplate(template.id)}><ListTree size={17} /><span><strong>{template.id}</strong><code>{template.pattern}</code><small>{count} bounded record{count === 1 ? "" : "s"} · {patternServices.join(", ") || "No matching service"}</small><small>Variables: {template.variables.length ? template.variables.join(", ") : "none"}</small></span></button>;
        })}
        {!investigation.templates.length && <p className={styles.empty}>No stable templates are available for this investigation.</p>}
      </section>}
      <Inspector evidence={selectedEvidence} selectedEvidenceId={selectedEvidenceId} onClear={() => onSelectEvidence(null)} />
    </section>
  );
}
