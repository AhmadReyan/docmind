"use client";

import { useEffect, useRef, useState } from "react";
import type { Source } from "@/lib/api-types";
import { cn } from "@/lib/cn";
import { SourceCard, SourceChipCard } from "@/components/chat/source-card";

const CITATION_PATTERN = /\[(\d+)\]/g;

export interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  sources: Source[] | null;
  /** Renders a blinking cursor after the content (live assistant stream). */
  streaming?: boolean;
}

type Segment =
  | { kind: "text"; text: string }
  | { kind: "citation"; index: number; source: Source };

function segmentContent(content: string, sources: Source[] | null): Segment[] {
  const bySourceIndex = new Map<number, Source>(
    (sources ?? []).map((s) => [s.index, s]),
  );
  const segments: Segment[] = [];
  let cursor = 0;
  for (const match of content.matchAll(CITATION_PATTERN)) {
    const matchStart = match.index;
    const index = Number.parseInt(match[1], 10);
    const source = bySourceIndex.get(index);
    if (!source) continue; // No matching source: leave the marker as text.
    if (matchStart > cursor) {
      segments.push({ kind: "text", text: content.slice(cursor, matchStart) });
    }
    segments.push({ kind: "citation", index, source });
    cursor = matchStart + match[0].length;
  }
  if (cursor < content.length) {
    segments.push({ kind: "text", text: content.slice(cursor) });
  }
  return segments;
}

export function ChatMessage({
  role,
  content,
  sources,
  streaming = false,
}: ChatMessageProps) {
  const [openCitation, setOpenCitation] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close the popover on any outside click.
  useEffect(() => {
    if (openCitation === null) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpenCitation(null);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [openCitation]);

  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2.5 text-sm leading-relaxed text-white">
          {content}
        </div>
      </div>
    );
  }

  const segments = segmentContent(content, sources);

  return (
    <div ref={containerRef} className="flex justify-start">
      <div className="max-w-[85%]">
        <div className="rounded-2xl rounded-bl-sm border border-zinc-800 bg-zinc-900/70 px-4 py-2.5 text-sm leading-relaxed text-zinc-200">
          <span className="whitespace-pre-wrap">
            {segments.map((segment, i) =>
              segment.kind === "text" ? (
                <span key={i}>{segment.text}</span>
              ) : (
                <span key={i} className="relative inline-block">
                  <button
                    type="button"
                    onClick={() =>
                      setOpenCitation((open) =>
                        open === segment.index ? null : segment.index,
                      )
                    }
                    aria-label={`Citation ${segment.index}: ${segment.source.document_title}`}
                    aria-expanded={openCitation === segment.index}
                    className={cn(
                      "mx-0.5 inline-flex h-4 min-w-4 -translate-y-1 items-center justify-center rounded px-1 align-baseline text-[10px] font-semibold transition-colors",
                      openCitation === segment.index
                        ? "bg-indigo-500 text-white"
                        : "bg-indigo-500/20 text-indigo-300 hover:bg-indigo-500/40",
                    )}
                  >
                    {segment.index}
                  </button>
                  {openCitation === segment.index && (
                    <span className="absolute left-0 top-full z-30 mt-1.5 block animate-fade-in-up">
                      <SourceCard source={segment.source} />
                    </span>
                  )}
                </span>
              ),
            )}
            {streaming && (
              <span
                className="ml-0.5 inline-block h-4 w-2 translate-y-0.5 animate-blink bg-indigo-400"
                aria-hidden="true"
              />
            )}
          </span>
        </div>

        {sources && sources.length > 0 && (
          <div className="mt-2">
            <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
              Sources
            </p>
            <div className="flex flex-wrap gap-1.5">
              {sources.map((source) => (
                <SourceChipCard key={source.index} source={source} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
