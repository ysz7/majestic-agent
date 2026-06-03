import { cn } from "@shared/lib/cn";
import type { HTMLAttributes } from "react";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "live" | "active";
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center text-2xs font-semibold uppercase tracking-[1.2px] px-[7px] py-[5px] rounded-badge whitespace-nowrap",
        variant === "default" && "bg-bg-elevated text-text-dim border border-border",
        variant === "live"    && "bg-bg-elevated text-text-sub border border-border",
        variant === "active"  && "bg-bg-selected text-text-bright border border-border-strong",
        className,
      )}
      {...props}
    />
  );
}
