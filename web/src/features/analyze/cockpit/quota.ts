/**
 * quota.ts — pure helper for detecting a quota/rate-limit refusal. Kept
 * separate from the QuotaBlocked component so it can be unit-tested and so the
 * component file stays component-only (fast-refresh).
 *
 * Detection is status-first: the stream hook records the HTTP status behind an
 * error (429 = quota), so a real rate-limit never depends on message text. The
 * message regex is only a fallback for status-less paths (e.g. an in-stream
 * error frame), and deliberately narrow — incidental "429"/"replay" mentions in
 * arbitrary errors must NOT steer users away from the real failure.
 */
export function isQuotaError(
  message: string | null,
  status?: number | null,
): boolean {
  if (status === 429) return true;
  if (!message) return false;
  return /rate limit|quota/i.test(message);
}
