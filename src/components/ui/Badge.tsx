import React from "react";
import { cn } from "../../lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "success" | "warning" | "danger" | "outline";
}

export function Badge({
  className,
  variant = "default",
  ...props
}: BadgeProps) {
  const variants = {
    default: "bg-[#cbddea] text-slate-800",
    success: "bg-green-500/10 text-emerald-700 border border-green-500/20",
    warning: "bg-amber-500/10 text-sky-700 border border-amber-500/20",
    danger: "bg-red-500/10 text-red-700 border border-red-500/20",
    outline: "border border-[#cbddea] text-[#617991]",
  };

  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
