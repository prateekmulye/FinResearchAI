/**
 * markdown.test.ts — the report renderer must NEVER pass raw HTML through.
 * These assert DOMPurify strips script/handler/iframe/javascript: vectors while
 * keeping legitimate markdown structure.
 */
import { describe, expect, it } from "vitest";

import { sanitizeMarkdown } from "./markdown";

describe("sanitizeMarkdown — injection defense", () => {
  it("strips <script> tags from the output", () => {
    const html = sanitizeMarkdown("Hello\n\n<script>alert('xss')</script>");
    expect(html).not.toContain("<script");
    expect(html.toLowerCase()).not.toContain("alert(");
  });

  it("strips inline event handlers", () => {
    const html = sanitizeMarkdown('<img src=x onerror="alert(1)">');
    expect(html.toLowerCase()).not.toContain("onerror");
  });

  it("neutralizes javascript: URLs in links", () => {
    const html = sanitizeMarkdown("[click](javascript:alert(1))");
    expect(html.toLowerCase()).not.toContain("javascript:alert");
  });

  it("removes <iframe> embeds", () => {
    const html = sanitizeMarkdown('<iframe src="https://evil.example"></iframe>');
    expect(html.toLowerCase()).not.toContain("<iframe");
  });

  it("keeps legitimate markdown structure (headings, bold, lists)", () => {
    const html = sanitizeMarkdown(
      "# Executive Summary\n\n**BUY** AAPL.\n\n- point one\n- point two",
    );
    expect(html).toContain("<h1");
    expect(html).toContain("<strong>BUY</strong>");
    expect(html).toContain("<li>point one</li>");
  });

  it("renders gfm tables", () => {
    const html = sanitizeMarkdown(
      "| Metric | Value |\n| --- | --- |\n| P/E | 28 |",
    );
    expect(html).toContain("<table");
    expect(html).toContain("<td>P/E</td>");
  });

  it("handles empty / nullish input without throwing", () => {
    expect(sanitizeMarkdown("")).toBe("");
    // @ts-expect-error — guarding the runtime nullish path on purpose
    expect(sanitizeMarkdown(undefined)).toBe("");
  });
});
