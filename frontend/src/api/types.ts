export type IncidentStatus =
  | "created"
  | "analyzing"
  | "analyzed"
  | "analysis_failed"
  | "reviewed";

export type AnalysisConfidence = "low" | "medium" | "high";
export type IncidentCategory =
  | "bug"
  | "feature"
  | "documentation"
  | "configuration"
  | "performance";
export type IncidentSeverity = "low" | "medium" | "high" | "critical";
export type IncidentPriority = "low" | "medium" | "high" | "urgent";

export interface HealthResponse {
  status: "ok";
  analyzer_backend: string;
}

export interface TriageSummary {
  category: IncidentCategory;
  severity: IncidentSeverity;
  priority: IncidentPriority;
  summary: string;
}

export interface IncidentListItem {
  id: string;
  title: string;
  status: IncidentStatus;
  created_at: string;
  confidence: AnalysisConfidence | null;
  proposal: TriageSummary | null;
  final: TriageSummary | null;
}

export interface IncidentListPage {
  items: IncidentListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface TriageResult {
  category: IncidentCategory;
  severity: IncidentSeverity;
  priority: IncidentPriority;
  summary: string;
  affected_components: string[];
  missing_information: string[];
  justification: string;
  confidence: AnalysisConfidence;
}

export interface TriageReview {
  reviewed: boolean;
  source: string;
  review_comment: string | null;
  reviewed_at: string;
  final: TriageResult;
}

export interface TriageResultResponse extends TriageResult {
  id: string;
  created_at: string;
  review: TriageReview | null;
}

export interface IncidentResponse {
  id: string;
  title: string;
  description: string;
  steps_to_reproduce: string | null;
  expected_behavior: string | null;
  actual_behavior: string | null;
  environment: string | null;
  components: string[] | null;
  status: IncidentStatus;
  created_at: string;
  triage: TriageResultResponse | null;
}

export interface IncidentCreatePayload {
  title: string;
  description: string;
  steps_to_reproduce?: string;
  expected_behavior?: string;
  actual_behavior?: string;
  environment?: string;
  components?: string[];
}

export interface TriageReviewPayload {
  category?: IncidentCategory;
  severity?: IncidentSeverity;
  priority?: IncidentPriority;
  summary?: string;
  affected_components?: string[];
  missing_information?: string[];
  justification?: string;
  confidence?: AnalysisConfidence;
  review_comment?: string;
}

export interface FieldAccuracy {
  total: number;
  correct: number;
  accuracy: number;
}

export interface CorrectionByConfidence {
  total_reviews: number;
  corrected_reviews: number;
  accepted_without_changes: number;
  correction_rate: number;
}

export interface ReviewMetricsResponse {
  total_reviewed: number;
  accepted_without_changes: number;
  acceptance_rate: number;
  field_accuracy: Record<string, FieldAccuracy>;
  confusion_matrices: Record<string, Record<string, Record<string, number>>>;
  corrections_by_confidence: Record<string, CorrectionByConfidence>;
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface ApiErrorPayload {
  detail?: string;
}
