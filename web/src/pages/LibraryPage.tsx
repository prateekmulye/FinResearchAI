import { Library } from "lucide-react";

import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";

/**
 * LibraryPage — WP-8 fills this with the run history (GET /api/library): a
 * filterable, paginated table of past analyses with verdict + cost, each row
 * opening a full replay.
 */
export function LibraryPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Research library"
        title="Every run, replayable."
        description="A searchable archive of past analyses. Filter by ticker or status, scan the verdict and cost at a glance, and open any run to replay the full agent stream exactly as it happened — even when your live quota is spent."
      />
      <EmptyState
        icon={Library}
        badge="Ships in WP-8"
        title="No runs to show yet"
        description="Once analyses start completing, they land here newest-first with their BUY / SELL / HOLD verdict, conviction, token cost, and latency — one click to replay the stream frame by frame."
      />
    </div>
  );
}
