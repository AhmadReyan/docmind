"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatStreamEvent, Source } from "@/lib/api-types";

export interface ChatStreamError {
  detail: string;
  code: string;
}

export interface ChatStreamDone {
  message_id: string;
  conversation_title: string;
}

export interface ChatStreamState {
  sources: Source[] | null;
  streamedText: string;
  isStreaming: boolean;
  error: ChatStreamError | null;
  done: ChatStreamDone | null;
}

export interface UseChatStreamOptions {
  /** Called for every parsed SSE event, in arrival order. */
  onEvent?: (event: ChatStreamEvent) => void;
}

export interface UseChatStreamResult extends ChatStreamState {
  sendMessage: (conversationId: string, content: string) => Promise<void>;
  /** Clears sources/text/error/done (e.g. after merging into history). */
  reset: () => void;
  /** Aborts an in-flight stream, if any. */
  abort: () => void;
}

const INITIAL_STATE: ChatStreamState = {
  sources: null,
  streamedText: "",
  isStreaming: false,
  error: null,
  done: null,
};

const FRAME_SEPARATOR = /\r?\n\r?\n/;

/**
 * Parses one raw SSE frame ("event: X\ndata: {...}") into a typed
 * ChatStreamEvent, or null if the frame is not one of the contract events.
 */
export function parseChatStreamFrame(frame: string): ChatStreamEvent | null {
  let eventName = "";
  const dataLines: string[] = [];
  for (const rawLine of frame.split("\n")) {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).replace(/^ /, ""));
    }
  }
  if (eventName === "" || dataLines.length === 0) return null;

  let data: unknown;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    return null;
  }
  if (data === null || typeof data !== "object") return null;

  switch (eventName) {
    case "sources": {
      const d = data as { sources?: unknown };
      if (!Array.isArray(d.sources)) return null;
      return { event: "sources", data: { sources: d.sources as Source[] } };
    }
    case "token": {
      const d = data as { delta?: unknown };
      if (typeof d.delta !== "string") return null;
      return { event: "token", data: { delta: d.delta } };
    }
    case "done": {
      const d = data as { message_id?: unknown; conversation_title?: unknown };
      if (typeof d.message_id !== "string" || typeof d.conversation_title !== "string") {
        return null;
      }
      return {
        event: "done",
        data: { message_id: d.message_id, conversation_title: d.conversation_title },
      };
    }
    case "error": {
      const d = data as { detail?: unknown; code?: unknown };
      return {
        event: "error",
        data: {
          detail: typeof d.detail === "string" ? d.detail : "Something went wrong.",
          code: typeof d.code === "string" ? d.code : "internal_error",
        },
      };
    }
    default:
      return null;
  }
}

/**
 * Consumes the `POST /api/conversations/{id}/messages` SSE stream via
 * fetch + ReadableStream, handling frames split across network chunks,
 * pre-stream JSON errors (e.g. 429 rate_limited), mid-stream `error`
 * events, and network aborts.
 */
export function useChatStream(
  options: UseChatStreamOptions = {},
): UseChatStreamResult {
  const [state, setState] = useState<ChatStreamState>(INITIAL_STATE);
  const abortRef = useRef<AbortController | null>(null);
  const onEventRef = useRef<UseChatStreamOptions["onEvent"]>(options.onEvent);
  onEventRef.current = options.onEvent;

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    setState(INITIAL_STATE);
  }, []);

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const sendMessage = useCallback(
    async (conversationId: string, content: string) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setState({ ...INITIAL_STATE, isStreaming: true });

      let sawTerminal = false;

      const dispatch = (event: ChatStreamEvent): void => {
        onEventRef.current?.(event);
        switch (event.event) {
          case "sources":
            setState((s) => ({ ...s, sources: event.data.sources }));
            break;
          case "token":
            setState((s) => ({
              ...s,
              streamedText: s.streamedText + event.data.delta,
            }));
            break;
          case "done":
            sawTerminal = true;
            setState((s) => ({ ...s, done: event.data, isStreaming: false }));
            break;
          case "error":
            sawTerminal = true;
            setState((s) => ({ ...s, error: event.data, isStreaming: false }));
            break;
        }
      };

      try {
        const res = await fetch(
          `/api/conversations/${conversationId}/messages`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ content }),
            signal: controller.signal,
          },
        );

        const contentType = res.headers.get("content-type") ?? "";
        if (!res.ok || !contentType.includes("text/event-stream")) {
          // Non-stream response: a plain JSON error (e.g. 429 rate_limited).
          let error: ChatStreamError = {
            detail: `Request failed with status ${res.status}`,
            code: "internal_error",
          };
          try {
            const body: unknown = await res.json();
            if (body !== null && typeof body === "object") {
              const maybe = body as { detail?: unknown; code?: unknown };
              error = {
                detail:
                  typeof maybe.detail === "string" ? maybe.detail : error.detail,
                code: typeof maybe.code === "string" ? maybe.code : error.code,
              };
            }
          } catch {
            // keep fallback
          }
          setState((s) => ({ ...s, error, isStreaming: false }));
          return;
        }

        if (!res.body) {
          throw new Error("Response has no body");
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        const drainFrames = (): void => {
          for (;;) {
            const match = FRAME_SEPARATOR.exec(buffer);
            if (!match) break;
            const frame = buffer.slice(0, match.index);
            buffer = buffer.slice(match.index + match[0].length);
            const event = parseChatStreamFrame(frame);
            if (event) dispatch(event);
            if (sawTerminal) break;
          }
        };

        for (;;) {
          const { done: readerDone, value } = await reader.read();
          if (readerDone) break;
          buffer += decoder.decode(value, { stream: true });
          drainFrames();
          if (sawTerminal) {
            await reader.cancel().catch(() => undefined);
            break;
          }
        }

        if (!sawTerminal) {
          buffer += decoder.decode();
          drainFrames();
        }

        if (!sawTerminal) {
          setState((s) => ({
            ...s,
            error: {
              detail: "The response stream ended unexpectedly.",
              code: "stream_interrupted",
            },
            isStreaming: false,
          }));
        }
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") {
          setState((s) => ({ ...s, isStreaming: false }));
          return;
        }
        setState((s) => ({
          ...s,
          error: {
            detail: "Connection lost. Check your network and try again.",
            code: "network_error",
          },
          isStreaming: false,
        }));
      }
    },
    [],
  );

  return { ...state, sendMessage, reset, abort };
}
