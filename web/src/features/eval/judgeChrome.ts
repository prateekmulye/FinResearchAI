/**
 * judgeChrome — the shared visual DNA of the A/B comparison: how a judge
 * preference is colored, everywhere it appears (scatter points, table chips,
 * the legend). Kept as a pure `.ts` so both the chart and the table import it
 * without tripping react-refresh (components live in JudgeBadges.tsx).
 *
 * The mapping IS the A/B legend a recruiter reads in one glance:
 *   on  → bull green  (debate won)
 *   off → bear red    (baseline won)
 *   tie → amber hold  (a wash)
 *   null→ dim         (never refereed)
 */
import type { JudgePreferred } from "./evalFormat";

export function judgeColor(pref: JudgePreferred): string {
  switch (pref) {
    case "on":
      return "var(--color-bull)";
    case "off":
      return "var(--color-bear)";
    case "tie":
      return "var(--color-hold)";
    default:
      return "var(--color-fg-subtle)";
  }
}

/** The human label for a preference, used in chips and aria. */
export function judgeLabel(pref: JudgePreferred): string {
  switch (pref) {
    case "on":
      return "prefers debate";
    case "off":
      return "prefers baseline";
    case "tie":
      return "tie";
    default:
      return "unjudged";
  }
}
