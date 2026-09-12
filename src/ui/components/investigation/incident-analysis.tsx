"use client";

import { AlertTriangle, FileWarning, FlaskConical, ListChecks, SearchCheck } from "lucide-react";
import type { Investigation } from "@/lib/investigation-contract";
import styles from "./analysis.module.css";

type IncidentAnalysisProps = {
  investigation: Investigation;
  onOpenEvidence: (evidenceId: string) => void;
};

const statusLabels: Record<Investigation["status"], string> = {
  investigating: "Investigating",
  insufficient_evidence: "Insufficient evidence",
  resolved: "Resolved",
};

function EvidenceLinks({
  evidenceIds,
  evidenceIdSet,
  onOpenEvidence,
}: {
  evidenceIds: string[];
  evidenceIdSet: Set<string>;
  onOpenEvidence: (evidenceId: string) => void;
}) {
  if (evidenceIds.length === 0) {
    return <p className={styles.emptyInline}>No linked evidence.</p>;
  }

  return (
    <div className={styles.evidenceLinks}>
      {evidenceIds.map((evidenceId) => {
        const available = evidenceIdSet.has(evidenceId);
        return available ? (
          <button
            className={styles.evidenceLink}
            key={evidenceId}
            onClick={() => onOpenEvidence(evidenceId)}
            type="button"
            aria-label={`Open evidence ${evidenceId}`}
          >
            {evidenceId}
          </button>
        ) : (
          <span className={styles.unavailableEvidence} key={evidenceId} title="This evidence is unavailable in this investigation.">
            {evidenceId} unavailable
          </span>
        );
      })}
    </div>
  );
}

function formatMetric(value: number, unit: string) {
  return `${value} ${unit}`;
}

export function IncidentAnalysis({ investigation, onOpenEvidence }: IncidentAnalysisProps) {
  const evidenceIdSet = new Set(investigation.evidence.map((evidence) => evidence.id));
  const hypotheses = [...investigation.hypotheses].sort((left, right) => left.rank - right.rank);

  return (
    <section className={styles.analysis} aria-label="Incident analysis">
      <header className={styles.summary}>
        <div className={styles.summaryHeader}>
          <div className={styles.summaryTitle}>
            <div className={styles.kicker}><AlertTriangle size={14} /> Incident analysis</div>
            <h1>{investigation.title}</h1>
            <p>{investigation.summary}</p>
          </div>
          <div className={`${styles.status} ${styles[`status_${investigation.status}`]}`}>
            {statusLabels[investigation.status]}
          </div>
        </div>
        <dl className={styles.metadata}>
          <div><dt>Source / dataset</dt><dd>{investigation.source.dataset}</dd></div>
          <div><dt>Interval (UTC)</dt><dd>{investigation.source.start} — {investigation.source.end}</dd></div>
          <div><dt>Coverage</dt><dd>{investigation.source.coverage}</dd></div>
          <div><dt>Entities</dt><dd>{investigation.entities.length ? investigation.entities.join(", ") : "No entities identified"}</dd></div>
        </dl>
        <p className={styles.sourceNote}>
          {investigation.source.mode === "synthetic" && <span className={styles.syntheticBadge}>Synthetic fixture</span>}
          {investigation.source.queryDescription}
        </p>
      </header>

      <section className={styles.section} aria-labelledby="findings-heading">
        <div className={styles.sectionHeading}><SearchCheck size={17} /><div><span>Observed finding</span><h2 id="findings-heading">Anomalies</h2></div></div>
        {investigation.anomalies.length === 0 ? (
          <p className={styles.emptyState}>No anomaly findings are available for this investigation.</p>
        ) : investigation.anomalies.map((finding) => (
          <article className={styles.card} key={finding.id}>
            <span className={styles.id}>{finding.id}</span>
            <h3>{finding.title}</h3>
            <dl className={styles.findingDetails}>
              <div><dt>Class</dt><dd>{finding.anomalyClass}</dd></div>
              <div><dt>Rule / method</dt><dd>{finding.method}</dd></div>
            </dl>
            <p>{finding.explanation}</p>
            <div className={styles.measurement}>
              <div><span>Observed</span><strong>{finding.observed === null ? "Not available" : formatMetric(finding.observed, finding.unit)}</strong></div>
              <div><span>Baseline</span><strong>{finding.baseline === null ? "Not available" : formatMetric(finding.baseline, finding.unit)}</strong></div>
              <div><span>Baseline interval</span><strong>{finding.baselineWindow ? `${finding.baselineWindow.start} — ${finding.baselineWindow.end}` : "Not available"}</strong></div>
              <div><span>Threshold</span><strong>{finding.threshold || "Not specified"}</strong></div>
            </div>
            <div className={styles.evidenceGroup}><span>Evidence</span><EvidenceLinks evidenceIds={finding.evidenceIds} evidenceIdSet={evidenceIdSet} onOpenEvidence={onOpenEvidence} /></div>
          </article>
        ))}
      </section>

      <section className={styles.section} aria-labelledby="hypotheses-heading">
        <div className={styles.sectionHeading}><FlaskConical size={17} /><div><span>Cause hypotheses</span><h2 id="hypotheses-heading">Ranked for investigation</h2></div></div>
        {investigation.status === "insufficient_evidence" && <p className={styles.caution}>The initiating cause is not established. These are hypotheses to test, not conclusions.</p>}
        {hypotheses.length === 0 ? (
          <p className={styles.emptyState}>No root-cause hypotheses are available yet.</p>
        ) : hypotheses.map((hypothesis, index) => (
          <details className={styles.hypothesis} key={hypothesis.id} open={index === 0}>
            <summary>
              <span className={styles.rank}>#{hypothesis.rank}</span>
              <h3 className={styles.hypothesisTitle}><span>{hypothesis.title}</span><small>{hypothesis.status.replaceAll("_", " ")} · {hypothesis.confidence} confidence</small></h3>
            </summary>
            <div className={styles.hypothesisBody}>
              <p>{hypothesis.reasoning}</p>
              <p className={styles.confidenceReason}><b>Confidence rationale:</b> {hypothesis.confidenceReason}</p>
              <div className={styles.evidenceColumns}>
                <div><h4>Supporting evidence</h4><EvidenceLinks evidenceIds={hypothesis.supportingEvidenceIds} evidenceIdSet={evidenceIdSet} onOpenEvidence={onOpenEvidence} /></div>
                <div><h4>Contradicting evidence</h4><EvidenceLinks evidenceIds={hypothesis.contradictingEvidenceIds} evidenceIdSet={evidenceIdSet} onOpenEvidence={onOpenEvidence} /></div>
              </div>
              <div className={styles.missingEvidence}><h4>Still needed</h4>{hypothesis.missingEvidence.length ? <ul>{hypothesis.missingEvidence.map((item) => <li key={item}>{item}</li>)}</ul> : <p className={styles.emptyInline}>No missing evidence was recorded.</p>}</div>
            </div>
          </details>
        ))}
      </section>

      <section className={styles.section} aria-labelledby="checks-heading">
        <div className={styles.sectionHeading}><ListChecks size={17} /><div><span>Safe next steps</span><h2 id="checks-heading">Checks to refine the investigation</h2></div></div>
        {investigation.nextChecks.length === 0 ? (
          <p className={styles.emptyState}>No follow-up checks have been defined for this investigation.</p>
        ) : <div className={styles.checkList}>{investigation.nextChecks.map((check) => (
          <article className={styles.check} key={check.id}><span className={styles.id}>{check.id}</span><h3>{check.title}</h3><p>{check.description}</p><div><h4>Expected result</h4><p>{check.expectedResult}</p></div><div className={styles.evidenceGroup}><span>Related evidence</span><EvidenceLinks evidenceIds={check.evidenceIds} evidenceIdSet={evidenceIdSet} onOpenEvidence={onOpenEvidence} /></div></article>
        ))}</div>}
      </section>

      <aside className={styles.limitations} aria-labelledby="limitations-heading">
        <FileWarning size={18} /><div><span>Limitations</span><h2 id="limitations-heading">What this analysis cannot establish</h2>{investigation.limitations.length ? <ul>{investigation.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul> : <p>No limitations were provided with this investigation.</p>}</div>
      </aside>
    </section>
  );
}
