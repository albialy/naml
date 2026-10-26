import React from "react";
import { cn } from "../../lib/utils";

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-11 w-full rounded-2xl border border-sky-200/60 bg-white/[0.03] backdrop-blur-xl px-4 py-2 text-sm text-slate-800 placeholder:text-slate-800/40 shadow-[inset_0_1px_2px_rgba(49,97,137,0.06)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#168bd2]/50 focus-visible:border-[#168bd2]/40 focus-visible:bg-white/[0.05] disabled:cursor-not-allowed disabled:opacity-50 transition-all duration-300",
          className,
        )}
        ref={ref}
        {...props}
      />
    );
  },
);

Input.displayName = "Input";
