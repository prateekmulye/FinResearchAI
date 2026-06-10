import { ArrowLeft, History } from "lucide-react";
import { Link, useParams } from "react-router";

import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";

/**
 * RunDetailPage — WP-8: full run detail + replay (GET /api/runs/:runId). The
 * report, the verdict, per-node cost/latency, and a scrubber that re-plays the
 * recorded SSE events on their original timeline.
 */
export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();

  return (
    <div className="space-y-8">
      <Link
        to="/library"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--color-fg-muted)] transition-colors hover:text-[var(--color-fg)]"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Back to library
      </Link>

      <PageHeader
        eyebrow="Run replay"
        title={
          <>
            Run <span className="font-mono text-[var(--color-accent)]">{runId}</span>
          </>
        }
        description="The complete record of one analysis — its report, structured verdict, per-node cost and latency, and a timeline scrubber that replays the agent stream exactly as it unfolded."
      />

      <EmptyState
        icon={History}
        badge="Ships in WP-8"
        title="Replay surface lands here"
        description="This page will hydrate from the run's stored events, rendering the markdown report, the verdict header, the cost/latency footer, and a play/scrub control over the recorded stream timeline."
      />
    </div>
  );
}
