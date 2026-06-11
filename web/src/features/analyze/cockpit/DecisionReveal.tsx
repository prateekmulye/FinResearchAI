/**
 * DecisionReveal — the Peak. When `done` lands, the verdict materializes in a
 * restrained, deliberate sequence (Peak-End Rule, no confetti):
 *
 *   T+0    SignalBadge springs in (scale 0.92 -> 1)
 *   T+50   radial ConvictionGauge sweeps (stroke-dashoffset, 350ms)
 *   T+100  the 0..100 score counts up (rAF, tabular, no jitter)
 *   then   the rationale line, then the full markdown report + copy button.
 *
 * Reduced-motion shows everything in its final state immediately. The whole
 * block lives ABOVE the report so the strongest moment is never buried.
 */
import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { SignalBadge } from "@/components/ui/signal-badge";
import type { AnalysisDone } from "@/hooks/useAnalysisStream";
import type { FinalDecision } from "@/lib/api";

import { ConvictionGauge } from "./ConvictionGauge";
import { Markdown } from "./MarkdownView";
import { useCountUp } from "./useCountUp";

function ScoreCountUp({ score }: { score: number }) {
  const ref = useCountUp(score, { duration: 300, active: true });
  return (
    <div className="flex flex-col">
      <span className="font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]">
        Outlook score
      </span>
      {/* Screen readers hear the FINAL value once; the rAF count-up below is
          decorative and aria-hidden — a live region on a per-frame textContent
          mutation would announce dozens of intermediate numbers. */}
      <span className="sr-only" aria-live="polite">
        {score}
        /100
      </span>
      <span className="flex items-baseline gap-0.5" aria-hidden="true">
        <span
          ref={ref}
          className="font-mono text-4xl font-semibold tabular-nums text-[var(--color-fg)]"
          style={{ willChange: "contents" }}
        >
          0
        </span>
        <span className="font-mono text-lg text-[var(--color-fg-subtle)]">/100</span>
      </span>
    </div>
  );
}

function CopyMarkdownButton({ markdown }: { markdown: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable — silently no-op */
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-strong)] bg-[var(--color-surface-2)] px-3 py-1.5 font-mono text-2xs uppercase tracking-[0.14em] text-[var(--color-fg-muted)] transition-colors hover:text-[var(--color-fg)]"
    >
      {copied ? (
        <>
          <Check className="size-3.5 text-[var(--color-bull)]" aria-hidden="true" />
          Copied
        </>
      ) : (
        <>
          <Copy className="size-3.5" aria-hidden="true" />
          Copy markdown
        </>
      )}
    </button>
  );
}

export function DecisionReveal({
  done,
  ticker,
}: {
  done: AnalysisDone;
  ticker: string | null;
}) {
  const decision: FinalDecision | null = done.finalDecision;
  if (!decision) {
    // A done with no decision (degraded arbiter) — still show the report.
    return (
      <article className="glass animate-verdict-in rounded-2xl p-5 sm:p-6">
        <ReportBlock markdown={done.finalReport} />
      </article>
    );
  }

  return (
    <article
      className="glass animate-verdict-in rounded-2xl p-5 sm:p-7"
      aria-label="Final verdict"
    >
      <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
        <ConvictionGauge
          conviction={decision.conviction}
          action={decision.action}
          active
        />
        <div className="flex flex-1 flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <SignalBadge action={decision.action} size="lg" />
            <span className="font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]">
              {ticker} · final decision
            </span>
          </div>
          <ScoreCountUp score={decision.score} />
          <p className="max-w-2xl text-sm leading-relaxed text-[var(--color-fg-muted)]">
            {decision.rationale}
          </p>
        </div>
      </div>

      <hr className="my-6 border-[var(--color-line)]" />
      <ReportBlock markdown={done.finalReport} />
    </article>
  );
}

function ReportBlock({ markdown }: { markdown: string }) {
  if (!markdown?.trim()) return null;
  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-accent)]">
          Investment report
        </h3>
        <CopyMarkdownButton markdown={markdown} />
      </div>
      <Markdown source={markdown} />
    </div>
  );
}
