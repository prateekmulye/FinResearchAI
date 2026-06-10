import { useHealth, type HealthState } from "@/hooks/useHealth";
import { cn } from "@/lib/utils";

const CONFIG: Record<HealthState, { color: string; label: string; breathe: boolean }> =
  {
    ok: { color: "var(--color-bull)", label: "Backend live", breathe: true },
    down: { color: "var(--color-bear)", label: "Backend unreachable", breathe: false },
    checking: {
      color: "var(--color-fg-subtle)",
      label: "Checking backend…",
      breathe: false,
    },
  };

/**
 * HealthDot — a live liveness indicator polling /healthz. Never color alone:
 * pairs the dot with a sr-only + title label so the meaning survives without hue.
 */
export function HealthDot({ withLabel = false }: { withLabel?: boolean }) {
  const { state } = useHealth();
  const cfg = CONFIG[state];

  return (
    <span
      className="inline-flex items-center gap-2"
      title={cfg.label}
      role="status"
      aria-live="polite"
    >
      <span className="relative inline-flex size-2.5 items-center justify-center">
        {cfg.breathe && (
          <span
            className="absolute inline-flex size-full rounded-full opacity-60 animate-breathe"
            style={{ background: cfg.color }}
          />
        )}
        <span
          className="relative inline-flex size-2 rounded-full"
          style={{ background: cfg.color, boxShadow: `0 0 8px ${cfg.color}` }}
        />
      </span>
      <span
        className={cn(
          "text-2xs font-medium text-[var(--color-fg-muted)]",
          withLabel ? "inline" : "sr-only",
        )}
      >
        {cfg.label}
      </span>
    </span>
  );
}
