import { Compass } from "lucide-react";
import { Link } from "react-router";

import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-2xl pt-8">
      <EmptyState
        icon={Compass}
        badge="404"
        title="Off the graph"
        description="That route doesn't exist. Head back to the cockpit and run an analysis."
      >
        <Link to="/" className={buttonVariants({ variant: "primary" })}>
          Back to Analyze
        </Link>
      </EmptyState>
    </div>
  );
}
