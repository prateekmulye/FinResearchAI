/**
 * CandlestickChart — the terminal-grade price panel (lightweight-charts v4).
 *
 * This is the "every exchange, every ticker" proof screen, so the chrome is
 * deliberately Bloomberg-restrained (NotebookLM: abolish "prison-cell" borders,
 * lean on negative space + tabular numerics): daily candles with a volume
 * sub-panel pinned to the bottom ~22% of the frame, a 1px dotted crosshair, and
 * a floating glass OHLC legend top-left that tracks the hovered bar (or the
 * latest bar at rest). Colors come from the DESIGN bull/bear tokens, resolved
 * to hex at mount because the charting canvas can't read CSS custom properties.
 *
 * A ResizeObserver keeps it fluid; reduced-motion users get an instant fit.
 * The canvas itself is aria-hidden — the legend + the surrounding panel carry
 * the accessible price story.
 */
import {
  type CandlestickData,
  ColorType,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type Time,
  createChart,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";

import type { PriceBar } from "@/lib/api";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { formatCompactUsd } from "@/lib/utils";

/**
 * Resolve a DESIGN CSS token to a canvas-parseable color.
 *
 * The DESIGN tokens are authored in OKLCH, which lightweight-charts v4's color
 * parser CANNOT read (it throws "Cannot parse color: oklch(...)", and the
 * attribution-logo widget grayscales the text color even when hidden). So we
 * let the BROWSER resolve the token to an rgb(...) string via a probe element's
 * computed `color`, then hand the chart that. Falls back to a hex when there's
 * no DOM (tests / SSR) or the resolution doesn't yield an rgb value.
 */
function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return fallback;
  }
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  if (!raw) return fallback;
  // Already canvas-safe (hex / rgb / named) — pass through.
  if (!raw.startsWith("oklch") && !raw.startsWith("lab") && !raw.startsWith("lch")) {
    return raw;
  }
  // Resolve the modern color space to rgb() through the browser.
  const probe = document.createElement("span");
  probe.style.color = raw;
  probe.style.display = "none";
  document.body.appendChild(probe);
  const resolved = getComputedStyle(probe).color;
  probe.remove();
  return resolved && resolved.startsWith("rgb") ? resolved : fallback;
}

/** Append an alpha to an rgb()/rgba() string for the volume tint (0..1). */
function withAlpha(color: string, alpha: number): string {
  const m = color.match(/rgba?\(([^)]+)\)/);
  if (m?.[1]) {
    const [r, g, b] = m[1].split(",").map((p) => p.trim());
    if (r && g && b) return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  return color;
}

/** YYYY-MM-DD business-day string lightweight-charts wants for a daily series. */
function toDay(ts: string): Time {
  return ts.slice(0, 10) as Time;
}

export interface OHLC {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export function CandlestickChart({ bars }: { bars: PriceBar[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const reducedMotion = useReducedMotion();

  // The OHLC the legend shows: the crosshair bar while hovering, else the last.
  const lastBar = bars.length ? bars[bars.length - 1] : null;
  const [legend, setLegend] = useState<OHLC | null>(
    lastBar
      ? {
          time: lastBar.ts,
          open: lastBar.open,
          high: lastBar.high,
          low: lastBar.low,
          close: lastBar.close,
          volume: lastBar.volume,
        }
      : null,
  );

  const tokens = useMemo(
    () => ({
      bull: cssVar("--color-bull", "#3fbf7f"),
      bear: cssVar("--color-bear", "#e0524a"),
      fg: cssVar("--color-fg-muted", "#b7bcc6"),
      line: "rgba(255,255,255,0.06)",
      crosshair: "rgba(235,238,245,0.28)",
    }),
    [],
  );

  // Build the chart once; series + data are updated in a separate effect so a
  // bars change doesn't tear down the canvas (avoids a flash on range switch).
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: tokens.fg,
        fontFamily:
          "'JetBrains Mono Variable', ui-monospace, SFMono-Regular, monospace",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        // No "prison cell" — only a whisper of horizontal grid, no verticals.
        horzLines: { color: tokens.line },
        vertLines: { visible: false },
      },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.08, bottom: 0.26 } },
      timeScale: { borderVisible: false, fixLeftEdge: true, fixRightEdge: true },
      crosshair: {
        vertLine: { color: tokens.crosshair, width: 1, style: 3, labelVisible: false },
        horzLine: { color: tokens.crosshair, width: 1, style: 3 },
      },
      handleScale: false,
      handleScroll: false,
      autoSize: false,
    });

    const candle = chart.addCandlestickSeries({
      upColor: tokens.bull,
      downColor: tokens.bear,
      borderUpColor: tokens.bull,
      borderDownColor: tokens.bear,
      wickUpColor: tokens.bull,
      wickDownColor: tokens.bear,
      priceLineVisible: false,
      lastValueVisible: true,
    });

    // Volume sub-panel — its own price scale pinned to the bottom 22%.
    const volume = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
      priceLineVisible: false,
      lastValueVisible: false,
    });
    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.78, bottom: 0 },
      borderVisible: false,
    });

    chartRef.current = chart;
    candleRef.current = candle;
    // Stash volume on the candle ref's chart via closure for the data effect.
    (chart as unknown as { _volume?: ISeriesApi<"Histogram"> })._volume = volume;

    // Crosshair → legend. On leave, snap the legend back to the latest bar.
    const onMove = (param: MouseEventParams) => {
      const d = param.seriesData.get(candle) as CandlestickData<Time> | undefined;
      const v = param.seriesData.get(volume) as HistogramData<Time> | undefined;
      if (!d || param.time == null) return;
      setLegend({
        time: String(param.time),
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
        volume: v?.value ?? null,
      });
    };
    chart.subscribeCrosshairMove(onMove);

    const ro = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) chart.resize(rect.width, rect.height);
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.unsubscribeCrosshairMove(onMove);
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
    };
  }, [tokens]);

  // Feed data whenever bars change (range switch / new ticker).
  useEffect(() => {
    const chart = chartRef.current;
    const candle = candleRef.current;
    if (!chart || !candle) return;
    const volume = (chart as unknown as { _volume?: ISeriesApi<"Histogram"> })._volume;

    const candleData: CandlestickData<Time>[] = bars.map((b) => ({
      time: toDay(b.ts),
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }));
    candle.setData(candleData);

    if (volume) {
      volume.setData(
        bars.map((b) => ({
          time: toDay(b.ts),
          value: b.volume ?? 0,
          color:
            b.close >= b.open
              ? withAlpha(tokens.bull, 0.28)
              : withAlpha(tokens.bear, 0.28),
        })),
      );
    }

    chart.timeScale().fitContent();

    // Reset the resting legend to the newest bar of the new series.
    const last = bars.length ? bars[bars.length - 1] : null;
    setLegend(
      last
        ? {
            time: last.ts,
            open: last.open,
            high: last.high,
            low: last.low,
            close: last.close,
            volume: last.volume,
          }
        : null,
    );
  }, [bars, tokens, reducedMotion]);

  const up = legend ? legend.close >= legend.open : true;

  return (
    <div className="relative h-[340px] w-full sm:h-[420px]">
      {/* Floating glass OHLC legend — top-left, tracks the crosshair. */}
      {legend && (
        <div className="pointer-events-none absolute left-3 top-3 z-10 rounded-lg border border-[var(--color-glass-border)] bg-[var(--color-glass-strong)] px-3 py-2 font-mono text-2xs backdrop-blur-[16px]">
          <div className="mb-1 flex items-center gap-2 tabular-nums text-[var(--color-fg-subtle)]">
            <span>{legend.time.slice(0, 10)}</span>
            {legend.volume != null && (
              <span aria-label={`Volume ${legend.volume}`}>
                vol {formatCompactUsd(legend.volume).replace("$", "")}
              </span>
            )}
          </div>
          <div className="flex items-center gap-x-3 gap-y-0.5 tabular-nums">
            <LegendCell label="O" value={legend.open} />
            <LegendCell label="H" value={legend.high} />
            <LegendCell label="L" value={legend.low} />
            <LegendCell
              label="C"
              value={legend.close}
              tint={up ? "var(--color-bull)" : "var(--color-bear)"}
            />
          </div>
        </div>
      )}
      <div ref={containerRef} className="size-full" aria-hidden="true" />
    </div>
  );
}

function LegendCell({
  label,
  value,
  tint,
}: {
  label: string;
  value: number;
  tint?: string;
}) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="text-[var(--color-fg-subtle)]">{label}</span>
      <span style={{ color: tint ?? "var(--color-fg)" }}>{value.toFixed(2)}</span>
    </span>
  );
}
