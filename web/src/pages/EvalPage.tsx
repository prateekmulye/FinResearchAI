import { FlaskConical } from "lucide-react";

import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";

/**
 * EvalPage — WP-10: the debate-on vs debate-off A/B harness results
 * (GET /api/eval/results). The rigor the TradingAgents paper omitted — does the
 * bull/bear debate actually earn its cost?
 */
export function EvalPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Ablation harness"
        title="Does the debate earn its cost?"
        description="A side-by-side A/B of the pipeline with the bull-bear debate on versus off — the ablation the source paper skipped. Decision agreement, conviction shift, and the extra tokens the debate spends, measured run by run."
      />
      <EmptyState
        icon={FlaskConical}
        badge="Ships in WP-10"
        title="Eval results land here"
        description="Stored A/B results from /api/eval/results, rendered as a per-ticker comparison: debate-on vs debate-off verdicts, where they diverged, and the cost/latency premium of running the debate — so the architecture choice is defended with data, not vibes."
      />
    </div>
  );
}
