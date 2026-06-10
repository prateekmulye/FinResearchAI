import { type HTMLAttributes, forwardRef } from "react";

import { cn } from "@/lib/utils";

/**
 * GlassCard — the SaaS-shell container. Terminal tiles and dense data live
 * INSIDE these (the nested hierarchy: glass moderates the technical noise).
 */
export const GlassCard = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("glass rounded-2xl p-5 sm:p-6", className)}
      {...props}
    />
  ),
);
GlassCard.displayName = "GlassCard";
