import { Suspense } from "react";
import { Outlet } from "react-router";

import { AuroraBackground } from "@/components/shell/AuroraBackground";
import { Footer } from "@/components/shell/Footer";
import { PageTransition } from "@/components/shell/PageTransition";
import { RouteFallback } from "@/components/shell/RouteFallback";
import { TopNav } from "@/components/shell/TopNav";

/**
 * AppShell — the persistent glass frame around every route. Layers, back to
 * front: aurora background → grain overlay (via `.grain` on the root) → glass
 * nav → transitioning page → footer. A skip link keeps keyboard users fast.
 */
export function AppShell() {
  return (
    <div className="grain relative flex min-h-dvh flex-col">
      <AuroraBackground />

      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-[var(--color-accent)] focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-[var(--color-accent-fg)]"
      >
        Skip to content
      </a>

      <TopNav />

      {/* tabIndex={-1}: the skip link's target must be programmatically
          focusable or the skip is a no-op in several browsers. */}
      <div
        id="main"
        tabIndex={-1}
        className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 outline-none sm:py-10"
      >
        <PageTransition>
          <Suspense fallback={<RouteFallback />}>
            <Outlet />
          </Suspense>
        </PageTransition>
      </div>

      <Footer />
    </div>
  );
}
