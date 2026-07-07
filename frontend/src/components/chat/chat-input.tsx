"use client";

import {
  useCallback,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
} from "react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/button";

export const MAX_MESSAGE_LENGTH = 4000;
const MAX_TEXTAREA_HEIGHT_PX = 200;

export interface ChatInputProps {
  onSend: (content: string) => void;
  disabled?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = "Ask a question about your documents…",
  autoFocus = false,
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT_PX)}px`;
  }, []);

  const submit = useCallback(() => {
    const content = value.trim();
    if (content.length === 0 || content.length > MAX_MESSAGE_LENGTH || disabled) {
      return;
    }
    onSend(content);
    setValue("");
    requestAnimationFrame(() => {
      resize();
      textareaRef.current?.focus();
    });
  }, [value, disabled, onSend, resize]);

  const onChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value.slice(0, MAX_MESSAGE_LENGTH));
    resize();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const remaining = MAX_MESSAGE_LENGTH - value.length;
  const nearLimit = remaining <= 200;

  return (
    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-2 focus-within:border-indigo-500">
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={onChange}
        onKeyDown={onKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        autoFocus={autoFocus}
        maxLength={MAX_MESSAGE_LENGTH}
        aria-label="Message"
        className="max-h-[200px] w-full resize-none bg-transparent px-2 py-1.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none disabled:opacity-60"
      />
      <div className="flex items-center justify-between px-2 pt-1">
        <span
          className={cn(
            "text-[10px]",
            nearLimit ? "text-amber-400" : "text-zinc-600",
          )}
        >
          {nearLimit
            ? `${remaining} characters left`
            : "Enter to send · Shift+Enter for a new line"}
        </span>
        <Button
          size="sm"
          onClick={submit}
          disabled={disabled || value.trim().length === 0}
          aria-label="Send message"
        >
          Send
        </Button>
      </div>
    </div>
  );
}
