"use client";

import { useEffect, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  className,
}: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={cn(
          "relative w-full max-w-md animate-fade-in-up rounded-xl border border-zinc-800 bg-zinc-900 shadow-xl",
          className,
        )}
      >
        <div className="border-b border-zinc-800 px-5 py-4">
          <h2 className="text-sm font-semibold text-zinc-100">{title}</h2>
        </div>
        <div className="px-5 py-4 text-sm text-zinc-300">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-zinc-800 px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
