/**
 * Markdown.tsx — renders the final report from sanitized markdown.
 *
 * The HTML fed to dangerouslySetInnerHTML is ALWAYS produced by
 * sanitizeMarkdown() (marked -> DOMPurify), never raw model output. The
 * sanitizer lives in ./markdown.ts so it can be unit-tested for injection.
 */
import { useMemo } from "react";

import { sanitizeMarkdown } from "./markdown";

/**
 * Rendered markdown with the editorial typography from DESIGN.md. External
 * links are hardened to noopener/noreferrer inside the sanitizer.
 */
export function Markdown({ source }: { source: string }) {
  const html = useMemo(() => sanitizeMarkdown(source), [source]);
  // The input is DOMPurify-sanitized in sanitizeMarkdown(); this is the single
  // controlled injection point in the app.
  return (
    <div className="report-prose" dangerouslySetInnerHTML={{ __html: html }} />
  );
}
