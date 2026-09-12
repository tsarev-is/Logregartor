import type { UiAction } from "@/lib/chat-contract";
import type { Investigation, InvestigationSelection } from "@/lib/investigation-contract";

/** Maps only IDs present in the supplied investigation; it never supplies a fallback. */
export function resolveInvestigationAction(
  action: UiAction,
  investigation: Investigation,
): InvestigationSelection | null {
  const base = { evidenceId: null, templateId: null, service: null };
  const evidence = investigation.evidence.find((item) => item.id === action.targetId);
  const template = investigation.templates.find((item) => item.id === action.targetId);
  const serviceExists = investigation.evidence.some((item) => item.service === action.targetId);

  // The fixture also recognizes legacy `show_service` references, although the
  // current live chat contract no longer emits them.
  const kind: string = action.kind;
  switch (kind) {
    case "open_incident":
      return action.targetId === investigation.id ? { view: "overview", ...base } : null;
    case "show_timeline":
      if (action.targetId === investigation.id) return { view: "timeline", ...base };
      return evidence ? { view: "timeline", ...base, evidenceId: evidence.id } : null;
    case "show_logs":
      if (action.targetId === investigation.id) return { view: "logs", ...base };
      if (evidence) return { view: "logs", ...base, evidenceId: evidence.id };
      return template ? { view: "logs", ...base, templateId: template.id } : null;
    case "show_service":
      return serviceExists ? { view: "logs", ...base, service: action.targetId } : null;
    default:
      return null;
  }
}
