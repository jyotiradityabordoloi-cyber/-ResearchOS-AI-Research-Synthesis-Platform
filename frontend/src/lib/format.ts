import { formatDistanceToNowStrict } from "date-fns";

export function timeAgo(iso: string): string {
  return `${formatDistanceToNowStrict(new Date(iso))} ago`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** "2026-11-19" (a UTC calendar day from the API) -> "19 Nov". */
export function formatDay(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone: "UTC" });
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export const PROJECT_STATUS_LABEL: Record<string, string> = {
  draft: "Draft",
  collecting: "Collecting interviews",
  in_review: "In review",
  completed: "Completed",
};

export const SYNTHESIS_STATUS_LABEL: Record<string, string> = {
  not_started: "Not synthesised",
  running: "Synthesising…",
  completed: "Synthesised",
  failed: "Synthesis failed",
};

export const FIELD_LABEL: Record<string, string> = {
  participant_id: "Participant ID",
  participant_role: "Participant Role",
  company_size: "Company Size",
  plan_tier: "Plan Tier",
  pain: "Pain",
  behavior: "Behavior",
  verbatim_quote: "Verbatim Quote",
};
