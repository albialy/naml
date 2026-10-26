import React from "react";
import { cn } from "../../lib/utils";
import { Spinner } from "./Spinner";
export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost" | "outline";
  size?: "sm" | "md" | "lg";
  isLoading?: boolean;
}
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = "primary",
      size = "md",
      isLoading,
      children,
      disabled,
      ...props
    },
    ref,
  ) => {
    const variants = {
      primary:
        "bg-sky-600 text-white border-sky-500 shadow-sm hover:bg-sky-700",
      secondary: "bg-sky-100/70 text-sky-900 border-sky-200 hover:bg-sky-100",
      danger: "bg-red-50 text-red-700 border-red-200 hover:bg-red-100",
      ghost:
        "bg-transparent border-transparent text-slate-600 hover:bg-white/70",
      outline: "bg-white/50 border-sky-200 text-sky-900 hover:bg-white",
    };
    return (
      <button
        ref={ref}
        {...props}
        disabled={disabled || isLoading}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-xl border font-medium transition-colors disabled:opacity-50",
          variants[variant],
          {
            sm: "min-h-9 px-3 text-xs",
            md: "min-h-11 px-4 py-2 text-sm",
            lg: "min-h-12 px-6 text-base",
          }[size],
          className,
        )}
      >
        {isLoading && <Spinner size="sm" />}
        {children}
      </button>
    );
  },
);
Button.displayName = "Button";
