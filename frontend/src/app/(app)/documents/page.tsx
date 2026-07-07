"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import type { DocumentOut, Paginated } from "@/lib/api-types";
import { api, isApiClientError } from "@/lib/api-client";
import { formatBytes, formatDate } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Modal } from "@/components/ui/modal";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { DocumentStatusBadge } from "@/components/documents/status-badge";
import { UploadDropzone } from "@/components/documents/upload-dropzone";

const POLL_INTERVAL_MS = 2000;

const MIME_LABELS: Record<DocumentOut["mime_type"], string> = {
  "application/pdf": "PDF",
  "text/plain": "TXT",
  "text/markdown": "MD",
};

export default function DocumentsPage() {
  const { toast } = useToast();
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [pendingDelete, setPendingDelete] = useState<DocumentOut | null>(null);
  const [deleting, setDeleting] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchDocuments = useCallback(async () => {
    try {
      const page = await api.get<Paginated<DocumentOut>>(
        "/api/documents?limit=100&offset=0",
      );
      setDocuments(page.items);
    } catch {
      // Auth failures are handled by the shell guard; transient errors
      // will be retried by the next poll or manual action.
    }
  }, []);

  useEffect(() => {
    void fetchDocuments();
  }, [fetchDocuments]);

  // Poll every 2s while any document is still being ingested.
  const hasActive =
    documents?.some(
      (d) => d.status === "pending" || d.status === "processing",
    ) ?? false;

  useEffect(() => {
    if (!hasActive) return;
    pollTimer.current = setInterval(() => {
      void fetchDocuments();
    }, POLL_INTERVAL_MS);
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, [hasActive, fetchDocuments]);

  const uploadFile = useCallback(
    async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      try {
        const doc = await api.postForm<DocumentOut>("/api/documents", form);
        setDocuments((docs) => [doc, ...(docs ?? [])]);
        toast(`Uploaded "${file.name}" — ingestion started.`, "success");
      } catch (e) {
        if (isApiClientError(e)) {
          if (e.code === "file_too_large") {
            toast(`"${file.name}" is too large — the limit is 20 MB.`, "error");
          } else if (e.code === "unsupported_file_type") {
            toast(
              `"${file.name}" is not a supported file type (PDF, TXT, MD).`,
              "error",
            );
          } else {
            toast(e.detail, "error");
          }
        } else {
          toast(`Could not upload "${file.name}". Please try again.`, "error");
        }
      }
    },
    [toast],
  );

  const confirmDelete = useCallback(async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await api.del(`/api/documents/${pendingDelete.id}`);
      setDocuments((docs) =>
        (docs ?? []).filter((d) => d.id !== pendingDelete.id),
      );
      setPendingDelete(null);
      toast("Document deleted.", "success");
    } catch {
      toast("Could not delete the document. Please try again.", "error");
    } finally {
      setDeleting(false);
    }
  }, [pendingDelete, toast]);

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-zinc-100">Documents</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Upload documents, then ask questions about them in Chat.
        </p>
      </div>

      <UploadDropzone onFileAccepted={(file) => void uploadFile(file)} />

      <div className="mt-8">
        {documents === null ? (
          <div className="flex justify-center py-16 text-zinc-500">
            <Spinner size="lg" />
          </div>
        ) : documents.length === 0 ? (
          <Card className="px-6 py-12 text-center">
            <p className="text-sm text-zinc-400">
              No documents yet. Upload your first PDF, TXT, or MD file above.
            </p>
          </Card>
        ) : (
          <Card className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
                  <th className="px-4 py-3 font-medium">Title</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Size</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Chunks</th>
                  <th className="px-4 py-3 font-medium">Pages</th>
                  <th className="px-4 py-3 font-medium">Uploaded</th>
                  <th className="px-4 py-3" aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => (
                  <tr
                    key={doc.id}
                    className="border-b border-zinc-800/60 last:border-0 hover:bg-zinc-800/30"
                  >
                    <td className="max-w-[220px] px-4 py-3">
                      <Link
                        href={`/documents/${doc.id}`}
                        className="block truncate font-medium text-zinc-100 hover:text-indigo-300"
                        title={doc.filename}
                      >
                        {doc.title}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone="indigo">{MIME_LABELS[doc.mime_type]}</Badge>
                    </td>
                    <td className="px-4 py-3 text-zinc-400">
                      {formatBytes(doc.size_bytes)}
                    </td>
                    <td className="px-4 py-3">
                      <DocumentStatusBadge
                        status={doc.status}
                        errorMessage={doc.error_message}
                      />
                    </td>
                    <td className="px-4 py-3 text-zinc-400">
                      {doc.chunk_count ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-zinc-400">
                      {doc.page_count ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-zinc-400">
                      {formatDate(doc.created_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Delete ${doc.title}`}
                        onClick={() => setPendingDelete(doc)}
                        className="text-zinc-500 hover:text-red-400"
                      >
                        Delete
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>

      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title="Delete document"
        footer={
          <>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setPendingDelete(null)}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              size="sm"
              loading={deleting}
              onClick={confirmDelete}
            >
              Delete
            </Button>
          </>
        }
      >
        Delete{" "}
        <span className="font-medium text-zinc-100">
          &ldquo;{pendingDelete?.title}&rdquo;
        </span>
        ? Its chunks and stored file will be removed permanently.
      </Modal>
    </div>
  );
}
