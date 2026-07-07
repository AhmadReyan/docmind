"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ChatStreamEvent,
  ConversationDetail,
  MessageOut,
  Source,
} from "@/lib/api-types";
import { api, isApiClientError } from "@/lib/api-client";
import { takePendingMessage } from "@/lib/pending-message";
import { useChatStream } from "@/lib/use-chat-stream";
import { useApp } from "@/components/shell/app-shell";
import { ChatInput } from "@/components/chat/chat-input";
import { ChatMessage } from "@/components/chat/chat-message";
import { Spinner } from "@/components/ui/spinner";

export default function ConversationPage() {
  const { id } = useParams<{ id: string }>();
  const { updateConversationTitle } = useApp();

  const [messages, setMessages] = useState<MessageOut[] | null>(null);
  const [notFound, setNotFound] = useState(false);

  const liveTextRef = useRef("");
  const liveSourcesRef = useRef<Source[] | null>(null);
  const sentPendingRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleEvent = useCallback(
    (event: ChatStreamEvent) => {
      switch (event.event) {
        case "sources":
          liveSourcesRef.current = event.data.sources;
          break;
        case "token":
          liveTextRef.current += event.data.delta;
          break;
        case "done": {
          const assistantMessage: MessageOut = {
            id: event.data.message_id,
            role: "assistant",
            content: liveTextRef.current,
            sources: liveSourcesRef.current,
            created_at: new Date().toISOString(),
          };
          setMessages((msgs) => [...(msgs ?? []), assistantMessage]);
          updateConversationTitle(id, event.data.conversation_title);
          break;
        }
        case "error":
          break;
      }
    },
    [id, updateConversationTitle],
  );

  const stream = useChatStream({ onEvent: handleEvent });
  const { reset: resetStream, sendMessage } = stream;

  // Merge the finalized assistant message, then clear the live stream state.
  useEffect(() => {
    if (stream.done) resetStream();
  }, [stream.done, resetStream]);

  const send = useCallback(
    (content: string) => {
      liveTextRef.current = "";
      liveSourcesRef.current = null;
      const userMessage: MessageOut = {
        id: `local-${Date.now()}`,
        role: "user",
        content,
        sources: null,
        created_at: new Date().toISOString(),
      };
      setMessages((msgs) => [...(msgs ?? []), userMessage]);
      void sendMessage(id, content);
    },
    [id, sendMessage],
  );

  // Load history, then fire the pending first message (from /chat) if any.
  useEffect(() => {
    let cancelled = false;
    setMessages(null);
    setNotFound(false);
    (async () => {
      try {
        const detail = await api.get<ConversationDetail>(
          `/api/conversations/${id}`,
        );
        if (cancelled) return;
        setMessages(detail.messages);
        if (!sentPendingRef.current) {
          sentPendingRef.current = true;
          const pending = takePendingMessage(id);
          if (pending) send(pending);
        }
      } catch (e) {
        if (!cancelled && isApiClientError(e) && e.status === 404) {
          setNotFound(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // `send` is stable per conversation id.
  }, [id, send]);

  // Keep the newest content in view.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, stream.streamedText, stream.sources]);

  if (notFound) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center">
        <h1 className="text-lg font-semibold text-zinc-100">
          Conversation not found
        </h1>
        <p className="mt-2 text-sm text-zinc-400">
          It may have been deleted.
        </p>
        <Link
          href="/chat"
          className="mt-4 text-sm font-medium text-indigo-400 hover:text-indigo-300"
        >
          Start a new chat
        </Link>
      </div>
    );
  }

  if (messages === null) {
    return (
      <div className="flex h-full items-center justify-center text-zinc-500">
        <Spinner size="lg" />
      </div>
    );
  }

  const showLiveBubble =
    stream.isStreaming || stream.streamedText.length > 0 || stream.sources !== null;

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-3xl flex-col gap-5 px-6 py-8">
          {messages.map((message) => (
            <ChatMessage
              key={message.id}
              role={message.role}
              content={message.content}
              sources={message.sources}
            />
          ))}

          {showLiveBubble && (
            <ChatMessage
              role="assistant"
              content={stream.streamedText}
              sources={stream.sources}
              streaming={stream.isStreaming}
            />
          )}

          {stream.isStreaming &&
            stream.streamedText.length === 0 &&
            stream.sources === null && (
              <div className="flex items-center gap-2 text-xs text-zinc-500">
                <Spinner size="sm" />
                Searching your documents…
              </div>
            )}

          {stream.error && (
            <div
              role="alert"
              className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300"
            >
              {stream.error.code === "rate_limited"
                ? "You're sending messages too quickly. Wait a moment and try again."
                : stream.error.detail}
            </div>
          )}
        </div>
      </div>

      <div className="mx-auto w-full max-w-3xl px-6 pb-6">
        <ChatInput
          onSend={send}
          disabled={stream.isStreaming}
          autoFocus
        />
      </div>
    </div>
  );
}
