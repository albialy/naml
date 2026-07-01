import React from 'react';
import { cn } from '../../lib/utils';
import { motion, HTMLMotionProps } from 'motion/react';
import { Spinner } from './Spinner';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', isLoading, children, ...props }, ref) => {
    const baseStyles = "relative inline-flex items-center justify-center rounded-2xl font-medium transition-all duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50 disabled:pointer-events-none disabled:opacity-50 backdrop-blur-xl border overflow-hidden";

    const variants = {
      primary: "bg-[#F5A623]/90 text-black border-amber-300/40 shadow-[0_8px_32px_rgba(245,166,35,0.35)] hover:bg-[#F5A623] hover:shadow-[0_8px_40px_rgba(245,166,35,0.5)]",
      secondary: "bg-white/5 text-white border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.3)] hover:bg-white/10",
      danger: "bg-red-500/10 text-red-400 border-red-500/20 shadow-[0_8px_32px_rgba(239,68,68,0.2)] hover:bg-red-500/20",
      ghost: "bg-transparent border-transparent text-gray-300 hover:bg-white/5 hover:text-white hover:border-white/10",
      outline: "bg-white/[0.02] border-white/15 text-white hover:bg-white/10"
    };

    const sizes = {
      sm: "h-8 px-3 text-xs",
      md: "h-10 px-4 py-2 text-sm",
      lg: "h-12 px-8 text-base"
    };

    return (
      <motion.button
        whileTap={{ scale: 0.97 }}
        whileHover={{ scale: 1.01 }}
        ref={ref}
        className={cn(baseStyles, variants[variant], sizes[size], className)}
        disabled={isLoading || props.disabled}
        {...(props as any)}
      >
        {/* Specular highlight on top edge */}
        <span className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/40 to-transparent" />
        {isLoading ? (
          <span className="flex items-center gap-2">
             <Spinner size="sm" className="text-current border-t-transparent" />
             {children}
          </span>
        ) : children}
      </motion.button>
    );
  }
);

Button.displayName = 'Button';
