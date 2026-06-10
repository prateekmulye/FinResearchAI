/**
 * DebateTheater — the centerpiece. Bull (green, left) vs Bear (red, right)
 * stream their theses; when the facilitator completes, the verdict lands as a
 * center bridge card that reads as a *synthesis* of the two columns — the
 * Climax/Resolution of the run (NLM: opposition -> convergence). The two side
 * columns are visually isolated by their signal-coloured borders (Von Restorff).
 *
 * Debate-off collapses to a single Research Synthesis tile (same verdict slot).
 */
import { ArrowDownRight, ArrowUpRight, Scale } from "lucide-react";

import { cn } from "@/lib/utils";

import { Tile, TokenStream } from "./panelKit";
import type { DebatePanel, NodeStatus } from "./pipeline";

const BULL = "var(--color-bull)";
const BEAR = "var(--color-bear)";

function ThesisColumn({
  side,
  status,
  text,
  thesis,
}: {
  side: "bull" | "bear";
  status: NodeStatus;
  text: string;
  thesis: string | null;
}) {
  const tint = side === "bull" ? BULL : BEAR;
  const Icon = side === "bull" ? ArrowUpRight : ArrowDownRight;
  const settled = status === "complete" && thesis;
  return (
    <Tile
      title={side === "bull" ? "Bull" : "Bear"}
      phase="Researcher"
      status={status}
      accent={tint}
      flash
      className="min-h-[7.5rem]"
    >
      <div className="mb-1.5 flex items-center gap-1">
        <Icon className="size-3.5" style={{ color: tint }} aria-hidden="true" />
        <span
          className="font-mono text-2xs uppercase tracking-[0.16em]"
          style={{ color: tint }}
        >
          {side === "bull" ? "Accumulate" : "Patience"}
        </span>
      </div>
      {settled ? (
        <p className="animate-rise-in text-xs leading-relaxed text-[var(--color-fg-muted)]">
          {thesis}
        </p>
      ) : status === "pending" ? (
        <p className="font-mono text-xs text-[var(--color-fg-subtle)]">
          awaiting analysts…
        </p>
      ) : text ? (
        <TokenStream text={text} />
      ) : (
        <p className="font-mono text-xs text-[var(--color-fg-subtle)]">
          building thesis…
        </p>
      )}
    </Tile>
  );
}

function VerdictBridge({
  status,
  text,
  label,
}: {
  status: NodeStatus;
  text: string;
  label: string;
}) {
  const settled = status === "complete" && text;
  return (
    <div
      className={cn(
        "grain relative flex flex-col justify-center rounded-xl border px-4 py-3.5",
        settled && "animate-verdict-in",
      )}
      style={{
        borderColor:
          status === "complete"
            ? "var(--color-accent)"
            : status === "running"
              ? "var(--color-accent)"
              : "var(--color-line)",
        background: "var(--color-surface-2)",
        boxShadow:
          status === "complete"
            ? "0 0 0 1px var(--color-accent), 0 0 28px -10px var(--color-accent)"
            : "none",
      }}
    >
      <div className="mb-1.5 flex items-center gap-1.5">
        <Scale className="size-3.5 text-[var(--color-accent)]" aria-hidden="true" />
        <span className="font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-accent)]">
          {label}
        </span>
      </div>
      {settled ? (
        <p className="text-xs leading-relaxed text-[var(--color-fg)]">{text}</p>
      ) : status === "running" ? (
        <p className="font-mono text-xs text-[var(--color-fg-subtle)]">
          weighing the debate…
        </p>
      ) : (
        <p className="font-mono text-xs text-[var(--color-fg-subtle)]">
          verdict pending
        </p>
      )}
    </div>
  );
}

export function DebateTheater({ panel }: { panel: DebatePanel }) {
  if (panel.mode === "off") {
    return (
      <section aria-label="Research synthesis" className="space-y-2.5">
        <h3 className="font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]">
          Research · synthesis (debate off)
        </h3>
        <VerdictBridge
          status={panel.verdict.status}
          text={panel.verdict.text}
          label="Synthesis verdict"
        />
      </section>
    );
  }

  return (
    <section aria-label="Bull versus bear debate" className="space-y-2.5">
      <h3 className="font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]">
        Debate theater · bull vs bear
      </h3>
      <div className="grid items-stretch gap-3 lg:grid-cols-[1fr_1.1fr_1fr]">
        <ThesisColumn
          side="bull"
          status={panel.bull.status}
          text={panel.bull.text}
          thesis={panel.bull.thesis}
        />
        <VerdictBridge
          status={panel.verdict.status}
          text={panel.verdict.text}
          label="Facilitator verdict"
        />
        <ThesisColumn
          side="bear"
          status={panel.bear.status}
          text={panel.bear.text}
          thesis={panel.bear.thesis}
        />
      </div>
    </section>
  );
}
