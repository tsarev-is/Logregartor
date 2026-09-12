"use client";

import { Activity, AlertTriangle, ArrowUpRight, Bot, Database, Menu, MessageSquareText, Send, Server, Sparkles, TerminalSquare, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { ChatReplySchema, type UiAction } from "@/lib/chat-contract";
import { LiveLogExplorer } from "@/components/live-log-explorer";
import { ServiceCatalog } from "@/components/service-catalog";
import { formatUtc } from "@/lib/format-utc";
import { isServiceSummaryList, type ServiceSummary } from "@/lib/services-contract";
import {
  DatasetsSchema, EvidenceSchema, IncidentSchema, ReportSchema, TimelineSchema, snapshotQuery,
  type AnalysisReport, type Dataset, type Evidence, type Incident, type Timeline,
} from "@/lib/analytics-contract";

type MainView = "incidents" | "services" | "logs";

type Message = { role: "user" | "assistant"; content: string; actions?: UiAction[]; localOnly?: boolean };
type EventReference = { id: string; run: string; dataset: string };
const initialMessages: Message[] = [{
  role: "assistant", localOnly: true,
  content: "Select a published incident to inspect its evidence. Ask me to explain the observation, identify missing evidence or suggest the next check.",
}];
const quickPrompts = ["Explain the selected incident", "Which evidence is missing?", "What should I check next?"];

async function readApi(path: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(`/api/analytics/${path}`, { cache: "no-store", signal });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail ?? "Unable to load published evidence.");
  return body;
}
function failure(error: unknown) { return error instanceof Error ? error.message : "Unable to load data."; }
function seconds(value: number) { return `${Number(value.toFixed(3))} s`; }
function short(id: string) { return id.slice(0, 12); }

export function IncidentWorkspace({ aiConfigured, mcpConfigured }: { aiConfigured: boolean; mcpConfigured: boolean }) {
  const [mobileNav, setMobileNav] = useState(false);
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [aiReady, setAiReady] = useState(aiConfigured);
  const [mcpReady, setMcpReady] = useState(false);
  const [mainView, setMainView] = useState<MainView>("incidents");
  const [logQuery, setLogQuery] = useState("");
  const [logComponent, setLogComponent] = useState("");
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [dataset, setDataset] = useState("");
  const [services, setServices] = useState<ServiceSummary[]>([]);
  const [servicesError, setServicesError] = useState("");
  const [servicesLoading, setServicesLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [discoveryError, setDiscoveryError] = useState("");
  const [discovering, setDiscovering] = useState(true);
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [reportError, setReportError] = useState("");
  const [reportLoading, setReportLoading] = useState(false);
  const [selectedView, setSelectedView] = useState<UiAction | null>(null);
  const [card, setCard] = useState<Incident | null>(null);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [detailError, setDetailError] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [eventReference, setEventReference] = useState<EventReference | null>(null);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [evidenceError, setEvidenceError] = useState("");
  const chatEnd = useRef<HTMLDivElement>(null);

  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/status", { cache: "no-store", signal: controller.signal }).then((response) => response.json()).then((status) => {
      setAiReady(status.aiConfigured);
      setMcpReady(status.mcp.connected);
    }).catch(() => undefined);
    return () => controller.abort();
  }, [refresh]);

  useEffect(() => {
    const controller = new AbortController();
    setDiscovering(true);
    setDiscoveryError("");
    void readApi("datasets", controller.signal).then((body) => {
      const result = DatasetsSchema.parse(body).datasets;
      if (controller.signal.aborted) return;
      setDatasets(result);
      setDataset((current) => current || result[0]?.dataset_id || "");
    }).catch((error) => { if (!controller.signal.aborted) setDiscoveryError(failure(error)); })
      .finally(() => { if (!controller.signal.aborted) setDiscovering(false); });
    return () => controller.abort();
  }, [refresh]);

  useEffect(() => {
    const controller = new AbortController();
    setReport(null);
    setReportError("");
    if (!dataset) return;
    setReportLoading(true);
    void readApi(`incidents?${new URLSearchParams({ dataset_id: dataset })}`, controller.signal).then((body) => {
      const result = ReportSchema.parse(body);
      if (result.dataset_id !== dataset) throw new Error("Unexpected dataset in Analytics response.");
      if (!controller.signal.aborted) setReport(result);
    }).catch((error) => { if (!controller.signal.aborted) setReportError(failure(error)); })
      .finally(() => { if (!controller.signal.aborted) setReportLoading(false); });
    return () => controller.abort();
  }, [dataset, refresh]);

  useEffect(() => {
    const controller = new AbortController();
    setServices([]);
    setServicesError("");
    if (!dataset) { setServicesLoading(false); return; }
    setServicesLoading(true);
    void fetch(`/api/services?${new URLSearchParams({ dataset })}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const body: unknown = await response.json().catch(() => null);
        if (!response.ok) {
          const message = body && typeof body === "object" && "error" in body && typeof body.error === "string" ? body.error : "Unable to load observed services.";
          throw new Error(message);
        }
        if (!isServiceSummaryList(body)) throw new Error("The services API returned an invalid response.");
        if (!controller.signal.aborted) setServices(body);
      })
      .catch((error) => { if (!controller.signal.aborted) setServicesError(failure(error)); })
      .finally(() => { if (!controller.signal.aborted) setServicesLoading(false); });
    return () => controller.abort();
  }, [dataset, refresh]);

  useEffect(() => {
    const controller = new AbortController();
    setCard(null); setTimeline(null); setDetailError("");
    if (!selectedView || selectedView.kind === "show_logs") { setDetailLoading(false); return; }
    const action = selectedView;
    setDetailLoading(true);
    const path = `incidents/${action.targetId}`;
    const query = snapshotQuery(action.analysisRunId);
    void Promise.all([
      readApi(`${path}?${query}`, controller.signal),
      readApi(`${path}/timeline?${query}`, controller.signal),
    ]).then(([cardBody, timelineBody]) => {
      const nextCard = IncidentSchema.parse(cardBody);
      const nextTimeline = TimelineSchema.parse(timelineBody);
      if (nextCard.dataset_id !== action.datasetId || nextCard.analysis_run_id !== action.analysisRunId ||
          nextCard.incident_id !== action.targetId || nextTimeline.incident_id !== action.targetId ||
          nextTimeline.analysis_run_id !== action.analysisRunId) throw new Error("Evidence snapshot does not match this incident.");
      if (!controller.signal.aborted) { setCard(nextCard); setTimeline(nextTimeline); }
    }).catch((error) => { if (!controller.signal.aborted) setDetailError(failure(error)); })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false); });
    return () => controller.abort();
  }, [selectedView, refresh]);

  useEffect(() => {
    const controller = new AbortController();
    setEvidence(null); setEvidenceError("");
    if (!eventReference) return;
    const ref = eventReference;
    void readApi(`events/${ref.id}?${snapshotQuery(ref.run)}`, controller.signal).then((body) => {
      const result = EvidenceSchema.parse(body);
      if (result.dataset_id !== ref.dataset || result.analysis_run_id !== ref.run || result.event_id !== ref.id) {
        throw new Error("Source record does not match the selected snapshot.");
      }
      if (!controller.signal.aborted) setEvidence(result);
    }).catch((error) => { if (!controller.signal.aborted) setEvidenceError(failure(error)); });
    return () => controller.abort();
  }, [eventReference, refresh]);

  useEffect(() => {
    if (mainView !== "incidents" || !timeline) return;
    document.getElementById(selectedView?.kind === "show_timeline" ? "timeline" : "incident-detail")?.scrollIntoView({ behavior: "smooth" });
  }, [timeline, selectedView, mainView]);
  useEffect(() => {
    if (mainView === "incidents" && evidence) document.getElementById("explorer")?.scrollIntoView({ behavior: "smooth" });
  }, [evidence, mainView]);

  const incidentServices = useMemo(() => {
    if (!timeline) return [];
    return [...new Set([...timeline.events, ...timeline.undated_events].map((event) => event.component).filter((value): value is string => Boolean(value)))].sort();
  }, [timeline]);

  function openIncidents() {
    setMainView("incidents");
    setMobileNav(false);
  }
  function openLogs(next?: { query?: string; component?: string }) {
    if (next) {
      setLogQuery(next.query ?? "");
      setLogComponent(next.component ?? "");
    }
    setMainView("logs");
    setMobileNav(false);
  }
  function openAction(action: UiAction) {
    setDataset(action.datasetId);
    setSelectedView(action);
    setEventReference(action.kind === "show_logs" ? { id: action.targetId, run: action.analysisRunId, dataset: action.datasetId } : null);
    setMainView("incidents");
    setMobileNav(false);
  }
  function openIncident(incident: Incident) {
    openAction({ kind: "open_incident", targetId: incident.incident_id, datasetId: incident.dataset_id,
      analysisRunId: incident.analysis_run_id, title: "Slow VM build", label: "Open incident",
      description: `Build completed in ${seconds(incident.observed_seconds)}, exceeding the ${seconds(incident.threshold_seconds)} threshold.` });
  }
  function openEvidence(id: string) {
    if (card) setEventReference({ id, run: card.analysis_run_id, dataset: card.dataset_id });
  }
  async function sendMessage(text: string) {
    const content = text.trim();
    if (!content || sending) return;
    const nextMessages: Message[] = [...messages, { role: "user", content }];
    setMessages([...nextMessages, { role: "assistant", content: "" }]);
    setInput(""); setSending(true);
    try {
      const response = await fetch("/api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: nextMessages.filter((message) => !message.localOnly).slice(-20).map(({ role, content }) => ({ role, content })),
          context: card ? { datasetId: card.dataset_id, incidentId: card.incident_id, analysisRunId: card.analysis_run_id } :
            evidence ? { datasetId: evidence.dataset_id, incidentId: null, eventId: evidence.event_id, analysisRunId: evidence.analysis_run_id } :
            report ? { datasetId: report.dataset_id, incidentId: null, analysisRunId: report.analysis_run_id } : undefined,
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error ?? body.detail ?? "Investigation failed.");
      const reply = ChatReplySchema.parse(body);
      setMessages([...nextMessages, { role: "assistant", content: reply.message, actions: reply.actions }]);
    } catch (error) {
      setMessages([...nextMessages, { role: "assistant", content: `I couldn't run the investigation: ${failure(error)}`, localOnly: true }]);
    } finally { setSending(false); }
  }
  function submit(event: FormEvent) { event.preventDefault(); void sendMessage(input); }
  const selectedDataset = datasets.find((item) => item.dataset_id === dataset);

  return (
    <main className="app-shell">
      <aside className={`sidebar ${mobileNav ? "sidebar-open" : ""}`}>
        <div className="brand-row"><div className="brand-mark"><Activity size={19} /></div><span>LOGREGATOR</span><button className="icon-button nav-close" onClick={() => setMobileNav(false)} aria-label="Close navigation"><X size={18} /></button></div>
        <nav className="primary-nav">
          <span className="nav-label">Workspace</span>
          <a className={`nav-item ${mainView === "incidents" ? "active" : ""}`} href="#incidents" onClick={openIncidents}><AlertTriangle size={18} /> Incidents <span className="nav-count">{report?.incidents.length ?? "—"}</span></a>
          <button type="button" className={`nav-item ${mainView === "services" ? "active" : ""}`} onClick={() => { setMainView("services"); setMobileNav(false); }}><Server size={18} /> Services <span className="nav-count">{services.length || "—"}</span></button>
          <a className="nav-item" href="#timeline" onClick={openIncidents}><Activity size={18} /> Evidence timeline</a>
          <a className="nav-item" href="#explorer" onClick={openIncidents}><TerminalSquare size={18} /> Source record</a>
          <button type="button" className={`nav-item ${mainView === "logs" ? "active" : ""}`} onClick={() => openLogs({ query: "", component: "" })}><Database size={18} /> Live logs</button>
          <a className="nav-item" href="#copilot"><MessageSquareText size={18} /> AI copilot</a>
        </nav>
        <div className="connection-card"><div className="connection-head"><Database size={17} /> Evidence source</div><strong>Analytics publications</strong><div className={`connection-status ${discoveryError ? "offline" : ""}`}><i /> {discovering ? "Checking data…" : discoveryError ? "Unavailable" : "Connected · read only"}</div></div>
      </aside>
      {mobileNav && <button className="nav-scrim" onClick={() => setMobileNav(false)} aria-label="Close navigation" />}
      <section className="main-column">
        <header className="topbar"><button className="icon-button menu-button" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu size={20} /></button><div className="breadcrumbs"><span>Workspace</span><b>/</b><strong>{mainView === "logs" ? logComponent || "Live logs" : mainView === "services" ? "Services" : dataset || "No dataset"}</strong></div><span className="status-pill preview">{mainView === "incidents" ? "Published snapshot" : "Read only"}</span></header>
        <div className="workspace">
          <section className="incident-column" id="incidents">
            {mainView === "logs" ? <LiveLogExplorer key={`${dataset}|${logQuery}|${logComponent}`} dataset={dataset} initialQuery={logQuery} initialComponent={logComponent} /> : mainView === "services" ? <>
            <div className="incident-heading"><label className="dataset-picker">Dataset <select value={dataset} onChange={(event) => { setDataset(event.target.value); setSelectedView(null); setEventReference(null); setLogQuery(""); setLogComponent(""); }} disabled={!datasets.length}>
              {!datasets.length && <option value="">No published datasets</option>}
              {dataset && !datasets.some((item) => item.dataset_id === dataset) && <option value={dataset}>{dataset}</option>}
              {datasets.map((item) => <option key={item.dataset_id} value={item.dataset_id}>{item.dataset_id}</option>)}
            </select></label><button className="secondary-button" onClick={() => setRefresh((value) => value + 1)} disabled={servicesLoading}>Refresh</button></div>
            <ServiceCatalog dataset={dataset} services={services} loading={servicesLoading} error={servicesError} onOpenService={(service) => openLogs({ component: service })} />
            </> : <>
            <div className="incident-heading"><div><span className="panel-kicker">OPENSTACK INVESTIGATION</span><h1>Slow VM builds</h1><p>Inspect completed builds, their stages and original evidence.</p></div><button className="secondary-button" onClick={() => setRefresh((value) => value + 1)} disabled={discovering || reportLoading}>Refresh</button></div>
            <label className="dataset-picker">Dataset <select value={dataset} onChange={(event) => { setDataset(event.target.value); setSelectedView(null); setEventReference(null); setLogQuery(""); setLogComponent(""); }} disabled={!datasets.length}>
              {!datasets.length && <option value="">No published datasets</option>}
              {dataset && !datasets.some((item) => item.dataset_id === dataset) && <option value={dataset}>{dataset}</option>}
              {datasets.map((item) => <option key={item.dataset_id} value={item.dataset_id}>{item.dataset_id}</option>)}
            </select></label>
            {discoveryError && <p className="data-notice error" role="alert">{discoveryError}</p>}
            {!discovering && !discoveryError && !datasets.length && <p className="data-notice">No data has been published. Import logs with LogParser, then run Analytics for the dataset.</p>}
            {selectedDataset?.analysis_stale && <p className="data-notice">LogParser has newer input. This analysis still shows its original snapshot; run Analytics again to include the new data.</p>}
            {reportLoading && <p role="status">Loading incidents…</p>}
            {reportError && <p className="data-notice error" role="alert">{reportError} {selectedDataset?.analysis_run_id === null && "Run Analytics for this dataset after importing logs."}</p>}
            {report && <>
              <div className="metrics-grid">{[["Incidents", report.incidents.length], ["Completed VMs", report.completed_instances], ["Incomplete VMs", report.incomplete_instances], ["Events analyzed", report.events_read]].map(([label, value]) => <article className="metric-card" key={label}><span className="metric-label">{label}</span><div className="metric-value"><strong>{value}</strong></div></article>)}</div>
              {!report.incidents.length ? <p className="data-notice">No builds exceeded {seconds(report.threshold_seconds)} in this publication.</p> :
                <div className="incident-list panel">{report.incidents.map((incident, index) => (
                  <button className={`incident-row ${card?.incident_id === incident.incident_id ? "selected" : ""}`} key={incident.incident_id} onClick={() => openIncident(incident)}>
                    <span className="incident-rank">{index + 1}</span>
                    <span className="incident-copy">
                      <strong>Slow VM build · {seconds(incident.observed_seconds)}</strong>
                      <span className="incident-summary">Build completed above the {seconds(incident.threshold_seconds)} threshold.</span>
                      <small>{incident.event_time ? formatUtc(incident.event_time) : "Time unavailable"}</small>
                      <small title={`VM: ${incident.instance_id}\nSource: ${incident.source_sha256}`}>VM {short(incident.instance_id)} · source {short(incident.source_sha256)}</small>
                    </span>
                    <span className="incident-duration">+{seconds(incident.excess_seconds)}<small>over threshold</small></span>
                    <ArrowUpRight size={16} />
                  </button>
                ))}</div>}
              <p className="snapshot-note">List snapshot: <code>{report.analysis_run_id}</code> · threshold {seconds(report.threshold_seconds)}</p>
            </>}
            {detailLoading && <p role="status">Loading incident evidence…</p>}
            {detailError && <p className="data-notice error" role="alert">{detailError}</p>}
            {card && timeline && <>
              <section className="panel cause-panel" id="incident-detail">
                <span className="panel-kicker">DETECTOR OBSERVATION · {card.detector}</span><h2>Build completed in {seconds(card.observed_seconds)}</h2>
                <p className="cause-copy">The build exceeded its {seconds(card.threshold_seconds)} threshold by {seconds(card.excess_seconds)}. The measured deviation does not establish a root cause.</p>
                <p className="identifier">VM: {card.instance_id}<br />Source: {card.source_sha256}<br />Analysis: {card.analysis_run_id}</p>
                {report && report.analysis_run_id !== card.analysis_run_id && <p className="data-notice">This card is pinned to an earlier publication. Its original evidence remains available.</p>}
                {card.baseline ? <p className="cause-copy">Reference: {card.baseline.completed_instances} completed VMs, {card.baseline.incomplete_instances} incomplete. Median {seconds(card.baseline.median_seconds)}, maximum {seconds(card.baseline.max_seconds)}, margin {seconds(card.baseline.margin_seconds)}.</p> : <p className="cause-copy">Explicit threshold; no reference baseline was supplied.</p>}
                {incidentServices.length > 0 && <div className="service-row" aria-label="Observed services in this evidence snapshot"><span>Observed services</span><div>{incidentServices.map((service) => <button type="button" className="service-chip" key={service} onClick={() => openLogs({ component: service, query: card.instance_id })}>{service}</button>)}</div></div>}
                <div className="stage-grid">{card.stages.map((stage) => <div className={`stage-card ${stage.found ? "" : "missing"}`} key={stage.name}><strong>{stage.name}</strong><span>{!stage.found ? "Missing" : stage.duration_seconds === null ? "Observed" : seconds(stage.duration_seconds)}</span>{stage.evidence_ids.map((id, index) => <button className="text-button" key={id} onClick={() => openEvidence(id)}>Evidence {index + 1} <ArrowUpRight size={12} /></button>)}</div>)}</div>
                <p className="snapshot-note">Build and spawn intervals overlap and are not added together.</p>
                <p className="data-notice">Evidence: {card.completeness.status}. {card.completeness.missing_stages.length > 0 && `Missing stages: ${card.completeness.missing_stages.join(", ")}. `}{card.completeness.undated_event_ids.length} undated records; {card.completeness.parse_issue_event_ids.length} records with parse issues.</p>
              </section>
              <section className="panel timeline-panel" id="timeline"><div className="panel-title-row"><div><span className="panel-kicker">EVIDENCE TIMELINE</span><h2>One VM, one source, one build</h2></div></div>
                <div className="evidence-timeline">{timeline.events.map((event) => <button className="evidence-row" key={event.event_id} onClick={() => openEvidence(event.event_id)}><time>{event.event_time}</time><strong>{event.component ?? "Unknown component"}</strong><span>{event.message}</span><small>Line {event.line_start} · {event.parse_status} · {short(event.event_id)}</small></button>)}</div>
                {timeline.undated_events.length > 0 && <><h3>Records without timestamps</h3>{timeline.undated_events.map((event) => <button className="evidence-row" key={event.event_id} onClick={() => openEvidence(event.event_id)}><span>{event.message}</span><small>Line {event.line_start} · {event.parse_status}</small></button>)}</>}
              </section>
            </>}
            <section id="explorer" className="panel source-panel"><span className="panel-kicker">ORIGINAL SOURCE RECORD</span>
              {!eventReference && <p>Select a stage reference or a timeline event to open its exact source record.</p>}
              {eventReference && !evidence && !evidenceError && <p role="status">Loading source record…</p>}
              {evidenceError && <p className="data-notice error" role="alert">{evidenceError}</p>}
              {evidence && <><p className="identifier">{evidence.source_file} · lines {evidence.line_start}–{evidence.line_end}<br />Event: {evidence.event_id}<br />Ingestion: {evidence.ingestion_run_id}<br />Analysis: {evidence.analysis_run_id}</p><pre className="raw-record">{evidence.raw_text + evidence.line_ending}</pre></>}
            </section>
            </>}
          </section>
          <aside className="copilot" id="copilot">
            <div className="copilot-header"><div className="copilot-icon"><Bot size={19} /></div><div><strong>Incident copilot</strong><span className={aiReady ? "" : "offline"}><i />{aiReady ? mcpReady ? "AI + MCP connected" : "AI configured" : "AI not configured"}</span></div></div>
            <div className="context-chip"><AlertTriangle size={14} /><span>Context</span><strong>{mainView === "logs" && logComponent ? logComponent : card ? `Slow build · ${seconds(card.observed_seconds)}` : dataset || "No dataset"}</strong></div>
            <div className="messages">{messages.map((message, index) => <div className={`message ${message.role}`} key={index}>{message.role === "assistant" && <div className="message-avatar"><Sparkles size={14} /></div>}<div className="bubble">{message.content || <span className="typing"><i /><i /><i /></span>}{message.actions?.map((action) => <button className="ui-action-card" key={`${action.kind}-${action.targetId}-${action.analysisRunId}`} onClick={() => openAction(action)}><span className="ui-action-icon"><ArrowUpRight size={15} /></span><span className="ui-action-copy"><strong>{action.title}</strong><small>{action.description}</small><b>{action.label}</b></span></button>)}</div></div>)}<div ref={chatEnd} /></div>
            <div className="prompt-list">{quickPrompts.map((prompt) => <button key={prompt} onClick={() => void sendMessage(prompt)} disabled={sending || !aiReady}>{prompt}<ArrowUpRight size={14} /></button>)}</div>
            <form className="composer" onSubmit={submit}><textarea aria-label="Investigation question" value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} placeholder="Ask about this incident…" rows={2} maxLength={10_000} /><div><span>{mcpReady ? "Read-only MCP tools enabled" : mcpConfigured ? "MCP unavailable" : "Selected Analytics context"}</span><button type="submit" disabled={sending || !input.trim() || !aiReady} aria-label="Send message"><Send size={16} /></button></div></form>
            <p className="copilot-note">Verify hypotheses against evidence. Published records remain accessible when AI is unavailable.</p>
          </aside>
        </div>
      </section>
    </main>
  );
}
