"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import type { ChunkOut, DocumentOut, Paginated } from "@/lib/api-types";
import { api, isApiClientError } from "@/lib/api-client";
import { formatBytes, formatDateTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { DocumentStatusBadge } from "@/components/documents/status-badge";

const PAGE_SIZE = 20;

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [doc, setDoc] = useState<DocumentOut | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [chunks, setChunks] = useState<Paginated<ChunkOut> | null>(null);
  const [page, setPage] = useState(0);
  const [loadingChunks, setLoadingChunks] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const d = await api.get<DocumentOut>(`/api/documents/${id}`);
        if (!cancelled) setDoc(d);
      } catch (e) {
        if (!cancelled && isApiClientError(e) && e.status === 404) {
          setNotFound(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const fetchChunks = useCallback(
    async (pageIndex: number) => {
      setLoadingChunks(true);
      try {
        const result = await api.get<Paginated<ChunkOut>>(
          `/api/documents/${id}/chunks?limit=${PAGE_SIZE}&offset=${pageIndex * PAGE_SIZE}`,
        );
        setChunks(result);
        setPage(pageIndex);
      } catch {
        // Keep the previous page on transient failure.
      } finally {
        setLoadingChunks(false);
      }
    },
    [id],
  );

  useEffect(() => {
    void fetchChunks(0);
  }, [fetchChunks]);

  if (notFound) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16 text-center">
        <h1 className="text-lg font-semibold text-zinc-100">
          Document not found
        </h1>
        <p className="mt-2 text-sm text-zinc-400">
          It may have been deleted, or the link is wrong.
        </p>
        <Link
          href="/documents"
          className="mt-4 inline-block text-sm font-medium text-indigo-400 hover:text-indigo-300"
        >
          Back to documents
        </Link>
      </div>
    );
  }

  if (!doc) {
    return (
      <div className="flex justify-center py-24 text-zinc-500">
        <Spinner size="lg" />
      </div>
    );
  }

  const totalPages = chunks ? Math.max(1, Math.ceil(chunks.total / PAGE_SIZE)) : 1;

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <Link
        href="/documents"
        className="text-xs font-medium text-zinc-500 hover:text-zinc-300"
      >
        &larr; All documents
      </Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-semibold text-zinc-100">
            {doc.title}
          </h1>
          <p className="mt-1 text-xs text-zinc-500">{doc.filename}</p>
        </div>
        <DocumentStatusBadge status={doc.status} errorMessage={doc.error_message} />
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
        <MetaItem label="Size" value={formatBytes(doc.size_bytes)} />
        <MetaItem label="Pages" value={doc.page_count?.toString() ?? "—"} />
        <MetaItem label="Chunks" value={doc.chunk_count?.toString() ?? "—"} />
        <MetaItem label="Uploaded" value={formatDateTime(doc.created_at)} />
      </dl>

      {doc.status === "failed" && doc.error_message && (
        <div
          role="alert"
          className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300"
        >
          Ingestion failed: {doc.error_message}
        </div>
      )}

      <div className="mt-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">
            Chunks{chunks ? ` (${chunks.total})` : ""}
          </h2>
          {chunks && chunks.total > PAGE_SIZE && (
            <div className="flex items-center gap-2 text-xs text-zinc-400">
              <Button
                variant="secondary"
                size="sm"
                disabled={page === 0 || loadingChunks}
                onClick={() => void fetchChunks(page - 1)}
              >
                Previous
              </Button>
              <span>
                Page {page + 1} of {totalPages}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={page + 1 >= totalPages || loadingChunks}
                onClick={() => void fetchChunks(page + 1)}
              >
                Next
              </Button>
            </div>
          )}
        </div>

        {!chunks ? (
          <div className="flex justify-center py-12 text-zinc-500">
            <Spinner />
          </div>
        ) : chunks.items.length === 0 ? (
          <Card className="px-6 py-10 text-center text-sm text-zinc-400">
            No chunks yet
            {doc.status === "pending" || doc.status === "processing"
              ? " — this document is still being processed."
              : "."}
          </Card>
        ) : (
          <div className="space-y-3">
            {chunks.items.map((chunk) => (
              <Card key={chunk.id}>
                <CardHeader className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2.5 text-xs text-zinc-500">
                  <span className="font-medium text-zinc-300">
                    Chunk {chunk.chunk_index}
                  </span>
                  {chunk.page_number !== null && (
                    <span>Page {chunk.page_number}</span>
                  )}
                  <span>{chunk.token_count} tokens</span>
                </CardHeader>
                <CardBody>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-300">
                    {chunk.content}
                  </p>
                </CardBody>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-zinc-500">
        {label}
      </dt>
      <dd className="mt-0.5 text-zinc-200">{value}</dd>
    </div>
  );
}
