/**
 * TradeRisk — the trade proposal + the risk debate, the run's final
 * deliberation before the verdict. The trader's TradeProposal lands as a card;
 * the conservative and aggressive desks state opposing stances that the arbiter
 * resolves into the bridge card on the right (mirrors the debate theater's
 * opposition->synthesis shape).
 */
import { Flame, Scale, ShieldHalf } from "lucide-react";

import { SignalBadge } from "@/components/ui/signal-badge";
import { cn } from "@/lib/utils";

import { Tile, TokenStream } from "./panelKit";
import type { NodeStatus, RiskPanel, TradePanel } from "./pipeline";

function StanceTile({
  side,
  status,
  text,
  stance,
}: {
  side: "conservative" | "aggressive";
  status: NodeStatus;
  text: string;
  stance: string | null;
}) {
  const tint =
    side === "conservative"
      ? "var(--color-conservative)"
      : "var(--color-aggressive)";
  const Icon = side === "conservative" ? ShieldHalf : Flame;
  const settled = status === "complete" && stance;
  return (
    <Tile
      title={side === "conservative" ? "Conservative" : "Aggressive"}
      phase="Risk desk"
      status={status}
      accent={tint}
      flash
    >
      <div className="mb-1.5 flex items-center gap-1">
        <Icon className="size-3.5" style={{ color: tint }} aria-hidden="true" />
        <span
          className="font-mono text-2xs uppercase tracking-[0.16em]"
          style={{ color: tint }}
        >
          {side === "conservative" ? "Preserve" : "Press"}
        </span>
      </div>
      {settled ? (
        <p className="animate-rise-in text-xs leading-relaxed text-[var(--color-fg-muted)]">
          {stance}
        </p>
      ) : status === "pending" ? (
        <p className="font-mono text-xs text-[var(--color-fg-subtle)]">
          awaiting trade proposal…
        </p>
      ) : text ? (
        <TokenStream text={text} />
      ) : (
        <p className="font-mono text-xs text-[var(--color-fg-subtle)]">
          stating stance…
        </p>
      )}
    </Tile>
  );
}

function TradeCard({ trade }: { trade: TradePanel }) {
  const settled = trade.status === "complete" && trade.action;
  return (
    <Tile
      title="Trade proposal"
      phase="Trader"
      status={trade.status}
      accent="var(--color-accent)"
      flash
    >
      {settled ? (
        <div className="animate-rise-in space-y-2">
          <div className="flex items-center gap-2">
            <SignalBadge action={trade.action!} score={trade.score ?? undefined} />
            {trade.conviction != null && (
              <span className="font-mono text-2xs tabular-nums text-[var(--color-fg-subtle)]">
                conv {(trade.conviction * 100).toFixed(0)}%
              </span>
            )}
          </div>
          {trade.rationale && (
            <p className="text-xs leading-relaxed text-[var(--color-fg-muted)]">
              {trade.rationale}
            </p>
          )}
        </div>
      ) : trade.status === "pending" ? (
        <p className="font-mono text-xs text-[var(--color-fg-subtle)]">
          awaiting debate verdict…
        </p>
      ) : trade.text ? (
        <TokenStream text={trade.text} />
      ) : (
        <p className="font-mono text-xs text-[var(--color-fg-subtle)]">
          sizing the trade…
        </p>
      )}
    </Tile>
  );
}

function ArbiterBridge({
  status,
  text,
}: {
  status: NodeStatus;
  text: string;
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
          status === "complete" || status === "running"
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
          Arbiter resolution
        </span>
      </div>
      {settled ? (
        <p className="text-xs leading-relaxed text-[var(--color-fg)]">{text}</p>
      ) : status === "running" ? (
        <p className="font-mono text-xs text-[var(--color-fg-subtle)]">
          reconciling the desks…
        </p>
      ) : (
        <p className="font-mono text-xs text-[var(--color-fg-subtle)]">
          resolution pending
        </p>
      )}
    </div>
  );
}

export function TradeRisk({
  trade,
  risk,
}: {
  trade: TradePanel;
  risk: RiskPanel;
}) {
  return (
    <section aria-label="Trade and risk" className="space-y-2.5">
      <h3 className="font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]">
        Trade desk · risk arbitration
      </h3>
      <TradeCard trade={trade} />
      <div className="grid items-stretch gap-3 lg:grid-cols-[1fr_1.1fr_1fr]">
        <StanceTile
          side="conservative"
          status={risk.conservative.status}
          text={risk.conservative.text}
          stance={risk.conservative.stance}
        />
        <ArbiterBridge status={risk.arbiter.status} text={risk.arbiter.resolution ?? ""} />
        <StanceTile
          side="aggressive"
          status={risk.aggressive.status}
          text={risk.aggressive.text}
          stance={risk.aggressive.stance}
        />
      </div>
    </section>
  );
}
