import { GlassCard } from "@/components/ui/glass-card";

/**
 * RouteFallback — the suspense skeleton shown while a lazily-loaded page chunk
 * resolves. A trio of shimmering glass bars; never a jarring blank flash.
 */
export function RouteFallback() {
  return (
    <div className="space-y-8" aria-busy="true" aria-label="Loading page">
      <div className="space-y-3">
        <div className="h-3 w-32 animate-breathe rounded bg-[var(--color-glass-strong)]" />
        <div className="h-8 w-2/3 rounded bg-[var(--color-glass)]" />
      </div>
      <GlassCard className="h-40 animate-breathe" />
    </div>
  );
}
