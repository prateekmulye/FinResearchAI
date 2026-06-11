import { AnimatePresence, motion } from "motion/react";
import { type ReactNode } from "react";
import { useLocation } from "react-router";

import { useReducedMotion } from "@/hooks/useReducedMotion";

/**
 * PageTransition — a short, spring-eased cross-fade + lift between routes.
 * Keyed on pathname so AnimatePresence runs on navigation. Honors the
 * Doherty Threshold (well under 400ms) and disables under reduced motion.
 *
 * This component OWNS the page's <main> landmark (motion.main below), so the
 * reduced-motion branch must still render a real <main> — returning bare
 * children would silently drop the landmark for exactly the users most likely
 * to navigate by it.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const location = useLocation();
  const reduced = useReducedMotion();

  if (reduced) return <main className="flex-1">{children}</main>;

  return (
    <AnimatePresence mode="wait">
      <motion.main
        key={location.pathname}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
        className="flex-1"
      >
        {children}
      </motion.main>
    </AnimatePresence>
  );
}
