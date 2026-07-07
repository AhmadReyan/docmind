"use client";

import Link from "next/link";
import type { Source } from "@/lib/api-types";

/** Full source details — used inside the citation-chip popover. */
export function SourceCard({ source }: { source: Source }) {
  return (
    <div className="w-72 rounded-lg border border-zinc-700 bg-zinc-900 p-3 text-left shadow-xl">
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 truncate text-xs font-semibold text-zinc-100">
          <span className="mr-1.5 text-indigo-400">[{source.index}]</span>
          {source.document_title}
        </p>
        <span className="shrink-0 text-[10px] text-zinc-500">
          score {source.score.toFixed(3)}
        </span>
      </div>
      {source.page_number !== null && (
        <p className="mt-0.5 text-[10px] uppercase tracking-wider text-zinc-500">
          Page {source.page_number}
        </p>
      )}
      <p className="mt-2 line-clamp-4 text-xs leading-relaxed text-zinc-400">
        {source.snippet}
      </p>
      <Link
        href={`/documents/${source.document_id}`}
        className="mt-2 inline-block text-xs font-medium text-indigo-400 hover:text-indigo-300"
      >
        Open document &rarr;
      </Link>
    </div>
  );
}

/** Compact numbered source — used in the "Sources" row under a message. */
export function SourceChipCard({ source }: { source: Source }) {
  return (
    <Link
      href={`/documents/${source.document_id}`}
      className="group flex max-w-[220px] items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/70 px-2.5 py-1.5 transition-colors hover:border-zinc-600"
      title={source.snippet}
    >
      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded bg-indigo-500/20 text-[10px] font-semibold text-indigo-300">
        {source.index}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-xs text-zinc-300 group-hover:text-zinc-100">
          {source.document_title}
        </span>
        {source.page_number !== null && (
          <span className="block text-[10px] text-zinc-500">
            Page {source.page_number}
          </span>
        )}
      </span>
    </Link>
  );
}
