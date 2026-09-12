"use client";

import { ChevronLeft, ChevronRight, Database, Filter, RefreshCw, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatUtcMillis } from "@/lib/format-utc";
import { isLiveLogsPage, type LiveLogEvent, type LiveLogsPage } from "@/lib/logs-contract";
import styles from "./live-log-explorer.module.css";

const PAGE_SIZE = 50;

function levelClass(level: string | null) {
  const normalized = (level ?? "unknown").toLowerCase();
  return `${styles.level} ${styles[`level_${normalized}`] ?? ""}`;
}

export function LiveLogExplorer({
  dataset,
  initialQuery = "",
  initialComponent = "",
}: {
  dataset: string;
  initialQuery?: string;
  initialComponent?: string;
}) {
  const [query, setQuery] = useState(initialQuery);
  const [debouncedQuery, setDebouncedQuery] = useState(initialQuery);
  const [level, setLevel] = useState("");
  const [source, setSource] = useState("");
  const [component, setComponent] = useState(initialComponent);
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<LiveLogsPage | null>(null);
  const [selected, setSelected] = useState<LiveLogEvent | null>(null);
  const [loading, setLoading] = useState(Boolean(dataset));
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setDebouncedQuery(query.trim());
      setOffset(0);
    }, 350);
    return () => window.clearTimeout(timeout);
  }, [query]);

  useEffect(() => {
    if (!dataset) {
      setPage(null);
      setLoading(false);
      setError(null);
      return;
    }
    const controller = new AbortController();
    const params = new URLSearchParams({ dataset, limit: String(PAGE_SIZE), offset: String(offset) });
    if (debouncedQuery) params.set("q", debouncedQuery);
    if (level) params.set("level", level);
    if (source) params.set("source", source);
    if (component) params.set("component", component);
    setLoading(true);
    setError(null);
    void fetch(`/api/logs?${params}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const payload: unknown = await response.json().catch(() => null);
        if (!response.ok) {
          const message = payload && typeof payload === "object" && "error" in payload && typeof payload.error === "string" ? payload.error : "The log query failed.";
          throw new Error(message);
        }
        if (!isLiveLogsPage(payload)) throw new Error("The log API returned an invalid response.");
        setPage(payload);
        setSelected((current) => current && payload.events.some((event) => event.eventId === current.eventId) ? current : null);
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "The log query failed.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [dataset, debouncedQuery, level, source, component, offset, refreshToken]);

  const range = useMemo(() => {
    if (!page || page.total === 0) return "0 events";
    return `${page.offset + 1}–${Math.min(page.offset + page.events.length, page.total)} of ${page.total.toLocaleString("en-US")}`;
  }, [page]);

  function applyService(service: string) {
    setComponent(service);
    setOffset(0);
  }

  function reset() {
    setQuery("");
    setDebouncedQuery("");
    setLevel("");
    setSource("");
    setComponent("");
    setOffset(0);
    setSelected(null);
  }

  return (
    <section className={styles.explorer} aria-label="Live ClickHouse log explorer">
      <header className={styles.header}>
        <div>
          <span className={styles.kicker}><Database size={14} /> LIVE CLICKHOUSE</span>
          <h1>OpenStack log explorer</h1>
          <p>Finalized events from the <code>logs.log_events</code> view. Service is the observed OpenStack component, not a topology node.</p>
        </div>
        <button type="button" className={styles.refresh} onClick={() => setRefreshToken((value) => value + 1)} disabled={loading || !dataset}>
          <RefreshCw size={15} /> Refresh
        </button>
      </header>

      <div className={styles.controls}>
        <label className={styles.search}>
          <span>Search real logs</span>
          <div><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="message, event, request, instance or service" /></div>
        </label>
        <label><span>Severity</span><select value={level} onChange={(event) => { setLevel(event.target.value); setOffset(0); }}><option value="">All severities</option>{page?.facets.levels.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
        <label><span>Service</span><select value={component} onChange={(event) => applyService(event.target.value)}><option value="">All services</option>{page?.facets.components.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
        <label><span>Source</span><select value={source} onChange={(event) => { setSource(event.target.value); setOffset(0); }}><option value="">All source files</option>{page?.facets.sources.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
        <button type="button" className={styles.reset} onClick={reset}><Filter size={14} /> Reset</button>
      </div>

      <div className={styles.status} aria-live="polite">
        <span>{!dataset ? "Select a dataset to query logs." : loading ? "Loading ClickHouse events…" : error ? "Log query failed" : range}</span>
        {page && <span>Dataset: <strong>{page.dataset}</strong>{component ? <> · service <strong>{component}</strong></> : null} · page size {page.limit}</span>}
      </div>

      {!dataset && <section className={styles.empty}><h2>No dataset selected</h2><p>Choose a published dataset before opening live service logs.</p></section>}
      {error && <section className={styles.error} role="alert"><strong>Unable to read ClickHouse logs</strong><p>{error}</p><button type="button" onClick={() => setRefreshToken((value) => value + 1)}>Try again</button></section>}
      {!error && !loading && page?.events.length === 0 && <section className={styles.empty}><h2>No matching events</h2><p>Change the search text or service filters.</p><button type="button" onClick={reset}>Reset filters</button></section>}

      {!error && page && page.events.length > 0 && <>
        <div className={styles.table} role="table" aria-label="Real OpenStack log events">
          <div className={styles.tableHead} role="row"><span>UTC timestamp</span><span>Level</span><span>Service</span><span>Source</span><span>Message</span></div>
          {page.events.map((event) => <button type="button" role="row" aria-selected={selected?.eventId === event.eventId} className={`${styles.row} ${selected?.eventId === event.eventId ? styles.selected : ""}`} key={event.eventId} onClick={() => setSelected(event)}>
            <time>{formatUtcMillis(event.timestampMs)}</time>
            <span className={levelClass(event.level)}>{event.level ?? "—"}</span>
            <span className={styles.component}>{event.component ?? "—"}</span>
            <span className={styles.source}>{event.sourceFile}:{event.lineStart}</span>
            <span className={styles.message}>{event.message || "(empty message)"}</span>
          </button>)}
        </div>
        <nav className={styles.pagination} aria-label="Log result pages">
          <button type="button" onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))} disabled={loading || offset === 0}><ChevronLeft size={15} /> Previous</button>
          <span>{range}</span>
          <button type="button" onClick={() => setOffset((value) => value + PAGE_SIZE)} disabled={loading || offset + page.events.length >= page.total}>Next <ChevronRight size={15} /></button>
        </nav>
      </>}

      {selected && <section className={styles.inspector} aria-label={`Raw log event ${selected.eventId}`}>
        <div className={styles.inspectorHead}><div><span className={styles.kicker}>RAW DATABASE EVENT</span><h2>{selected.eventId}</h2></div><button type="button" onClick={() => setSelected(null)}><X size={14} /> Close</button></div>
        <dl>
          <div><dt>Timestamp</dt><dd>{formatUtcMillis(selected.timestampMs)}</dd></div>
          <div><dt>Source</dt><dd>{selected.sourceFile}:{selected.lineStart}</dd></div>
          <div><dt>Service</dt><dd>{selected.component ?? "—"}{selected.component && selected.component !== component && <button type="button" className={styles.textAction} onClick={() => applyService(selected.component!)}>Filter to this service</button>}</dd></div>
          <div><dt>Level</dt><dd>{selected.level ?? "—"}</dd></div>
          <div><dt>Request ID</dt><dd>{selected.requestId ?? "—"}</dd></div>
          <div><dt>Instance ID</dt><dd>{selected.instanceId ?? "—"}</dd></div>
          <div><dt>Template ID</dt><dd>{selected.templateId ?? "—"}</dd></div>
          <div><dt>Parse/template</dt><dd>{selected.parseStatus} / {selected.templateStatus}</dd></div>
        </dl>
        <details open><summary>Raw event</summary><pre>{selected.rawText}</pre></details>
      </section>}
    </section>
  );
}
