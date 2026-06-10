import { CandlestickChart } from "lucide-react";

import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";

/**
 * MarketPage — WP-9: the Market Explorer. Instrument search, a lightweight-charts
 * price panel, a fundamentals tile, and a news feed — all from /api/market/*.
 */
export function MarketPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Market explorer"
        title="The data behind the verdict."
        description="Search any covered instrument and inspect the raw inputs the agents reason over — daily price action on an interactive chart, the latest fundamentals snapshot, and the news the analysts ingest."
      />
      <EmptyState
        icon={CandlestickChart}
        badge="Ships in WP-9"
        title="Explorer lands here"
        description="Type-ahead instrument search backed by /api/market/instruments, a candlestick price chart, a tabular fundamentals card (P/E, EPS, margins, growth), and a newest-first headline feed — the same surfaces the news and fundamentals analysts draw on."
      />
    </div>
  );
}
