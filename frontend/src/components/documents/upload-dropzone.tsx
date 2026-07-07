"use client";

import { useRef, useState, type DragEvent } from "react";
import { cn } from "@/lib/cn";
import { formatBytes } from "@/lib/format";

export const MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024;

const ALLOWED_EXTENSIONS = ["pdf", "txt", "md"] as const;
const ALLOWED_MIME_TYPES = [
  "application/pdf",
  "text/plain",
  "text/markdown",
] as const;

/** Returns a user-facing error message, or null if the file is acceptable. */
export function validateFile(file: File): string | null {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  const extensionOk = (ALLOWED_EXTENSIONS as readonly string[]).includes(
    extension,
  );
  const mimeOk =
    file.type !== "" &&
    (ALLOWED_MIME_TYPES as readonly string[]).includes(file.type);
  if (!extensionOk && !mimeOk) {
    return `"${file.name}" is not a supported file type. Upload a PDF, TXT, or MD file.`;
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return `"${file.name}" is ${formatBytes(file.size)} — the limit is 20 MB.`;
  }
  return null;
}

export interface UploadDropzoneProps {
  onFileAccepted: (file: File) => void;
  disabled?: boolean;
}

export function UploadDropzone({
  onFileAccepted,
  disabled = false,
}: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFiles = (files: FileList | File[]) => {
    setError(null);
    for (const file of Array.from(files)) {
      const problem = validateFile(file);
      if (problem) {
        setError(problem);
        continue;
      }
      onFileAccepted(file);
    }
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    if (disabled) return;
    if (e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  };

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload documents"
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (!disabled && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors",
          dragOver
            ? "border-indigo-400 bg-indigo-500/10"
            : "border-zinc-700 bg-zinc-900/40 hover:border-zinc-500",
          disabled && "cursor-not-allowed opacity-60",
        )}
      >
        <svg
          className="h-8 w-8 text-zinc-500"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" />
        </svg>
        <p className="text-sm text-zinc-300">
          <span className="font-medium text-indigo-400">Click to browse</span>{" "}
          or drag files here
        </p>
        <p className="text-xs text-zinc-500">PDF, TXT, or MD — up to 20 MB</p>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
          multiple
          className="hidden"
          data-testid="file-input"
          disabled={disabled}
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              handleFiles(e.target.files);
            }
            e.target.value = "";
          }}
        />
      </div>
      {error && (
        <p role="alert" className="mt-2 text-xs text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}
