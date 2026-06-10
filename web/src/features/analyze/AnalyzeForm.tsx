import { Loader2, Search, Square } from "lucide-react";
import { type FormEvent, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { type DebateMode, type InvestorMode } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface AnalyzeFormValues {
  ticker: string;
  investorMode: InvestorMode;
  debateMode?: DebateMode;
}

const INVESTOR_MODES: InvestorMode[] = ["Neutral", "Bullish", "Bearish"];

/**
 * AnalyzeForm — the command bar that kicks off a run. Ticker is mono (it IS
 * data), the mode is a segmented control, and the debate toggle exposes the A/B
 * the project is built around. The CTA flips to a Stop affordance while active.
 */
export function AnalyzeForm({
  onSubmit,
  onStop,
  isActive,
  disabled,
}: {
  onSubmit: (values: AnalyzeFormValues) => void;
  onStop: () => void;
  isActive: boolean;
  disabled?: boolean;
}) {
  const tickerId = useId();
  const [ticker, setTicker] = useState("AAPL");
  const [investorMode, setInvestorMode] = useState<InvestorMode>("Neutral");
  const [debate, setDebate] = useState<"default" | DebateMode>("default");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = ticker.trim().toUpperCase();
    if (!trimmed) return;
    onSubmit({
      ticker: trimmed,
      investorMode,
      ...(debate !== "default" ? { debateMode: debate } : {}),
    });
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-4"
      aria-label="Start an equity analysis"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        {/* Ticker */}
        <div className="flex-1">
          <label
            htmlFor={tickerId}
            className="mb-1.5 block font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]"
          >
            Ticker
          </label>
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[var(--color-fg-subtle)]"
              aria-hidden="true"
            />
            <input
              id={tickerId}
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="AAPL · RELIANCE.NS · 0700.HK"
              autoComplete="off"
              spellCheck={false}
              maxLength={15}
              className={cn(
                "h-11 w-full rounded-lg pl-9 pr-3",
                "bg-[var(--color-surface-2)] font-mono text-base uppercase tracking-wide text-[var(--color-fg)]",
                "border border-[var(--color-line)] placeholder:text-[var(--color-fg-subtle)] placeholder:normal-case placeholder:tracking-normal",
                "transition-colors focus:border-[var(--color-accent)] focus:outline-none focus-visible:outline-none",
              )}
            />
          </div>
        </div>

        {/* Investor mode segmented control */}
        <fieldset className="shrink-0">
          <legend className="mb-1.5 font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]">
            Investor lens
          </legend>
          <div className="inline-flex h-11 items-center gap-0.5 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-1)] p-1">
            {INVESTOR_MODES.map((mode) => (
              <button
                key={mode}
                type="button"
                aria-pressed={investorMode === mode}
                onClick={() => setInvestorMode(mode)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-xs font-medium transition-colors duration-[120ms]",
                  investorMode === mode
                    ? "bg-[var(--color-glass-strong)] text-[var(--color-fg)] ring-1 ring-[var(--color-glass-border)]"
                    : "text-[var(--color-fg-subtle)] hover:text-[var(--color-fg-muted)]",
                )}
              >
                {mode}
              </button>
            ))}
          </div>
        </fieldset>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Debate toggle */}
        <fieldset className="flex items-center gap-2">
          <legend className="sr-only">Debate mode</legend>
          <span className="font-mono text-2xs uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]">
            Debate
          </span>
          <div className="inline-flex items-center gap-0.5 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-1)] p-1">
            {(["default", "on", "off"] as const).map((opt) => (
              <button
                key={opt}
                type="button"
                aria-pressed={debate === opt}
                onClick={() => setDebate(opt)}
                className={cn(
                  "rounded-md px-2.5 py-1 font-mono text-2xs font-medium uppercase tracking-wide transition-colors",
                  debate === opt
                    ? "bg-[var(--color-accent)] text-[var(--color-accent-fg)]"
                    : "text-[var(--color-fg-subtle)] hover:text-[var(--color-fg-muted)]",
                )}
              >
                {opt}
              </button>
            ))}
          </div>
        </fieldset>

        {isActive ? (
          <Button type="button" variant="outline" onClick={onStop}>
            <Square className="fill-current" />
            Stop
          </Button>
        ) : (
          <Button type="submit" disabled={disabled || !ticker.trim()}>
            {disabled ? <Loader2 className="animate-spin" /> : <Search />}
            Run analysis
          </Button>
        )}
      </div>
    </form>
  );
}
