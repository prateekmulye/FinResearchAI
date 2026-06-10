/**
 * AnalystTrio — three compact terminal tiles, one per analyst. While a node
 * runs it streams its token text (mono, auto-scrolling, older lines fading); on
 * completion it flips to the structured summary + key points + confidence chip,
 * read from the node's `analyst_reports` delta.
 */
import { ConfidenceChip, KeyPoints, Tile, TokenStream } from "./panelKit";
import type { AnalystPanel } from "./pipeline";

const ACCENT = "var(--color-accent)";

function AnalystCard({ panel, title }: { panel: AnalystPanel; title: string }) {
  const showStructured = panel.status === "complete" && panel.summary;
  return (
    <Tile title={title} phase="Analyst" status={panel.status} accent={ACCENT} flash>
      {showStructured ? (
        <div className="animate-rise-in">
          <p className="text-xs leading-relaxed text-[var(--color-fg-muted)]">
            {panel.summary}
          </p>
          <KeyPoints points={panel.keyPoints} />
          <div className="mt-2.5">
            <ConfidenceChip value={panel.confidence} />
          </div>
        </div>
      ) : panel.status === "complete" ? (
        // Completed without a structured report — the node degraded. Amber is
        // the DESIGN token for warn/degraded; never show a check + "analyzing…".
        <p className="font-mono text-xs text-[var(--color-hold)]">
          no report — degraded
        </p>
      ) : panel.status === "pending" ? (
        <p className="font-mono text-xs text-[var(--color-fg-subtle)]">
          awaiting router…
        </p>
      ) : panel.text ? (
        <TokenStream text={panel.text} />
      ) : (
        <p className="font-mono text-xs text-[var(--color-fg-subtle)]">
          analyzing…
        </p>
      )}
    </Tile>
  );
}

export function AnalystTrio({
  news,
  fundamentals,
  technicals,
}: {
  news: AnalystPanel;
  fundamentals: AnalystPanel;
  technicals: AnalystPanel;
}) {
  return (
    <section aria-label="Analysts" className="space-y-2.5">
      <h3 className="font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]">
        Analysts
      </h3>
      <div className="grid gap-3 sm:grid-cols-3">
        <AnalystCard panel={news} title="News" />
        <AnalystCard panel={fundamentals} title="Fundamentals" />
        <AnalystCard panel={technicals} title="Technicals" />
      </div>
    </section>
  );
}
