/**
 * JudgeBadges — the A/B legend and the per-pair judge chip. Both read their
 * color from judgeChrome.ts so the scatter, the legend, and the table speak one
 * visual language (Gestalt similarity). The legend is what makes "debate ON vs
 * OFF" instantly legible to a recruiter who's never seen the repo.
 */
import type { JudgePreferred } from "./evalFormat";
import { judgeColor, judgeLabel } from "./judgeChrome";

/** A swatch + caption explaining what each scatter-point color means. */
export function JudgeLegend() {
  const items: { pref: JudgePreferred; caption: string }[] = [
    { pref: "on", caption: "judge prefers debate" },
    { pref: "off", caption: "judge prefers baseline" },
    { pref: "tie", caption: "tie / wash" },
    { pref: null, caption: "not refereed" },
  ];
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5" aria-label="Legend: scatter point color by judge preference">
      {items.map((it) => (
        <li
          key={it.caption}
          className="flex items-center gap-1.5 font-mono text-2xs text-[var(--color-fg-muted)]"
        >
          <span
            aria-hidden="true"
            className="size-2.5 rounded-full"
            style={{
              background: judgeColor(it.pref),
              boxShadow: it.pref ? `0 0 6px -1px ${judgeColor(it.pref)}` : undefined,
            }}
          />
          {it.caption}
        </li>
      ))}
    </ul>
  );
}

/** The per-pair judge-preference chip (table cell). Color + word, never color
 *  alone, plus an optional confidence readout. */
export function JudgePrefChip({
  pref,
  confidence,
}: {
  pref: JudgePreferred;
  confidence: number | null;
}) {
  const color = judgeColor(pref);
  const word =
    pref === "on" ? "on" : pref === "off" ? "off" : pref === "tie" ? "tie" : "—";
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-2xs tracking-wide"
      style={{
        color: pref ? color : "var(--color-fg-subtle)",
        background: pref ? "var(--color-glass)" : "transparent",
        border: `1px solid ${pref ? color : "var(--color-line)"}`,
      }}
      aria-label={judgeLabel(pref)}
    >
      <span aria-hidden="true">{word}</span>
      {confidence != null && (
        <span className="tabular-nums text-[var(--color-fg-subtle)]">
          {Math.round(confidence * 100)}%
        </span>
      )}
    </span>
  );
}
