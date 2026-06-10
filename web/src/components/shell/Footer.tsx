import { Github } from "lucide-react";

/**
 * Footer — quiet, persistent. Carries the GitHub source link and the
 * "powered by a 12-node multi-agent graph" provenance line that frames the whole
 * project as an engineering artifact, not a toy.
 */
export function Footer() {
  return (
    <footer className="mx-auto mt-16 w-full max-w-7xl px-4 pb-10">
      <div className="glass flex flex-col items-start gap-4 rounded-2xl px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="font-mono text-xs text-[var(--color-fg-subtle)]">
          powered by a{" "}
          <span className="text-[var(--color-fg-muted)]">
            12-node multi-agent graph
          </span>{" "}
          · router → analysts → debate → trader → risk → reporter
        </p>
        <a
          href="https://github.com/prateekmulye/FinResearchAI"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 rounded-md text-xs font-medium text-[var(--color-fg-muted)] transition-colors hover:text-[var(--color-fg)]"
        >
          <Github className="size-4" aria-hidden="true" />
          <span>Source on GitHub</span>
        </a>
      </div>
    </footer>
  );
}
