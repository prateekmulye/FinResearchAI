import { type LucideIcon } from "lucide-react";
import { type ReactNode } from "react";

import { GlassCard } from "@/components/ui/glass-card";

/**
 * EmptyState — the "designed placeholder" for pages WP-7..10 will fill. It
 * describes what lands here (never lorem) so navigation feels real and the
 * roadmap is legible to a recruiter clicking around.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  children,
  badge,
}: {
  icon: LucideIcon;
  title: string;
  description: ReactNode;
  children?: ReactNode;
  badge?: string;
}) {
  return (
    <GlassCard className="flex flex-col items-center gap-5 py-14 text-center">
      <span className="relative flex size-14 items-center justify-center rounded-2xl bg-[var(--color-glass-strong)] ring-1 ring-[var(--color-glass-border)]">
        <Icon className="size-6 text-[var(--color-accent)]" aria-hidden="true" />
      </span>
      <div className="max-w-md space-y-2">
        {badge && (
          <p className="font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]">
            {badge}
          </p>
        )}
        <h2 className="text-lg font-semibold text-[var(--color-fg)]">{title}</h2>
        <p className="text-sm leading-relaxed text-[var(--color-fg-muted)]">
          {description}
        </p>
      </div>
      {children}
    </GlassCard>
  );
}
