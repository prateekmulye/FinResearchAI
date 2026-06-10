import { cva, type VariantProps } from "class-variance-authority";
import { type ButtonHTMLAttributes, forwardRef } from "react";

import { cn } from "@/lib/utils";

/**
 * Button — the shell's primary affordance. The `primary` variant uses the azure
 * functional accent; `signal` variants exist for verdict-styled actions later.
 * Motion: 120ms press scale, spring easing — shared physics language.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium " +
    "transition-[transform,background-color,box-shadow,border-color] duration-[120ms] ease-[var(--ease-spring)] " +
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)] " +
    "disabled:pointer-events-none disabled:opacity-50 active:scale-[0.97] " +
    "[&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "bg-[var(--color-accent)] text-[var(--color-accent-fg)] font-semibold " +
          "hover:bg-[var(--color-accent-strong)] hover:shadow-[var(--shadow-glow-accent)]",
        glass: "glass text-[var(--color-fg)] hover:bg-[var(--color-glass-strong)]",
        ghost:
          "text-[var(--color-fg-muted)] hover:text-[var(--color-fg)] hover:bg-[var(--color-glass)]",
        outline:
          "border border-[var(--color-line-strong)] bg-transparent text-[var(--color-fg)] " +
          "hover:bg-[var(--color-glass)] hover:border-[var(--color-glass-border)]",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-10 px-4",
        lg: "h-12 px-6 text-base",
        icon: "size-10",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends
    ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  ),
);
Button.displayName = "Button";

// Co-exported for link-styled-as-button usage (shadcn convention).
// eslint-disable-next-line react-refresh/only-export-components
export { buttonVariants };
