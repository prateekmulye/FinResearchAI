/**
 * MethodologyTape — the portfolio's credibility signature, by design.
 *
 * The brief mandates the PROXY honesty cue ride prominently. The trap is making
 * it read as an error/warning (amber alarm), which triggers anxiety instead of
 * trust (NotebookLM). So this is framed as a confident "methodology note": a
 * flask glyph, a neutral azure-tinted glass tape with the grain texture (the
 * "methodology paper" feel), a one-line headline, and the full caveat in a
 * collapsible — Onion-Peel disclosure so the detail is there for the skeptic
 * without taxing the casual reader.
 */
import { FlaskConical } from "lucide-react";
import { useId, useState } from "react";

import { PROXY_BODY, PROXY_HEADLINE } from "./evalFormat";

export function MethodologyTape() {
  const [open, setOpen] = useState(false);
  const bodyId = useId();

  return (
    <div
      className="grain relative overflow-hidden rounded-xl border px-4 py-3"
      style={{
        borderColor: "var(--color-accent)",
        // A faint azure wash — informational, not alarming. Distinct from the
        // amber keyword-fallback banner (which signals a real degradation).
        background:
          "linear-gradient(0deg, oklch(70% 0.13 245 / 7%), oklch(70% 0.13 245 / 7%))",
      }}
      role="note"
      aria-label="Methodology and honesty disclaimer"
    >
      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg"
          style={{
            background: "oklch(70% 0.13 245 / 14%)",
            color: "var(--color-accent-strong)",
          }}
        >
          <FlaskConical className="size-4" aria-hidden="true" />
        </span>

        <div className="min-w-0 flex-1">
          <p className="font-mono text-2xs font-medium uppercase tracking-[0.16em] text-[var(--color-accent-strong)]">
            Methodology
          </p>
          <p className="mt-1 text-sm font-medium leading-snug text-[var(--color-fg)]">
            {PROXY_HEADLINE}
          </p>

          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-controls={bodyId}
            className="mt-1.5 font-mono text-2xs tracking-wide text-[var(--color-fg-muted)] underline-offset-2 transition-colors hover:text-[var(--color-fg)] hover:underline"
          >
            {open ? "− what this measures" : "+ what this measures (and what it doesn't)"}
          </button>

          {open && (
            <p
              id={bodyId}
              className="mt-2 max-w-3xl text-xs leading-relaxed text-[var(--color-fg-muted)]"
            >
              {PROXY_BODY}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
