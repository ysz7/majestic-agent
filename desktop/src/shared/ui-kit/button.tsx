import { cn } from "@shared/lib/cn";
import { type ButtonHTMLAttributes, forwardRef } from "react";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "cta" | "ghost";
  size?: "sm" | "md";
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "md", ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center font-[inherit] cursor-pointer transition-colors",
          // sizes
          size === "sm" && "text-base px-3 py-2 rounded-control",
          size === "md" && "text-md px-4 py-2 rounded-control",
          // variants — all using template tokens
          variant === "default" &&
            "bg-bg-elevated text-text-dim border border-border hover:border-border-strong hover:text-text-sub",
          variant === "cta" &&
            "bg-cta-bg text-cta-text font-semibold border-0 hover:opacity-90",
          variant === "ghost" &&
            "bg-transparent text-text-muted border border-transparent hover:border-border hover:text-text-sub",
          className,
        )}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
