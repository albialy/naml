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
    const baseStyles = "inline-flex items-center justify-center rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 disabled:pointer-events-none disabled:opacity-50";
    
    const variants = {
      primary: "bg-[#F5A623] text-black hover:bg-[#d98f1b]",
      secondary: "bg-[#1E1E1E] text-white hover:bg-[#2A2A2A]",
      danger: "bg-red-500/10 text-red-500 hover:bg-red-500/20",
      ghost: "hover:bg-[#1E1E1E] text-gray-300 hover:text-white",
      outline: "border border-[#1E1E1E] bg-transparent hover:bg-[#1E1E1E] text-white"
    };
    
    const sizes = {
      sm: "h-8 px-3 text-xs",
      md: "h-10 px-4 py-2 text-sm",
      lg: "h-12 px-8 text-base"
    };

    return (
      <motion.button
        whileTap={{ scale: 0.98 }}
        ref={ref}
        className={cn(baseStyles, variants[variant], sizes[size], className)}
        disabled={isLoading || props.disabled}
        {...(props as any)}
      >
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
