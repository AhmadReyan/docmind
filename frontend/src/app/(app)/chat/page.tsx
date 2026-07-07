"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ConversationOut } from "@/lib/api-types";
import { api } from "@/lib/api-client";
import { stashPendingMessage } from "@/lib/pending-message";
import { useApp } from "@/components/shell/app-shell";
import { ChatInput } from "@/components/chat/chat-input";
import { useToast } from "@/components/ui/toast";

export default function NewChatPage() {
  const router = useRouter();
  const { addConversation } = useApp();
  const { toast } = useToast();
  const [creating, setCreating] = useState(false);

  const startConversation = async (content: string) => {
    setCreating(true);
    try {
      const conversation = await api.post<ConversationOut>(
        "/api/conversations",
        {},
      );
      // The [id] page picks this up on mount and sends it as the first message.
      stashPendingMessage(conversation.id, content);
      addConversation(conversation);
      router.push(`/chat/${conversation.id}`);
    } catch {
      toast("Could not start a conversation. Please try again.", "error");
      setCreating(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        <div
          className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-500/15 text-xl"
          aria-hidden="true"
        >
          &#x1F4AC;
        </div>
        <h1 className="text-lg font-semibold text-zinc-100">
          Ask your documents anything
        </h1>
        <p className="mt-1 max-w-md text-sm text-zinc-400">
          Answers come with numbered citations you can click to see the exact
          passage they came from.
        </p>
      </div>
      <div className="mx-auto w-full max-w-3xl px-6 pb-6">
        <ChatInput
          onSend={(content) => void startConversation(content)}
          disabled={creating}
          autoFocus
        />
      </div>
    </div>
  );
}
