/**
 * markdown.ts — the pure, testable sanitization core for the report renderer.
 *
 * marked (tiny) -> HTML string -> DOMPurify (sanitize). This is the ONLY place
 * raw model markdown becomes HTML, and it is ALWAYS DOMPurify-sanitized before
 * the Markdown component injects it. Kept framework-free so injection tests can
 * call it directly.
 *
 * Both marked and dompurify resolve into the lazy Analyze chunk (only the
 * cockpit imports this, and the cockpit only loads on the Analyze route).
 */
import DOMPurify from "dompurify";
import { marked } from "marked";

marked.setOptions({ gfm: true, breaks: false });

// Harden any anchors DOMPurify keeps: external links get noopener/noreferrer.
if (typeof window !== "undefined") {
  DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A" && node.getAttribute("href")) {
      node.setAttribute("target", "_blank");
      node.setAttribute("rel", "noopener noreferrer");
    }
  });
}

/** Render markdown to a sanitized HTML string. Pure — safe to unit-test. */
export function sanitizeMarkdown(md: string): string {
  const rawHtml = marked.parse(md ?? "", { async: false }) as string;
  return DOMPurify.sanitize(rawHtml, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["style", "script", "iframe", "form", "object", "embed"],
    FORBID_ATTR: ["style", "onerror", "onload", "onclick"],
    ALLOW_DATA_ATTR: false,
  });
}
