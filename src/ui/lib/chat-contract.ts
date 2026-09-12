import { z } from "zod";
import { EvidenceIdSchema, RunIdSchema } from "./analytics-contract.ts";

// Only actions with a real data endpoint are advertised to the model.
export const UI_ACTION_KINDS = ["open_incident", "show_timeline", "show_logs"] as const;
export const UiActionSchema = z.object({
  kind: z.enum(UI_ACTION_KINDS),
  label: z.string(),
  title: z.string(),
  description: z.string(),
  targetId: EvidenceIdSchema,
  datasetId: z.string().min(1),
  analysisRunId: RunIdSchema,
});
export const ChatReplySchema = z.object({
  message: z.string().describe("Concise operator-facing answer in the user's language."),
  actions: z.array(UiActionSchema).max(3).describe(
    "Verified snapshot links. show_logs targets one event_id; other actions target an incident_id. Empty without evidence.",
  ),
});
export const ChatRequestSchema = z.object({
  messages: z.array(z.object({
    role: z.enum(["user", "assistant"]),
    content: z.string().trim().min(1).max(10_000),
  })).min(1).max(20),
  context: z.object({
    datasetId: z.string().trim().min(1),
    incidentId: EvidenceIdSchema.nullable(),
    eventId: EvidenceIdSchema.optional(),
    analysisRunId: RunIdSchema.nullable(),
  }).optional(),
});
export type UiActionKind = (typeof UI_ACTION_KINDS)[number];
export type UiAction = z.infer<typeof UiActionSchema>;
export type ChatReply = z.infer<typeof ChatReplySchema>;
export type ChatRequest = z.infer<typeof ChatRequestSchema>;
export const CHAT_REPLY_SCHEMA = z.toJSONSchema(ChatReplySchema);
export function isChatReply(value: unknown): value is ChatReply {
  return ChatReplySchema.safeParse(value).success;
}
