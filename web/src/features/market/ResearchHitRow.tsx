/**
 * ResearchHitRow — one "research memory" hit. The same row silhouette as an
 * instrument (Gestalt similarity links the lanes) but the destination differs
 * by kind: a `news` hit links OUT to the article (rel=noopener, new tab — it
 * leaves the app), a `run` hit links IN to that run's replay at /library/:runId
 * (router state prefills the ticker for the replay CTA, mirroring LibraryRow).
 *
 * `score` is a cosine DISTANCE in semantic mode (lower = closer) — we never
 * dress it up as a relevance %; it's shown raw + mono only as a quiet honesty
 * cue, and omitted entirely in keyword mode (where it's null).
 */
import { ArrowUpRight, ChevronRight } from "lucide-react";
import { Link } from "react-router";

import type { SearchHit } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";

import { KindChip } from "./marketChips";

function HitBody({ hit }: { hit: SearchHit }) {
  return (
    <>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <KindChip kind={hit.kind} />
          <span className="font-mono text-2xs font-semibold tracking-tight text-[var(--color-fg)]">
            {hit.ticker}
          </span>
          <span className="font-mono text-2xs text-[var(--color-fg-subtle)]">
            {formatRelativeTime(hit.ts)}
          </span>
          {hit.score != null && (
            <span
              className="ml-auto font-mono text-2xs tabular-nums text-[var(--color-fg-subtle)]"
              title="Cosine distance — lower is closer"
            >
              d {hit.score.toFixed(3)}
            </span>
          )}
        </div>
        <p className="mt-1 truncate text-sm font-medium text-[var(--color-fg)]">
          {hit.title}
        </p>
        {hit.snippet && (
          <p className="mt-0.5 line-clamp-2 text-xs leading-relaxed text-[var(--color-fg-muted)]">
            {hit.snippet}
          </p>
        )}
      </div>
    </>
  );
}

export function ResearchHitRow({ hit }: { hit: SearchHit }) {
  const tileCls =
    "glass flex items-start gap-3 overflow-hidden rounded-xl px-4 py-3 transition-[transform,box-shadow,border-color] duration-[200ms] ease-[var(--ease-spring)] group-hover:-translate-y-0.5 group-hover:shadow-[var(--shadow-raised)] group-focus-visible:outline-2 group-focus-visible:outline-offset-2 group-focus-visible:outline-[var(--color-accent)]";

  if (hit.kind === "news") {
    return (
      <a
        href={hit.ref}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`Open article: ${hit.title} (opens in a new tab)`}
        className="group block focus-visible:outline-none"
      >
        <div className={tileCls}>
          <HitBody hit={hit} />
          <ArrowUpRight
            className="mt-0.5 size-4 shrink-0 text-[var(--color-fg-subtle)] transition-[transform,color] duration-[200ms] group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-[var(--color-accent)]"
            aria-hidden="true"
          />
        </div>
      </a>
    );
  }

  return (
    <Link
      to={`/library/${encodeURIComponent(hit.ref)}`}
      state={{ ticker: hit.ticker }}
      aria-label={`Replay run for ${hit.ticker}: ${hit.title}`}
      className="group block focus-visible:outline-none"
    >
      <div className={tileCls}>
        <HitBody hit={hit} />
        <ChevronRight
          className="mt-0.5 size-4 shrink-0 text-[var(--color-fg-subtle)] transition-[transform,color] duration-[200ms] group-hover:translate-x-0.5 group-hover:text-[var(--color-accent)]"
          aria-hidden="true"
        />
      </div>
    </Link>
  );
}
