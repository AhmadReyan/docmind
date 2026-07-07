import type { ApiError } from "@/lib/api-types";

/**
 * Same-origin base URL. All requests go to `/api/*`, which the Next.js
 * server rewrites to the API service so the httpOnly auth cookie stays
 * first-party.
 */
const BASE_URL = "";

export type ApiErrorCode = ApiError["code"];

/** Normalized error thrown by every api-client helper on a non-2xx response. */
export class ApiClientError extends Error {
  readonly detail: string;
  readonly code: ApiErrorCode;
  readonly status: number;

  constructor(detail: string, code: ApiErrorCode, status: number) {
    super(detail);
    this.name = "ApiClientError";
    this.detail = detail;
    this.code = code;
    this.status = status;
  }
}

export function isApiClientError(e: unknown): e is ApiClientError {
  return e instanceof ApiClientError;
}

const VALID_CODES: readonly ApiErrorCode[] = [
  "unauthorized",
  "invalid_credentials",
  "email_taken",
  "not_found",
  "validation_error",
  "file_too_large",
  "unsupported_file_type",
  "rate_limited",
  "internal_error",
];

function isApiErrorCode(value: unknown): value is ApiErrorCode {
  return (
    typeof value === "string" && (VALID_CODES as readonly string[]).includes(value)
  );
}

async function normalizeError(res: Response): Promise<ApiClientError> {
  let detail = `Request failed with status ${res.status}`;
  let code: ApiErrorCode = "internal_error";
  try {
    const body: unknown = await res.json();
    if (body !== null && typeof body === "object") {
      const maybe = body as Partial<ApiError>;
      if (typeof maybe.detail === "string" && maybe.detail.length > 0) {
        detail = maybe.detail;
      }
      if (isApiErrorCode(maybe.code)) {
        code = maybe.code;
      }
    }
  } catch {
    // Non-JSON body (proxy error page, empty body, ...) — keep the fallback.
  }
  return new ApiClientError(detail, code, res.status);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    credentials: "include",
    ...init,
  });
  if (!res.ok) {
    throw await normalizeError(res);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export const api = {
  get<T>(path: string): Promise<T> {
    return request<T>(path, { method: "GET" });
  },

  post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    });
  },

  postForm<T>(path: string, form: FormData): Promise<T> {
    // No Content-Type header: the browser sets the multipart boundary itself.
    return request<T>(path, { method: "POST", body: form });
  },

  del(path: string): Promise<void> {
    return request<void>(path, { method: "DELETE" });
  },
};
