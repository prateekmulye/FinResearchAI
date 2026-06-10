import { motion } from "motion/react";
import { NavLink, useLocation } from "react-router";

import { HealthDot } from "@/components/shell/HealthDot";
import { QuotaPill } from "@/components/shell/QuotaPill";
import { Wordmark } from "@/components/shell/Wordmark";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { cn } from "@/lib/utils";

const ROUTES = [
  { to: "/", label: "Analyze", end: true },
  { to: "/library", label: "Library", end: false },
  { to: "/market", label: "Market", end: false },
  { to: "/eval", label: "Eval", end: false },
] as const;

/**
 * TopNav — the floating glass app-bar. An active-route pill slides between tabs
 * via a shared Motion layoutId (one continuous element, spring physics). Under
 * reduced motion the pill snaps without animating.
 */
export function TopNav() {
  const reduced = useReducedMotion();
  const location = useLocation();
  // Match the deepest active root segment so /library/:id keeps "Library" lit.
  const activeRoot =
    ROUTES.slice()
      .reverse()
      .find((r) =>
        r.end ? location.pathname === r.to : location.pathname.startsWith(r.to),
      )?.to ?? "/";

  return (
    <header className="sticky top-0 z-40 px-4 pt-4">
      <nav
        aria-label="Primary"
        className={cn(
          "glass-strong mx-auto flex h-14 max-w-7xl items-center gap-2 rounded-2xl pl-4 pr-3",
        )}
      >
        <NavLink
          to="/"
          className="rounded-md focus-visible:outline-2"
          aria-label="FinResearch home"
        >
          <Wordmark />
        </NavLink>

        {/* Plain nav links (NavLink anchors) — deliberately NOT a tablist:
            tabs control in-page panels; these navigate between routes. */}
        <div className="ml-2 hidden items-center gap-1 sm:flex">
          {ROUTES.map((route) => {
            const isActive = activeRoot === route.to;
            return (
              <NavLink
                key={route.to}
                to={route.to}
                end={route.end}
                className={cn(
                  "relative rounded-lg px-3.5 py-2 text-sm font-medium transition-colors duration-[120ms]",
                  isActive
                    ? "text-[var(--color-fg)]"
                    : "text-[var(--color-fg-subtle)] hover:text-[var(--color-fg-muted)]",
                )}
              >
                {isActive && (
                  <motion.span
                    layoutId="nav-active-pill"
                    className="absolute inset-0 -z-10 rounded-lg bg-[var(--color-glass-strong)] ring-1 ring-[var(--color-glass-border)]"
                    transition={
                      reduced
                        ? { duration: 0 }
                        : { type: "spring", stiffness: 380, damping: 32, mass: 0.8 }
                    }
                  />
                )}
                {route.label}
              </NavLink>
            );
          })}
        </div>

        <div className="ml-auto flex items-center gap-3">
          <QuotaPill />
          <span className="hidden h-5 w-px bg-[var(--color-line)] md:block" />
          <HealthDot />
        </div>
      </nav>

      {/* Mobile tab row — full-width segmented control under the bar */}
      <div className="mx-auto mt-2 flex max-w-7xl gap-1 sm:hidden">
        {ROUTES.map((route) => (
          <NavLink
            key={route.to}
            to={route.to}
            end={route.end}
            className={({ isActive }) =>
              cn(
                "glass flex-1 rounded-lg py-2 text-center text-xs font-medium transition-colors",
                isActive
                  ? "text-[var(--color-fg)] ring-1 ring-[var(--color-accent)]"
                  : "text-[var(--color-fg-subtle)]",
              )
            }
          >
            {route.label}
          </NavLink>
        ))}
      </div>
    </header>
  );
}
