/**
 * NewsFeed — the newest-first headline tiles the news analyst ingests. Each is
 * a glass tile: source + relative time eyebrow, the title linking OUT to the
 * article (new tab, rel=noopener — it leaves the app), and a snippet. The whole
 * tile is the click target (Fitts). Empty → an outcome-oriented nudge.
 */
import { ArrowUpRight, Newspaper } from "lucide-react";
import { Link } from "react-router";

import { buttonVariants } from "@/components/ui/button";
import type { NewsItem } from "@/lib/api";
import { cn, formatRelativeTime } from "@/lib/utils";

function NewsTile({ item }: { item: NewsItem }) {
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`${item.title} (opens in a new tab)`}
      className="group block focus-visible:outline-none"
    >
      <article className="glass overflow-hidden rounded-xl px-4 py-3 transition-[transform,box-shadow,border-color] duration-[200ms] ease-[var(--ease-spring)] group-hover:-translate-y-0.5 group-hover:shadow-[var(--shadow-raised)] group-focus-visible:outline-2 group-focus-visible:outline-offset-2 group-focus-visible:outline-[var(--color-accent)]">
        <div className="mb-1 flex items-center gap-2 font-mono text-2xs text-[var(--color-fg-subtle)]">
          <span className="truncate uppercase tracking-wide text-[var(--color-fg-muted)]">
            {item.source ?? "source"}
          </span>
          <span aria-hidden="true">·</span>
          <span className="tabular-nums">{formatRelativeTime(item.ts)}</span>
          <ArrowUpRight
            className="ml-auto size-3.5 text-[var(--color-fg-subtle)] transition-[transform,color] duration-[200ms] group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-[var(--color-accent)]"
            aria-hidden="true"
          />
        </div>
        <h3 className="text-sm font-medium leading-snug text-[var(--color-fg)] group-hover:text-[var(--color-accent)]">
          {item.title}
        </h3>
        {item.snippet && (
          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-[var(--color-fg-muted)]">
            {item.snippet}
          </p>
        )}
      </article>
    </a>
  );
}

export function NewsFeed({
  ticker,
  items,
  isLoading,
}: {
  ticker: string;
  items: NewsItem[];
  isLoading: boolean;
}) {
  return (
    <section className="space-y-3">
      <p className="flex items-center gap-2 px-1 font-mono text-2xs font-medium uppercase tracking-[0.18em] text-[var(--color-accent)]">
        <Newspaper className="size-3.5" aria-hidden="true" />
        News the analysts ingest
      </p>

      {isLoading ? (
        <ul className="space-y-2.5" aria-hidden="true">
          {Array.from({ length: 4 }).map((_, i) => (
            <li
              key={i}
              className="glass h-20 animate-shimmer rounded-xl bg-[var(--color-surface-1)]"
            />
          ))}
        </ul>
      ) : items.length === 0 ? (
        <div className="glass flex flex-col items-center gap-2 rounded-xl px-5 py-8 text-center">
          <Newspaper className="size-5 text-[var(--color-fg-subtle)]" aria-hidden="true" />
          <p className="text-sm font-medium text-[var(--color-fg)]">
            No headlines stored yet
          </p>
          <p className="max-w-xs text-xs leading-relaxed text-[var(--color-fg-muted)]">
            The news analyst pulls and stores headlines for {ticker} on its first
            run — they’ll appear here newest-first.
          </p>
          <Link
            to="/"
            state={{ ticker }}
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "mt-1")}
          >
            Analyze {ticker}
          </Link>
        </div>
      ) : (
        <ul className="space-y-2.5">
          {items.map((item, i) => (
            <li key={`${item.url}:${i}`}>
              <NewsTile item={item} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
