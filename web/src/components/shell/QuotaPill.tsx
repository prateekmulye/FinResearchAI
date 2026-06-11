import { ShieldCheck, Zap, Archive, Infinity as InfinityIcon } from "lucide-react";

import { useQuota } from "@/hooks/useQuota";
import { type QuotaState } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Map each quota state to an icon + accent. Replay-only uses amber (a soft
 *  "caution", not an error) to steer the user toward the Library replays. */
function presentation(q: QuotaState): {
  Icon: typeof Zap;
  tint: string;
  ring: string;
} {
  switch (q.kind) {
    case "admin":
      return {
        Icon: InfinityIcon,
        tint: "var(--color-accent)",
        ring: "var(--color-accent)",
      };
    case "available":
      return { Icon: Zap, tint: "var(--color-bull)", ring: "var(--color-bull)" };
    case "replay-only":
      return { Icon: Archive, tint: "var(--color-hold)", ring: "var(--color-hold)" };
    case "unmetered":
      return {
        Icon: ShieldCheck,
        tint: "var(--color-fg-muted)",
        ring: "var(--color-line-strong)",
      };
    // "degraded" (counters unreadable — an outage, not exhaustion) and
    // "unknown" share the neutral treatment: never amber, never a dead wall.
    default:
      return {
        Icon: ShieldCheck,
        tint: "var(--color-fg-subtle)",
        ring: "var(--color-line)",
      };
  }
}

/**
 * QuotaPill — terminal-styled status chip reading /api/quota. Mono numerals,
 * tabular so the count never jitters when it ticks down between runs.
 */
export function QuotaPill() {
  const { quota } = useQuota();
  const { Icon, tint, ring } = presentation(quota);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1",
        "font-mono text-2xs font-medium tracking-tight",
        "bg-[var(--color-glass)] backdrop-blur-md",
      )}
      style={{ border: `1px solid ${ring}`, color: tint }}
      title={`Live-run quota: ${quota.label}`}
    >
      <Icon className="size-3" aria-hidden="true" />
      <span className="text-[var(--color-fg)]">{quota.label}</span>
    </span>
  );
}
