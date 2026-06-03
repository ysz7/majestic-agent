import { cn } from "@shared/lib/cn";
import type { HTMLAttributes } from "react";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "border border-border rounded-card bg-card-gradient p-[10px]",
        className,
      )}
      {...props}
    />
  );
}

export function CardLabel({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "block text-2xs font-semibold uppercase tracking-[1.3px] text-text-muted-3",
        className,
      )}
      {...props}
    />
  );
}
