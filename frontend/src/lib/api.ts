// Typed client for the ResearchOS FastAPI backend.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8010").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
  }
}

function describeDetail(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : String(d)))
      .join("; ");
  }
  return undefined;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  const isForm = typeof FormData !== "undefined" && init?.body instanceof FormData;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      // Let the browser set the multipart boundary for FormData bodies.
      headers: isForm ? init?.headers : { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, `Cannot reach the ResearchOS API at ${API_URL}. Is the backend running?`);
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => undefined);
  if (!res.ok) {
    const detail = body?.detail;
    throw new ApiError(res.status, describeDetail(detail) ?? `Request failed (${res.status})`, detail);
  }
  return body as T;
}

function qs(params: Record<string, string | number | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

// ---------------------------------------------------------------------------
// Types (mirror backend/app/schemas.py)
// ---------------------------------------------------------------------------

export type ProjectStatus = "draft" | "collecting" | "in_review" | "completed";
export type SynthesisStatus = "not_started" | "running" | "completed" | "failed";
export type ValidationStatus = "pending" | "valid" | "invalid";

export interface Project {
  id: string;
  name: string;
  description: string;
  objectives: string[];
  target_segments: string[];
  status: ProjectStatus;
  synthesis_status: SynthesisStatus;
  owner_name: string | null;
  interview_count: number;
  valid_interview_count: number;
  invalid_interview_count: number;
  participant_count: number;
  theme_count: number;
  pending_review_count: number;
  ready_for_synthesis: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectInput {
  name: string;
  description?: string;
  objectives?: string[];
  target_segments?: string[];
}

export interface ValidationIssue {
  field: string;
  severity: "error" | "warning";
  message: string;
}

export interface InterviewFields {
  participant_id: string;
  participant_role: string;
  company_size: string;
  plan_tier: string;
  pain: string;
  behavior: string;
  verbatim_quote: string;
}

export interface Interview extends InterviewFields {
  id: string;
  project_id: string;
  project_name: string | null;
  raw_content: string;
  source: "paste" | "upload" | "manual";
  source_filename: string | null;
  validation_status: ValidationStatus;
  validation_errors: ValidationIssue[];
  created_at: string;
  updated_at: string;
}

export interface ActivityItem {
  kind: string;
  title: string;
  detail: string | null;
  project_id: string | null;
  project_name: string | null;
  actor: string | null;
  at: string;
}

export interface DashboardStats {
  total_projects: number;
  total_interviews: number;
  valid_interviews: number;
  themes_identified: number;
  pending_reviews: number;
  projects_by_status: Record<string, number>;
  per_project: {
    project_id: string;
    project_name: string;
    interviews: number;
    valid_interviews: number;
    themes: number;
  }[];
  recent_activity: ActivityItem[];
}

export interface AuditEntry {
  id: string;
  project_id: string;
  entity_type: string;
  entity_id: string | null;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  comment: string | null;
  actor: string | null;
  created_at: string;
}

export interface PreviewItem {
  index: number;
  fields: InterviewFields;
  raw_content: string;
  source: "paste" | "upload" | "manual";
  source_filename: string | null;
  status: "valid" | "invalid";
  issues: ValidationIssue[];
  context_issues: ValidationIssue[];
}

export interface ImportPreview {
  items: PreviewItem[];
  summary: {
    total: number;
    valid: number;
    invalid: number;
    with_warnings: number;
    duplicate_participants: string[];
    existing_valid_participants: number;
    valid_participants_after_import: number;
    min_required: number;
    sample_sufficient: boolean;
  };
  file_errors: { filename: string; message: string }[];
}

export interface ImportItem {
  fields: InterviewFields;
  parsed_fields?: InterviewFields;
  raw_content: string;
  source: "paste" | "upload" | "manual";
  source_filename?: string | null;
}

export interface ImportResult {
  created: Interview[];
  skipped: { index: number; participant_id: string; reason: string }[];
}

export interface ValidationReport {
  total_interviews: number;
  valid_interviews: number;
  invalid_interviews: number;
  unique_valid_participants: number;
  min_required: number;
  duplicate_participants: Record<string, number>;
  invalid: { id: string; participant_id: string; errors: string[] }[];
  checks: { key: string; status: "pass" | "warn" | "fail"; message: string }[];
  can_run_standard_synthesis: boolean;
}

export interface SynthesisRun {
  id: string;
  project_id: string;
  status: "running" | "completed" | "failed";
  stage: string;
  provider: string;
  model: string;
  embedding_provider: string;
  error: string | null;
  warnings: { code: string; message: string }[];
  stats: Record<string, number | boolean | string>;
  started_at: string;
  finished_at: string | null;
  is_active: boolean;
  is_demo: boolean;
}

export interface Evidence {
  id: string;
  interview_id: string;
  pain_point_id: string | null;
  participant_id: string;
  quote: string;
  quote_verified: boolean;
  source_field: string | null;
  stance: "supporting" | "contradicting";
  note: string;
}

export interface Theme {
  id: string;
  project_id: string;
  run_id: string | null;
  code: string;
  name: string;
  description: string;
  implication: string;
  participant_ids: string[];
  participant_count: number;
  total_participants: number;
  frequency: number;
  confidence: number;
  severity: number;
  evidence_status: "sufficient" | "insufficient";
  is_outlier: boolean;
  is_low_confidence: boolean;
  has_contradictions: boolean;
  sensitive_tags: string[];
  requires_approval: boolean;
  strategic_flag: boolean;
  status: "proposed" | "approved" | "rejected" | "merged";
  origin: "ai" | "manual";
  human_edited: boolean;
  merged_into_id: string | null;
  split_from_id: string | null;
  evidence: Evidence[];
}

export type Decision = "approve" | "reject" | "reopen";
export type PriorityBand = "high" | "medium" | "low";

export interface ReviewPayload {
  decision: Decision;
  comment?: string;
  acknowledge_sensitive?: boolean;
}

export interface InsightPatch {
  title?: string;
  statement?: string;
  implication?: string;
  severity?: number;
  strategic_relevance?: number;
  priority_override?: PriorityBand | null;
  override_reason?: string | null;
  pm_comment?: string | null;
  strategic_flag?: boolean;
  comment?: string;
}

export interface Insight {
  id: string;
  project_id: string;
  theme_id: string | null;
  theme_code: string | null;
  title: string;
  statement: string;
  implication: string;
  frequency: number;
  severity: number;
  strategic_relevance: number;
  confidence: number;
  priority_score: number;
  priority_override: string | null;
  override_reason: string | null;
  pm_comment: string | null;
  is_outlier: boolean;
  sensitive_tags: string[];
  requires_approval: boolean;
  strategic_flag: boolean;
  status: string;
  origin: string;
  project_name: string | null;
  computed_priority: PriorityBand;
  effective_priority: PriorityBand;
  is_overridden: boolean;
}

export interface ReportSummary {
  id: string;
  project_id: string;
  project_name: string | null;
  run_id: string | null;
  title: string;
  status: "draft" | "approved";
  excluded_sensitive_count: number;
  created_at: string;
}

export interface ReportTheme {
  id: string;
  code: string;
  name: string;
  description: string;
  implication: string;
  status: string;
  reviewed: boolean;
  participant_ids: string[];
  participant_count: number;
  total_participants: number;
  frequency: number;
  confidence: number;
  severity: number;
  strategic_flag: boolean;
  sensitive_tags: string[];
  is_outlier: boolean;
  is_low_confidence: boolean;
  quotes: { participant_id: string; quote: string; interview_id: string }[];
  contradictions: { participant_id: string; quote: string; note: string; interview_id: string }[];
}

export interface ReportContent {
  kind: "draft" | "approved";
  generated_at: string;
  project: { id: string; name: string; description: string; objectives: string[]; target_segments: string[] };
  run: { provider: string; model: string; embedding_provider: string; is_demo: boolean; finished_at: string | null };
  section_titles: string[];
  sections: {
    objective: { objectives: string[]; context: string };
    participants: {
      total_interviews: number;
      valid_interviews: number;
      unique_participants: number;
      roles: Record<string, number>;
      company_sizes: Record<string, number>;
      plan_tiers: Record<string, number>;
      target_segments: string[];
    };
    methodology: string[];
    themes: ReportTheme[];
    frequency: { code: string; name: string; participant_count: number; total_participants: number; frequency: number; is_outlier: boolean }[];
    quotes: { code: string; name: string; quotes: ReportTheme["quotes"] }[];
    contradictions: { code: string; name: string; participant_id: string; quote: string; note: string; interview_id: string }[];
    outliers: ReportTheme[];
    implications: {
      title: string;
      statement: string;
      implication: string;
      theme_code: string | null;
      priority: PriorityBand;
      computed_priority: PriorityBand;
      overridden: boolean;
      override_reason: string | null;
      frequency: number;
      severity: number;
      strategic_relevance: number;
      confidence: number;
      pm_comment: string | null;
      origin: string;
      reviewed: boolean;
    }[];
    next_steps: string[];
    limitations: string[];
  };
  excluded: { sensitive_pending: { code: string; name: string; tags: string[] }[]; unreviewed: number; rejected: number };
}

export interface Report extends ReportSummary {
  content_markdown: string;
  content_json: ReportContent;
}

export interface RepositoryHit {
  kind: "theme" | "insight";
  id: string;
  project_id: string;
  project_name: string;
  project_status: string;
  code: string | null;
  title: string;
  description: string;
  implication: string;
  participant_ids: string[];
  participant_count: number | null;
  total_participants: number | null;
  frequency: number;
  severity: number;
  status: string;
  requires_approval: boolean;
  sensitive_tags: string[];
  is_outlier: boolean;
  has_contradictions: boolean;
  score: number | null;
  evidence_count: number;
  evidence: { id: string; interview_id: string; participant_id: string; quote: string; quote_verified: boolean; note: string; stance: string }[];
  priority: PriorityBand | null;
  created_at: string;
}

export interface RepositoryFacets {
  projects: { id: string; name: string; status: string }[];
  roles: string[];
  company_sizes: string[];
  plan_tiers: string[];
}

export type SearchParams = {
  q?: string;
  mode?: "keyword" | "semantic" | "theme";
  project_id?: string;
  role?: string;
  company_size?: string;
  plan_tier?: string;
  approved_only?: string;
};

export interface ProviderStatus {
  name: string;
  model: string;
  available: boolean;
  detail: string;
  is_demo: boolean;
}

export interface AISettings {
  llm: ProviderStatus;
  embeddings: ProviderStatus;
  min_interviews_for_synthesis: number;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export const api = {
  health: () => request<{ status: string; database: string; pgvector: string | null }>("/api/health"),
  aiSettings: () => request<AISettings>("/api/settings/ai"),
  dashboard: () => request<DashboardStats>("/api/dashboard"),

  projects: {
    list: (params: { q?: string; status?: string } = {}) => request<Project[]>(`/api/projects${qs(params)}`),
    get: (id: string) => request<Project>(`/api/projects/${id}`),
    create: (data: ProjectInput) =>
      request<Project>("/api/projects", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<ProjectInput> & { status?: ProjectStatus }) =>
      request<Project>(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    remove: (id: string) => request<void>(`/api/projects/${id}`, { method: "DELETE" }),
    audit: (id: string) => request<AuditEntry[]>(`/api/projects/${id}/audit`),
  },

  interviews: {
    list: (params: { project_id?: string; validation_status?: string; q?: string } = {}) =>
      request<Interview[]>(`/api/interviews${qs(params)}`),
    forProject: (projectId: string) => request<Interview[]>(`/api/projects/${projectId}/interviews`),
    get: (id: string) => request<Interview>(`/api/interviews/${id}`),
    create: (projectId: string, data: Partial<InterviewFields> & { raw_content?: string }) =>
      request<Interview>(`/api/projects/${projectId}/interviews`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    correct: (id: string, data: Partial<InterviewFields> & { comment?: string }) =>
      request<Interview>(`/api/interviews/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    remove: (id: string) => request<void>(`/api/interviews/${id}`, { method: "DELETE" }),
    validate: (fields: InterviewFields) =>
      request<{ status: "valid" | "invalid"; issues: ValidationIssue[] }>("/api/interviews/validate", {
        method: "POST",
        body: JSON.stringify(fields),
      }),
  },

  imports: {
    previewText: (projectId: string, text: string) =>
      request<ImportPreview>(`/api/projects/${projectId}/import/preview`, {
        method: "POST",
        body: JSON.stringify({ text }),
      }),
    previewFiles: (projectId: string, files: File[]) => {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      return request<ImportPreview>(`/api/projects/${projectId}/import/preview-files`, {
        method: "POST",
        body: form,
      });
    },
    save: (projectId: string, items: ImportItem[], skipInvalid = true) =>
      request<ImportResult>(`/api/projects/${projectId}/import`, {
        method: "POST",
        body: JSON.stringify({ items, skip_invalid: skipInvalid }),
      }),
    report: (projectId: string) => request<ValidationReport>(`/api/projects/${projectId}/validation-report`),
  },

  synthesis: {
    start: (projectId: string, force = false) =>
      request<SynthesisRun>(`/api/projects/${projectId}/synthesis`, {
        method: "POST",
        body: JSON.stringify({ force }),
      }),
    runs: (projectId: string) => request<SynthesisRun[]>(`/api/projects/${projectId}/synthesis/runs`),
    themes: (projectId: string, includeRejected = false) =>
      request<Theme[]>(`/api/projects/${projectId}/themes${qs({ include_rejected: includeRejected ? "true" : undefined })}`),
    insights: (projectId: string) => request<Insight[]>(`/api/projects/${projectId}/insights`),
  },

  review: {
    editTheme: (id: string, data: { name?: string; description?: string; implication?: string; strategic_flag?: boolean; comment?: string }) =>
      request<Theme>(`/api/themes/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    reviewTheme: (id: string, data: ReviewPayload) =>
      request<Theme>(`/api/themes/${id}/review`, { method: "POST", body: JSON.stringify(data) }),
    merge: (projectId: string, data: { theme_ids: string[]; name?: string; description?: string; comment?: string }) =>
      request<Theme>(`/api/projects/${projectId}/themes/merge`, { method: "POST", body: JSON.stringify(data) }),
    split: (id: string, data: { evidence_ids: string[]; name: string; description?: string; comment?: string }) =>
      request<Theme>(`/api/themes/${id}/split`, { method: "POST", body: JSON.stringify(data) }),
    moveEvidence: (evidenceId: string, targetThemeId: string) =>
      request<Theme[]>(`/api/evidence/${evidenceId}/move`, {
        method: "POST",
        body: JSON.stringify({ target_theme_id: targetThemeId }),
      }),
    history: (id: string) => request<AuditEntry[]>(`/api/themes/${id}/history`),
    allInsights: (params: { project_id?: string; status?: string; q?: string } = {}) =>
      request<Insight[]>(`/api/insights${qs(params)}`),
    editInsight: (id: string, data: InsightPatch) =>
      request<Insight>(`/api/insights/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    reviewInsight: (id: string, data: ReviewPayload) =>
      request<Insight>(`/api/insights/${id}/review`, { method: "POST", body: JSON.stringify(data) }),
    createInsight: (
      projectId: string,
      data: { title: string; statement?: string; implication?: string; theme_id?: string; severity: number; strategic_relevance: number; pm_comment?: string },
    ) => request<Insight>(`/api/projects/${projectId}/insights`, { method: "POST", body: JSON.stringify(data) }),
  },

  reports: {
    generate: (projectId: string, kind: "draft" | "approved", title?: string) =>
      request<Report>(`/api/projects/${projectId}/reports`, { method: "POST", body: JSON.stringify({ kind, title }) }),
    forProject: (projectId: string) => request<ReportSummary[]>(`/api/projects/${projectId}/reports`),
    list: () => request<ReportSummary[]>("/api/reports"),
    get: (id: string) => request<Report>(`/api/reports/${id}`),
    remove: (id: string) => request<void>(`/api/reports/${id}`, { method: "DELETE" }),
    markdownUrl: (id: string) => `${API_URL}/api/reports/${id}/export.md`,
    pdfUrl: (id: string) => `${API_URL}/api/reports/${id}/export.pdf`,
  },

  repository: {
    search: (params: SearchParams) => request<RepositoryHit[]>(`/api/repository/search${qs(params)}`),
    facets: () => request<RepositoryFacets>("/api/repository/facets"),
  },
};
