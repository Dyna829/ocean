import type {
  BulkResponse,
  CertificateDetail,
  CoursesResponse,
  ListResponse,
  Me,
  SortDir,
  SortField,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}

function actorHeaders(actor: string): Record<string, string> {
  return { "X-Actor-Email": actor, Accept: "application/json" };
}

async function parseError(response: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `Request failed (${response.status})`;
  let details: unknown;
  try {
    const payload = (await response.json()) as {
      code?: string;
      message?: string;
      details?: unknown;
    };
    if (payload.code) code = payload.code;
    if (payload.message) message = payload.message;
    details = payload.details;
  } catch {
    // Non-JSON error body: keep the status-based default.
  }
  return new ApiError(response.status, code, message, details);
}

interface RequestOptions {
  actor: string;
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

export async function request<T>(path: string, options: RequestOptions): Promise<T> {
  const headers: Record<string, string> = {
    ...actorHeaders(options.actor),
    ...(options.headers ?? {}),
  };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(path, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  });

  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

export interface ListParams {
  q: string;
  sort: SortField;
  dir: SortDir;
  page?: number;
  pageSize?: number;
}

export function listQuery(params: ListParams): string {
  const search = new URLSearchParams({ q: params.q, sort: params.sort, dir: params.dir });
  if (params.page !== undefined) search.set("page", String(params.page));
  if (params.pageSize !== undefined) search.set("pageSize", String(params.pageSize));
  return search.toString();
}

export function fetchMe(actor: string, signal?: AbortSignal): Promise<Me> {
  return request<Me>("/api/me", { actor, signal });
}

export function fetchCertificates(
  actor: string,
  params: ListParams,
  signal?: AbortSignal,
): Promise<ListResponse> {
  return request<ListResponse>(`/api/certificates?${listQuery(params)}`, { actor, signal });
}

export function fetchCertificate(
  actor: string,
  certificateId: string,
  signal?: AbortSignal,
): Promise<CertificateDetail> {
  return request<CertificateDetail>(
    `/api/certificates/${encodeURIComponent(certificateId)}`,
    { actor, signal },
  );
}

export function fetchCourses(actor: string, signal?: AbortSignal): Promise<CoursesResponse> {
  return request<CoursesResponse>("/api/courses", { actor, signal });
}

export function revokeCertificate(
  actor: string,
  certificateId: string,
  reason?: string,
): Promise<CertificateDetail> {
  return request<CertificateDetail>(
    `/api/certificates/${encodeURIComponent(certificateId)}/revoke`,
    { actor, method: "POST", body: { reason: reason ?? null } },
  );
}

export async function bulkIssue(
  actor: string,
  courseId: string,
  idempotencyKey: string,
  reason?: string,
): Promise<{ data: BulkResponse; replayed: boolean }> {
  const response = await fetch("/api/certificates/bulk-issue", {
    method: "POST",
    headers: {
      ...actorHeaders(actor),
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({ courseId, reason: reason ?? null }),
  });
  if (!response.ok) throw await parseError(response);
  return {
    data: (await response.json()) as BulkResponse,
    replayed: response.headers.get("Idempotency-Replayed") === "true",
  };
}

export async function downloadCertificateExport(
  actor: string,
  params: Omit<ListParams, "page" | "pageSize">,
): Promise<void> {
  const response = await fetch(`/api/certificates/export.csv?${listQuery(params)}`, {
    headers: { "X-Actor-Email": actor },
  });
  if (!response.ok) throw await parseError(response);

  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename = /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? "certificates.csv";
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
