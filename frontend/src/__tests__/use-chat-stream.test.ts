import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ChatStreamEvent, Source } from "@/lib/api-types";
import { useChatStream } from "@/lib/use-chat-stream";

const SOURCE: Source = {
  index: 1,
  chunk_id: "c-1",
  document_id: "d-1",
  document_title: "Handbook",
  page_number: 3,
  snippet: "Cats purr at 25 Hz.",
  score: 0.0328,
};

/** Builds an SSE byte stream from string parts, one enqueue per part. */
function sseStream(parts: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const part of parts) {
        controller.enqueue(encoder.encode(part));
      }
      controller.close();
    },
  });
}

function sseResponse(parts: string[]): Response {
  return new Response(sseStream(parts), {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
    },
  });
}

describe("useChatStream", () => {
  it("dispatches the contract event sequence in order: sources → token → done", async () => {
    const frames =
      `event: sources\ndata: ${JSON.stringify({ sources: [SOURCE] })}\n\n` +
      `event: token\ndata: ${JSON.stringify({ delta: "Cats purr" })}\n\n` +
      `event: token\ndata: ${JSON.stringify({ delta: " at 25 Hz [1]." })}\n\n` +
      `event: done\ndata: ${JSON.stringify({ message_id: "m-9", conversation_title: "Cat facts" })}\n\n`;

    // Split at awkward positions so frames span multiple network chunks.
    const parts = [
      frames.slice(0, 25),
      frames.slice(25, 90),
      frames.slice(90, 91),
      frames.slice(91),
    ];

    const fetchMock = vi.fn(async () => sseResponse(parts));
    vi.stubGlobal("fetch", fetchMock);

    const events: ChatStreamEvent[] = [];
    const { result } = renderHook(() =>
      useChatStream({ onEvent: (e) => events.push(e) }),
    );

    await act(async () => {
      await result.current.sendMessage("conv-1", "Why do cats purr?");
    });

    // Ordering: sources first, then tokens, done last.
    expect(events.map((e) => e.event)).toEqual([
      "sources",
      "token",
      "token",
      "done",
    ]);

    await waitFor(() => {
      expect(result.current.done).toEqual({
        message_id: "m-9",
        conversation_title: "Cat facts",
      });
    });
    expect(result.current.sources).toEqual([SOURCE]);
    expect(result.current.streamedText).toBe("Cats purr at 25 Hz [1].");
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.error).toBeNull();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/conversations/conv-1/messages",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ content: "Why do cats purr?" }),
      }),
    );
  });

  it("surfaces a pre-stream 429 rate_limited JSON error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              detail: "Rate limit exceeded",
              code: "rate_limited",
            }),
            { status: 429, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.sendMessage("conv-1", "hello");
    });

    expect(result.current.error).toEqual({
      detail: "Rate limit exceeded",
      code: "rate_limited",
    });
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.done).toBeNull();
    expect(result.current.streamedText).toBe("");
  });

  it("handles a mid-stream error event after sources and partial tokens", async () => {
    const frames =
      `event: sources\ndata: ${JSON.stringify({ sources: [SOURCE] })}\n\n` +
      `event: token\ndata: ${JSON.stringify({ delta: "Partial" })}\n\n` +
      `event: error\ndata: ${JSON.stringify({ detail: "LLM provider unavailable", code: "internal_error" })}\n\n`;

    vi.stubGlobal("fetch", vi.fn(async () => sseResponse([frames])));

    const events: ChatStreamEvent[] = [];
    const { result } = renderHook(() =>
      useChatStream({ onEvent: (e) => events.push(e) }),
    );

    await act(async () => {
      await result.current.sendMessage("conv-1", "hello");
    });

    expect(events.map((e) => e.event)).toEqual(["sources", "token", "error"]);
    expect(result.current.error).toEqual({
      detail: "LLM provider unavailable",
      code: "internal_error",
    });
    expect(result.current.streamedText).toBe("Partial");
    expect(result.current.done).toBeNull();
    expect(result.current.isStreaming).toBe(false);
  });

  it("reports a network failure as an error state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.sendMessage("conv-1", "hello");
    });

    expect(result.current.error?.code).toBe("network_error");
    expect(result.current.isStreaming).toBe(false);
  });

  it("treats a stream that ends without done/error as interrupted", async () => {
    const frames = `event: token\ndata: ${JSON.stringify({ delta: "Hi" })}\n\n`;
    vi.stubGlobal("fetch", vi.fn(async () => sseResponse([frames])));

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.sendMessage("conv-1", "hello");
    });

    expect(result.current.streamedText).toBe("Hi");
    expect(result.current.error?.code).toBe("stream_interrupted");
    expect(result.current.isStreaming).toBe(false);
  });
});
