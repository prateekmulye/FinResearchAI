/**
 * pairSort — client-side sort for the per-ticker receipts table. Two keys the
 * reader actually reasons with: score delta (did the debate decide better?) and
 * cost delta (what did it cost?). Pure + tested; the table is a thin renderer
 * over this. Nulls always sink to the bottom regardless of direction, so a
 * ticker with missing metrics never masquerades as the best or worst.
 */
import type { EvalPair } from "./evalFormat";

export type SortKey = "scoreDelta" | "costDelta" | "ticker";
export type SortDir = "asc" | "desc";

export interface SortState {
  key: SortKey;
  dir: SortDir;
}

/** Toggling a key that's already active flips its direction; a new key starts
 *  descending for the numeric deltas (biggest-impact first) and ascending for
 *  the ticker (A→Z). */
export function nextSort(current: SortState, key: SortKey): SortState {
  if (current.key === key) {
    return { key, dir: current.dir === "desc" ? "asc" : "desc" };
  }
  return { key, dir: key === "ticker" ? "asc" : "desc" };
}

export function sortPairs(pairs: EvalPair[], sort: SortState): EvalPair[] {
  const out = [...pairs];
  const factor = sort.dir === "asc" ? 1 : -1;

  out.sort((a, b) => {
    if (sort.key === "ticker") {
      return a.ticker.localeCompare(b.ticker) * factor;
    }
    const av = a[sort.key];
    const bv = b[sort.key];
    // Nulls always sink, irrespective of direction.
    if (av == null && bv == null) return a.ticker.localeCompare(b.ticker);
    if (av == null) return 1;
    if (bv == null) return -1;
    if (av === bv) return a.ticker.localeCompare(b.ticker);
    return (av - bv) * factor;
  });

  return out;
}
