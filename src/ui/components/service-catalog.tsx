"use client";

import { ArrowUpRight, Server } from "lucide-react";
import { formatUtcMillis } from "@/lib/format-utc";
import type { ServiceSummary } from "@/lib/services-contract";
import styles from "./service-catalog.module.css";

function percent(rate: number | null) {
  return rate === null ? "—" : `${(rate * 100).toFixed(1)}%`;
}

function count(value: number) {
  return value.toLocaleString("en-US");
}

export function ServiceCatalog({
  dataset,
  services,
  loading,
  error,
  onOpenService,
}: {
  dataset: string;
  services: ServiceSummary[];
  loading: boolean;
  error: string;
  onOpenService: (service: string) => void;
}) {
  return (
    <section className={styles.catalog} aria-label="Observed OpenStack services">
      <div className={styles.heading}>
        <div>
          <span className={styles.kicker}><Server size={14} /> OBSERVED COMPONENTS</span>
          <h1>Services</h1>
          <p>Each row is a component name seen in finalized logs for this dataset. This is not a confirmed topology or health map.</p>
        </div>
      </div>
      {loading && <p role="status">Loading observed services…</p>}
      {error && <p className="data-notice error" role="alert">{error}</p>}
      {!loading && !error && !services.length && (
        <p className="data-notice">{dataset ? "No named services were observed in the current publication." : "Select a published dataset to inspect its services."}</p>
      )}
      {services.length > 0 && (
        <div className={`${styles.list} panel`}>
          <div className={styles.head} role="row">
            <span>Service</span><span>Events</span><span>Errors</span><span>Error rate</span><span>UTC window</span>
          </div>
          {services.map((item) => (
            <button type="button" className={styles.row} key={item.service} onClick={() => onOpenService(item.service)}>
              <span className={styles.name}><strong>{item.service}</strong><small>{item.httpLatencySampleCount ? `HTTP p95 ${item.httpP95Seconds === null ? "unavailable" : `${item.httpP95Seconds.toFixed(3)} s`}` : "No HTTP latency samples"}</small></span>
              <span>{count(item.eventCount)}</span>
              <span className={item.errorCount ? styles.errors : undefined}>{count(item.errorCount)}</span>
              <span>{percent(item.logErrorRate)}</span>
              <span className={styles.window}>{formatUtcMillis(item.firstEventTimeMs)} — {formatUtcMillis(item.lastEventTimeMs)}</span>
              <ArrowUpRight size={16} />
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
