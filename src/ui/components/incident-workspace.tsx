"use client";

import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Bell,
  Bot,
  Check,
  ChevronDown,
  CircleDot,
  Clock3,
  Database,
  Gauge,
  GitBranch,
  LayoutDashboard,
  Menu,
  MessageSquareText,
  PanelLeftClose,
  Search,
  Send,
  Server,
  Settings,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  X,
  Zap,
} from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import type { ChatReply, UiAction } from "@/lib/chat-contract";

type Message = {
  role: "user" | "assistant";
  content: string;
  actions?: UiAction[];
  localOnly?: boolean;
};
type RuntimeStatus = {
  aiConfigured: boolean;
  mcp: { configured: boolean; connected: boolean; tools: string[] };
};

const initialMessages: Message[] = [
  {
    role: "assistant",
    content:
      "Ask me what is happening in the system. When I find a useful incident, timeline, log set or service, I will attach a link that opens it in the workspace.",
    localOnly: true,
  },
];

const timeline = [
  { time: "11:41:52", service: "checkout-api", level: "warn", text: "p95 latency crossed 1.8s threshold", active: false },
  { time: "11:42:03", service: "payment-api", level: "error", text: "upstream request timed out after 3000ms", active: false },
  { time: "11:42:18", service: "postgres-primary", level: "critical", text: "remaining connection slots reserved", active: true },
  { time: "11:42:21", service: "payment-api", level: "error", text: "retry storm detected · 142 req/s", active: false },
  { time: "11:43:06", service: "checkout-api", level: "warn", text: "circuit breaker opened for payments", active: false },
];

const quickPrompts = [
  "Open demo incident",
  "Find active incidents",
  "What changed recently?",
];

const demoAction: UiAction = {
  kind: "open_incident",
  label: "Open incident",
  title: "INC-2048 · Checkout failures",
  description: "SEV-1 · 3 affected services · likely database connection exhaustion",
  targetId: "INC-2048",
};

export function IncidentWorkspace({ aiConfigured, mcpConfigured }: { aiConfigured: boolean; mcpConfigured: boolean }) {
  const [mobileNav, setMobileNav] = useState(false);
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [selectedView, setSelectedView] = useState<UiAction | null>(null);
  const [aiReady, setAiReady] = useState(aiConfigured);
  const [mcpReady, setMcpReady] = useState(false);
  const [statusChecked, setStatusChecked] = useState(false);
  const chatEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    let active = true;

    void fetch("/api/status", { cache: "no-store" })
      .then((response) => response.json() as Promise<RuntimeStatus>)
      .then((status) => {
        if (!active) return;
        setAiReady(status.aiConfigured);
        setMcpReady(status.mcp.connected);
      })
      .catch(() => {
        if (active) setMcpReady(false);
      })
      .finally(() => {
        if (active) setStatusChecked(true);
      });

    return () => {
      active = false;
    };
  }, []);

  async function sendMessage(text: string) {
    const content = text.trim();
    if (!content || sending) return;

    const nextMessages = [...messages, { role: "user" as const, content }];
    setMessages([...nextMessages, { role: "assistant", content: "" }]);
    setInput("");
    setSending(true);

    if (!aiReady && content === "Open demo incident") {
      await new Promise((resolve) => window.setTimeout(resolve, 450));
      setMessages([
        ...nextMessages,
        {
          role: "assistant",
          content: "I found one high-severity incident in the demo snapshot. Open it to inspect the evidence and likely cause.",
          actions: [demoAction],
        },
      ]);
      setSending(false);
      return;
    }

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: nextMessages
            .filter((message) => !message.localOnly)
            .map(({ role, content }) => ({ role, content })),
        }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { error?: string } | null;
        throw new Error(payload?.error ?? "The investigation request failed.");
      }

      const reply = (await response.json()) as ChatReply;
      setMessages([...nextMessages, { role: "assistant", content: reply.message, actions: reply.actions }]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Something went wrong.";
      setMessages([...nextMessages, { role: "assistant", content: `I couldn't run the investigation: ${message}` }]);
    } finally {
      setSending(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void sendMessage(input);
  }

  function openAction(action: UiAction) {
    setSelectedView(action);
    window.setTimeout(() => document.getElementById("incidents")?.scrollIntoView({ behavior: "smooth" }), 50);
  }

  return (
    <main className="app-shell">
      <aside className={`sidebar ${mobileNav ? "sidebar-open" : ""}`}>
        <div className="brand-row">
          <div className="brand-mark"><Activity size={19} /></div>
          <span>LOGREGATOR</span>
          <button className="icon-button nav-close" onClick={() => setMobileNav(false)} aria-label="Close navigation"><X size={18} /></button>
        </div>

        <nav className="primary-nav">
          <span className="nav-label">Workspace</span>
          <a className="nav-item" href="#overview"><LayoutDashboard size={18} /> Overview</a>
          <a className="nav-item active" href="#incidents"><AlertTriangle size={18} /> Incidents <span className="nav-count">{mcpReady ? "3" : "—"}</span></a>
          <a className="nav-item" href="#explorer"><TerminalSquare size={18} /> Log explorer</a>
          <a className="nav-item" href="#topology"><GitBranch size={18} /> Topology</a>
          <span className="nav-label second">Intelligence</span>
          <a className="nav-item" href="#copilot"><MessageSquareText size={18} /> AI copilot</a>
          <a className="nav-item" href="#patterns"><Sparkles size={18} /> Patterns</a>
        </nav>

        <div className="connection-card">
          <div className="connection-head"><Database size={17} /><span>Evidence source</span></div>
          <strong>{mcpReady ? "Observability MCP" : "Demo snapshot"}</strong>
          <div className={`connection-status ${mcpReady ? "" : "offline"}`}><i /> {mcpReady ? "Connected · read only" : statusChecked ? "MCP unavailable" : mcpConfigured ? "Checking MCP…" : "Add MCP_SERVER_URL"}</div>
        </div>

        <div className="sidebar-bottom">
          <button className="nav-item button-reset"><Settings size={18} /> Settings</button>
          <div className="operator"><div className="avatar">AZ</div><div><strong>Alex Zotov</strong><span>Incident commander</span></div><ChevronDown size={16} /></div>
        </div>
      </aside>

      {mobileNav && <button className="nav-scrim" onClick={() => setMobileNav(false)} aria-label="Close navigation" />}

      <section className="main-column">
        <header className="topbar">
          <button className="icon-button menu-button" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu size={20} /></button>
          <div className="breadcrumbs"><span>Workspace</span><b>/</b><strong>{selectedView?.targetId ?? "No selection"}</strong></div>
          <div className="top-actions">
            <label className="search-box"><Search size={17} /><input placeholder="Search logs, traces, services…" /><kbd>⌘ K</kbd></label>
            <button className="icon-button has-notification" aria-label="Notifications"><Bell size={18} /></button>
            <button className={`status-pill ${mcpReady ? "" : "preview"}`}><i /> {mcpReady ? "Live" : "Preview"}</button>
          </div>
        </header>

        <div className="workspace">
          {selectedView?.targetId === "INC-2048" ? (
          <section className="incident-column" id="incidents">
            <div className="incident-heading">
              <div>
                <div className="eyebrow"><span className="severity-dot" /> SEV-1 · ACTIVE INCIDENT</div>
                <h1>Checkout failures in production</h1>
                <p>Elevated error rate and latency across the checkout flow.</p>
              </div>
              <button className="secondary-button"><Clock3 size={16} /> Last 30 minutes <ChevronDown size={15} /></button>
            </div>

            <div className="metrics-grid">
              <Metric icon={<Gauge size={18} />} label="Error rate" value="18.4%" delta="+16.2%" tone="red" spark={[8, 10, 9, 13, 15, 25, 30, 54, 48, 72, 68]} />
              <Metric icon={<Activity size={18} />} label="p95 latency" value="2.8s" delta="+1.9s" tone="amber" spark={[12, 15, 14, 16, 15, 20, 17, 24, 38, 62, 68]} />
              <Metric icon={<Server size={18} />} label="Affected services" value="3" delta="of 12" tone="blue" spark={[10, 10, 10, 12, 12, 12, 28, 28, 30, 30, 30]} />
              <Metric icon={<Zap size={18} />} label="Anomalies" value="7" delta="4 critical" tone="violet" spark={[6, 8, 7, 10, 9, 16, 13, 38, 25, 58, 48]} />
            </div>

            <section className="panel cause-panel">
              <div className="panel-title-row">
                <div><span className="panel-kicker"><Sparkles size={14} /> AI ROOT CAUSE</span><h2>Database connection pool exhausted</h2></div>
                <div className="confidence"><span>Confidence</span><strong>87%</strong></div>
              </div>
              <p className="cause-copy">A burst of payment retries consumed all available PostgreSQL connections. Checkout requests then queued until their upstream timeout expired.</p>
              <div className="evidence-summary">
                <div><span>Trigger</span><strong>Payment retry storm</strong></div>
                <div><span>First observed</span><strong>11:42:18 UTC</strong></div>
                <div><span>Blast radius</span><strong>Checkout · Payments</strong></div>
              </div>
              <div className="cause-actions">
                <button className="primary-button">View full analysis <ArrowUpRight size={16} /></button>
                <span><ShieldCheck size={16} /> Grounded in 14 evidence items</span>
              </div>
            </section>

            <section className="panel timeline-panel">
              <div className="panel-title-row compact"><div><span className="panel-kicker">EVIDENCE TIMELINE</span><h2>Correlated sequence</h2></div><button className="text-button">Open in log explorer <ArrowUpRight size={15} /></button></div>
              <div className="timeline">
                {timeline.map((item) => (
                  <div className={`timeline-row ${item.active ? "is-critical" : ""}`} key={item.time}>
                    <time>{item.time}</time><div className="timeline-track"><i /></div>
                    <div className="event-copy"><div><span className={`level level-${item.level}`}>{item.level}</span><strong>{item.service}</strong></div><p>{item.text}</p></div>
                    {item.active && <span className="root-badge"><CircleDot size={13} /> likely cause</span>}
                  </div>
                ))}
              </div>
            </section>

            <section className="panel recommendation-panel">
              <div className="recommend-icon"><Check size={18} /></div>
              <div><span className="panel-kicker">RECOMMENDED NEXT ACTION</span><h3>Reduce payment retry concurrency and raise the pool limit temporarily.</h3><p>Then compare connection wait time and checkout error rate for five minutes.</p></div>
              <button className="secondary-button">Open runbook <ArrowUpRight size={15} /></button>
            </section>
          </section>
          ) : selectedView ? (
            <section className="incident-column empty-workspace" id="incidents">
              <div className="empty-heading">
                <div><span className="panel-kicker">AI RESULT · {selectedView.kind.replaceAll("_", " ")}</span><h1>{selectedView.title}</h1><p>{selectedView.description}</p></div>
                <button className="secondary-button"><Clock3 size={16} /> Current result</button>
              </div>
              <div className="empty-canvas result-placeholder">
                <div className="empty-orbit"><Database size={23} /></div>
                <h2>View reference resolved</h2>
                <p>The UI received <code>{selectedView.targetId}</code> from the AI. Connect the application data adapter to render the matching records here.</p>
                <span className="resolved-reference"><Check size={15} /> Typed action handled by the workspace</span>
              </div>
            </section>
          ) : (
            <section className="incident-column empty-workspace" id="incidents">
              <div className="empty-heading">
                <div><span className="panel-kicker">INVESTIGATION WORKSPACE</span><h1>No incident selected</h1><p>Ask the copilot to investigate your system, then open one of its results here.</p></div>
                <button className="secondary-button"><Clock3 size={16} /> Last 30 minutes <ChevronDown size={15} /></button>
              </div>
              <div className="empty-metrics">
                {["Error rate", "p95 latency", "Affected services", "Anomalies"].map((label) => <div className="empty-metric" key={label}><span>{label}</span><strong>—</strong></div>)}
              </div>
              <div className="empty-canvas">
                <div className="empty-orbit"><Sparkles size={23} /></div>
                <h2>Start in the incident copilot</h2>
                <p>Ask a question in natural language. Verified results will appear as links in the conversation and open in this workspace.</p>
                <button className="primary-button" onClick={() => void sendMessage("Open demo incident")} disabled={sending}>Try the demo incident <ArrowUpRight size={16} /></button>
                <div className="empty-capabilities">
                  <span><AlertTriangle size={14} /> Incidents</span><span><TerminalSquare size={14} /> Logs</span><span><GitBranch size={14} /> Timelines</span><span><Server size={14} /> Services</span>
                </div>
              </div>
            </section>
          )}

          <aside className="copilot" id="copilot">
            <div className="copilot-header">
              <div className="copilot-icon"><Bot size={19} /></div><div><strong>Incident copilot</strong><span className={mcpReady ? "" : "offline"}><i /> {mcpReady ? "Evidence connected" : "Demo mode"}</span></div>
              <button className="icon-button" aria-label="Collapse copilot"><PanelLeftClose size={18} /></button>
            </div>
            <div className={`context-chip ${selectedView ? "" : "context-empty"}`}><AlertTriangle size={14} /><span>Context</span><strong>{selectedView?.targetId ?? "No active view"}</strong></div>
            <div className="messages">
              {messages.map((message, index) => (
                <div className={`message ${message.role}`} key={`${message.role}-${index}`}>
                  {message.role === "assistant" && <div className="message-avatar"><Sparkles size={14} /></div>}
                  <div className="bubble">
                    {message.content || <span className="typing"><i /><i /><i /></span>}
                    {message.role === "assistant" && message.content && index === 0 && <div className="mini-evidence"><Database size={14} /><span>{mcpReady ? "MCP ready" : "Demo context only"}</span></div>}
                    {message.actions?.map((action) => (
                      <button className="ui-action-card" key={`${action.kind}-${action.targetId}`} onClick={() => openAction(action)}>
                        <span className="ui-action-icon">{action.kind === "open_incident" ? <AlertTriangle size={15} /> : action.kind === "show_service" ? <Server size={15} /> : <TerminalSquare size={15} />}</span>
                        <span className="ui-action-copy"><strong>{action.title}</strong><small>{action.description}</small><b>{action.label} <ArrowUpRight size={13} /></b></span>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
              <div ref={chatEnd} />
            </div>
            <div className="prompt-list">
              {quickPrompts.map((prompt) => <button key={prompt} onClick={() => void sendMessage(prompt)} disabled={sending}>{prompt}<ArrowUpRight size={14} /></button>)}
            </div>
            <form className="composer" onSubmit={submit}>
              <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} placeholder="Ask about this incident…" rows={2} />
              <div><span>{mcpReady ? "MCP tools enabled" : aiReady ? "AI ready · MCP unavailable" : "Add server environment variables"}</span><button type="submit" disabled={sending || !input.trim()} aria-label="Send message"><Send size={16} /></button></div>
            </form>
            <p className="copilot-note">AI can make mistakes. Verify actions against the linked evidence.</p>
          </aside>
        </div>
      </section>
    </main>
  );
}

function Metric({ icon, label, value, delta, tone, spark }: { icon: React.ReactNode; label: string; value: string; delta: string; tone: string; spark: number[] }) {
  const points = spark.map((height, index) => `${index * 10},${76 - height}`).join(" ");
  return (
    <article className="metric-card">
      <div className={`metric-icon ${tone}`}>{icon}</div><span className="metric-label">{label}</span>
      <div className="metric-value"><strong>{value}</strong><span>{delta}</span></div>
      <svg className={`sparkline ${tone}`} viewBox="0 0 100 80" preserveAspectRatio="none" aria-hidden="true"><polyline points={points} /></svg>
    </article>
  );
}
