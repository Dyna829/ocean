export type CertificateStatus = "ACTIVE" | "REVOKED";
export type SortField = "issued_date" | "learner_name" | "course_title" | "serial";
export type SortDir = "asc" | "desc";

export interface Tenant {
  id: string;
  slug: string;
  name: string;
  timezone: string;
}

export interface Actor {
  id: string;
  email: string;
  name: string;
}

export interface Me {
  actor: Actor;
  tenant: Tenant;
}

export interface CertificateItem {
  id: string;
  serial: string;
  courseId: string;
  courseTitle: string;
  learnerId: string;
  learnerName: string;
  status: CertificateStatus;
  issuedAt: string;
  issuedAtLocal: string;
  issueDateLocal: string;
  revokedAt: string | null;
  revokedAtLocal: string | null;
  revokedBy: string | null;
}

export interface AuditEvent {
  id: string;
  action: "ISSUED" | "REVOKED";
  actor: Actor;
  at: string;
  atLocal: string;
  detail: Record<string, unknown>;
}

export interface CertificateDetail {
  certificate: CertificateItem;
  audit: AuditEvent[];
  alreadyRevoked?: boolean;
}

export interface ListResponse {
  items: CertificateItem[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  sort: SortField;
  dir: SortDir;
  q: string;
  tenant: Tenant;
}

export interface Course {
  id: string;
  title: string;
  completed: number;
  incomplete: number;
  certified: number;
  eligible: number;
}

export interface CoursesResponse {
  courses: Course[];
  tenant: Tenant;
}

export type OutcomeStatus = "issued" | "skipped" | "failed";

export interface BulkOutcome {
  learnerId: string;
  learnerName: string;
  status: OutcomeStatus;
  reason?: string;
  message?: string;
  certificateId?: string;
  serial?: string;
}

export interface BulkResponse {
  operationId: string;
  courseId: string;
  courseTitle: string;
  tenant: Tenant;
  summary: {
    total: number;
    issued: number;
    skipped: number;
    failed: number;
  };
  outcomes: BulkOutcome[];
}

export type ListState =
  | { kind: "loading" }
  | { kind: "ready"; data: ListResponse }
  | { kind: "error"; message: string };
