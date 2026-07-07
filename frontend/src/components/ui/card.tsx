import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export function Card({
  className,
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xl border border-zinc-800 bg-zinc-900/70 shadow-sm",
        className,
      )}
      {...rest}
    />
  );
}

export function CardHeader({
  className,
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("border-b border-zinc-800 px-5 py-4", className)}
      {...rest}
    />
  );
}

export function CardBody({
  className,
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-5 py-4", className)} {...rest} />;
}
