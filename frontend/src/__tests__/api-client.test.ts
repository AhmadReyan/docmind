import { describe, expect, it, vi } from "vitest";
import { api, ApiClientError, isApiClientError } from "@/lib/api-client";

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api-client error normalization", () => {
  it("normalizes a 409 email_taken ErrorResponse into a typed ApiClientError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          { detail: "Email is already registered", code: "email_taken" },
          409,
        ),
      ),
    );

    const promise = api.post("/api/auth/register", {
      email: "demo@docmind.dev",
      password: "demo1234",
    });

    await expect(promise).rejects.toBeInstanceOf(ApiClientError);
    try {
      await api.post("/api/auth/register", {
        email: "demo@docmind.dev",
        password: "demo1234",
      });
      expect.unreachable("should have thrown");
    } catch (e) {
      expect(isApiClientError(e)).toBe(true);
      const error = e as ApiClientError;
      expect(error.code).toBe("email_taken");
      expect(error.status).toBe(409);
      expect(error.detail).toBe("Email is already registered");
      expect(error.message).toBe("Email is already registered");
    }
  });

  it("falls back to a generic error when the body is not the contract shape", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response("<html>Bad Gateway</html>", {
            status: 502,
            headers: { "Content-Type": "text/html" },
          }),
      ),
    );

    try {
      await api.get("/api/documents");
      expect.unreachable("should have thrown");
    } catch (e) {
      const error = e as ApiClientError;
      expect(isApiClientError(e)).toBe(true);
      expect(error.status).toBe(502);
      expect(error.code).toBe("internal_error");
      expect(error.detail).toContain("502");
    }
  });

  it("sends credentials and parses JSON on success", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ id: "u1", email: "demo@docmind.dev", created_at: "2026-07-07T12:00:00Z" }, 200),
    );
    vi.stubGlobal("fetch", fetchMock);

    const user = await api.get<{ id: string }>("/api/auth/me");
    expect(user.id).toBe("u1");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/me",
      expect.objectContaining({ credentials: "include", method: "GET" }),
    );
  });

  it("resolves undefined for 204 responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 204 })),
    );
    await expect(api.del("/api/documents/d1")).resolves.toBeUndefined();
  });
});
