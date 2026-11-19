/**
 * Where a project is in the research flow. Shared by the dashboard and project cards
 * so both always tell the same story.
 */

export const STAGES = ["Collect", "Validate", "Synthesise", "Review", "Report"] as const;

export interface ProgressInput {
  interviews: number;
  participants: number;
  min_participants: number;
  synthesis_status: string;
  review_total: number;
  review_done: number;
  reports: number;
}

export function stageFlags(p: ProgressInput): boolean[] {
  return [
    p.interviews > 0,
    p.participants >= p.min_participants,
    p.synthesis_status === "completed",
    p.review_total > 0 && p.review_done === p.review_total,
    p.reports > 0,
  ];
}

export function nextStep(p: ProgressInput, flags = stageFlags(p)): string {
  if (p.synthesis_status === "running") return "Synthesis running…";
  if (p.synthesis_status === "failed") return "Last synthesis failed, retry from the project";
  if (!flags[0]) return "Add interview notes";
  if (!flags[1]) return `${p.min_participants - p.participants} more valid participant(s) needed`;
  if (!flags[2]) return "Ready to synthesise";
  if (!flags[3]) return `${p.review_total - p.review_done} finding(s) to review`;
  if (!flags[4]) return "Generate the report";
  return "Report generated";
}
