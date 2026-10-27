import { log } from "./log";
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
  if (error instanceof TypeError) {
    return "Could not reach the server. Check that the app is running, then try again.";
  }
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}

function actorHeaders(actor: string): Record<string, string> {
  return { "X-Actor-Email": actor, Accept: "application/json" };
}

function newRequestId(): string {
  return `web-${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
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
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {
    ...actorHeaders(options.actor),
    ...(options.headers ?? {}),
  };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  const started = performance.now();
  const requestId = newRequestId();
  headers["X-Request-Id"] = requestId;
  log.debug("api.request", { method, path, requestId });

  try {
    const response = await fetch(path, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
    const durationMs = Math.round(performance.now() - started);

    if (!response.ok) {
      const error = await parseError(response);
      const fields = { method, path, status: response.status, code: error.code, durationMs, requestId };
      if (response.status >= 500) log.error("api.error", fields);
      else log.warn("api.error", fields);
      throw error;
    }

    log.debug("api.response", { method, path, status: response.status, durationMs, requestId });
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof Error && error.name === "AbortError") {
      log.debug("api.abort", { method, path, requestId });
      throw error;
    }
    log.error("api.network_error", { method, path, requestId, message: messageOf(error) });
    throw error;
  }
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
  const started = performance.now();
  const requestId = newRequestId();
  log.info("bulk_issue.submit", { courseId, requestId });

  try {
    const response = await fetch("/api/certificates/bulk-issue", {
      method: "POST",
      headers: {
        ...actorHeaders(actor),
        "X-Request-Id": requestId,
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify({ courseId, reason: reason ?? null }),
    });

    const durationMs = Math.round(performance.now() - started);
    if (!response.ok) {
      const error = await parseError(response);
      log.warn("bulk_issue.failed", {
        courseId,
        status: response.status,
        code: error.code,
        durationMs,
        requestId,
      });
      throw error;
    }

    const data = (await response.json()) as BulkResponse;
    const replayed = response.headers.get("Idempotency-Replayed") === "true";
    log.info("bulk_issue.result", {
      operationId: data.operationId,
      courseId,
      issued: data.summary.issued,
      skipped: data.summary.skipped,
      failed: data.summary.failed,
      replayed,
      durationMs,
      requestId,
    });
    return { data, replayed };
  } catch (error) {
    if (error instanceof ApiError) throw error;
    log.error("bulk_issue.network_error", { courseId, requestId, message: messageOf(error) });
    throw error;
  }
}

export async function downloadCertificateExport(
  actor: string,
  params: Omit<ListParams, "page" | "pageSize">,
): Promise<void> {
  const started = performance.now();
  const requestId = newRequestId();
  log.info("export.start", {
    sort: params.sort,
    dir: params.dir,
    qLen: params.q.length,
    requestId,
  });

  try {
    const response = await fetch(`/api/certificates/export.csv?${listQuery(params)}`, {
      headers: { "X-Actor-Email": actor, "X-Request-Id": requestId },
    });
    if (!response.ok) {
      const error = await parseError(response);
      log.warn("export.failed", { status: response.status, code: error.code, requestId });
      throw error;
    }

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

    log.info("export.done", {
      filename,
      bytes: blob.size,
      durationMs: Math.round(performance.now() - started),
      requestId,
    });
  } catch (error) {
    if (error instanceof ApiError) throw error;
    log.error("export.network_error", { requestId, message: messageOf(error) });
    throw error;
  }
}
