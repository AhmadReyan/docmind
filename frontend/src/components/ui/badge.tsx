import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type Tone = "gray" | "blue" | "green" | "red" | "indigo";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
  pulse?: boolean;
}

const TONE_CLASSES: Record<Tone, string> = {
  gray: "bg-zinc-800 text-zinc-300 border-zinc-700",
  blue: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  green: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  red: "bg-red-500/15 text-red-300 border-red-500/30",
  indigo: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
};

const DOT_CLASSES: Record<Tone, string> = {
  gray: "bg-zinc-400",
  blue: "bg-sky-400",
  green: "bg-emerald-400",
  red: "bg-red-400",
  indigo: "bg-indigo-400",
};

export function Badge({
  tone = "gray",
  pulse = false,
  className,
  children,
  ...rest
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        TONE_CLASSES[tone],
        className,
      )}
      {...rest}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          DOT_CLASSES[tone],
          pulse && "animate-pulse",
        )}
        aria-hidden="true"
      />
      {children}
    </span>
  );
}
