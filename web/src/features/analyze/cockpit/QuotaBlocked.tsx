/**
 * QuotaBlocked — the designed state when live runs are exhausted (429 / quota
 * replay-only). Rather than a dead error, it steers the visitor to the Library
 * replays so the showpiece is never a wall: a recruiter who hits the cap still
 * gets to watch a real recorded run.
 */
import { Archive, Sparkles } from "lucide-react";
import { Link } from "react-router";

import { Button, buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/utils";

export function QuotaBlocked({ onDismiss }: { onDismiss?: () => void }) {
  return (
    <EmptyState
      icon={Archive}
      badge="Daily live-run quota reached"
      title="Out of live runs for today"
      description="Live analyses are metered to keep the demo affordable. The full cockpit — every node, the debate, the verdict — replays from recorded runs in the Library, at speed and with zero quota."
    >
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Link to="/library" className={cn(buttonVariants({ variant: "primary" }))}>
          <Sparkles className="size-4" aria-hidden="true" />
          Watch a replay
        </Link>
        {onDismiss && (
          <Button variant="outline" onClick={onDismiss}>
            Dismiss
          </Button>
        )}
      </div>
    </EmptyState>
  );
}
