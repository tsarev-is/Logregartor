export const UI_ACTION_KINDS = ["open_incident", "show_timeline", "show_logs", "show_service"] as const;

export type UiActionKind = (typeof UI_ACTION_KINDS)[number];

export type UiAction = {
  kind: UiActionKind;
  label: string;
  title: string;
  description: string;
  targetId: string;
};

export type ChatReply = {
  message: string;
  actions: UiAction[];
};

export const CHAT_REPLY_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    message: {
      type: "string",
      description: "Concise operator-facing answer in the user's language.",
    },
    actions: {
      type: "array",
      maxItems: 3,
      description: "Typed UI links backed by identifiers found in tools. Empty when no verified target exists.",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          kind: { type: "string", enum: UI_ACTION_KINDS },
          label: { type: "string" },
          title: { type: "string" },
          description: { type: "string" },
          targetId: { type: "string" },
        },
        required: ["kind", "label", "title", "description", "targetId"],
      },
    },
  },
  required: ["message", "actions"],
} as const;

export function isChatReply(value: unknown): value is ChatReply {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<ChatReply>;
  return (
    typeof candidate.message === "string" &&
    Array.isArray(candidate.actions) &&
    candidate.actions.every(
      (action) =>
        action &&
        UI_ACTION_KINDS.includes(action.kind) &&
        typeof action.label === "string" &&
        typeof action.title === "string" &&
        typeof action.description === "string" &&
        typeof action.targetId === "string",
    )
  );
}
