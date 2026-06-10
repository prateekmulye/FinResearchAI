/**
 * quota.ts — pure helper for detecting a quota/rate-limit refusal in the stream
 * error string. Kept separate from the QuotaBlocked component so it can be
 * unit-tested and so the component file stays component-only (fast-refresh).
 *
 * The stream hook surfaces a 429 with a "Rate limited — daily live-run quota
 * reached…" message; this matches that family without coupling to exact copy.
 */
export function isQuotaError(message: string | null): boolean {
  if (!message) return false;
  return /rate limit|quota|429|replay/i.test(message);
}
