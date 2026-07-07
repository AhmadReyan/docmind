"use client";

import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";
import { Spinner } from "@/components/ui/spinner";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "bg-indigo-600 text-white hover:bg-indigo-500 disabled:hover:bg-indigo-600 focus-visible:ring-indigo-400",
  secondary:
    "bg-zinc-800 text-zinc-100 border border-zinc-700 hover:bg-zinc-700 disabled:hover:bg-zinc-800 focus-visible:ring-zinc-500",
  ghost:
    "bg-transparent text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 focus-visible:ring-zinc-500",
  danger:
    "bg-red-600/90 text-white hover:bg-red-500 disabled:hover:bg-red-600/90 focus-visible:ring-red-400",
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-9 px-4 text-sm",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    { variant = "primary", size = "md", loading = false, className, children, disabled, ...rest },
    ref,
  ) {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950",
          "disabled:cursor-not-allowed disabled:opacity-60",
          VARIANT_CLASSES[variant],
          SIZE_CLASSES[size],
          className,
        )}
        {...rest}
      >
        {loading && <Spinner size="sm" />}
        {children}
      </button>
    );
  },
);
