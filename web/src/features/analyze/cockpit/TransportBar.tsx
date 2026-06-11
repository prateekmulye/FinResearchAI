/**
 * TransportBar — the replay theater's playback control. The scrubber is not a
 * generic video bar: its track IS the pipeline timeline. Stage ticks sit at each
 * node's synthetic offset, so scrubbing reads as moving through named agent
 * stages (Gestalt continuity + the NotebookLM "visual spine" idea), and the
 * played region fills toward the verdict (Goal-Gradient).
 *
 * a11y: the track is a real ARIA slider (role=slider, valuemin/max/now, label),
 * keyboard-driven — Space toggles play, ←/→ step one event, Home/End jump to
 * ends. Speed is a segmented control (Hick's Law: 1/2/4/8, one tap each).
 */
import { Pause, Play, RotateCcw } from "lucide-react";
import {
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useRef,
} from "react";

import { nodeLabel, nodePhase } from "@/features/analyze/nodeLabels";
import { cn } from "@/lib/utils";

import { REPLAY_SPEEDS, type EventPlayerControls } from "./eventPlayer";
import { formatMs } from "./transportTime";

/** Phase -> token color, so ticks are legible as the run's structure. */
const PHASE_TINT: Record<string, string> = {
  Resolve: "var(--color-accent)",
  Analysts: "var(--color-fg-muted)",
  Debate: "var(--color-hold)",
  Trade: "var(--color-accent)",
  Risk: "var(--color-aggressive)",
  Report: "var(--color-bull)",
};

export function TransportBar({ player }: { player: EventPlayerControls }) {
  const {
    isActive,
    isEnded,
    play,
    pause,
    seekProgress,
    step,
    restart,
    setSpeed,
    speed,
    elapsedMs,
    durationMs,
    progress,
    stageTicks,
  } = player;

  const trackRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);

  const toggle = useCallback(() => {
    if (isActive) pause();
    else play();
  }, [isActive, play, pause]);

  const seekFromClientX = useCallback(
    (clientX: number) => {
      const el = trackRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const p = (clientX - rect.left) / rect.width;
      seekProgress(Math.max(0, Math.min(1, p)));
    },
    [seekProgress],
  );

  const onPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      draggingRef.current = true;
      e.currentTarget.setPointerCapture(e.pointerId);
      seekFromClientX(e.clientX);
    },
    [seekFromClientX],
  );

  const onPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (draggingRef.current) seekFromClientX(e.clientX);
    },
    [seekFromClientX],
  );

  const onPointerUp = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    draggingRef.current = false;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
  }, []);

  const onKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLDivElement>) => {
      switch (e.key) {
        case " ":
        case "Enter":
          e.preventDefault();
          toggle();
          break;
        // ARIA slider pattern: Right/Up increase, Left/Down decrease.
        case "ArrowRight":
        case "ArrowUp":
          e.preventDefault();
          step(1);
          break;
        case "ArrowLeft":
        case "ArrowDown":
          e.preventDefault();
          step(-1);
          break;
        case "Home":
          e.preventDefault();
          seekProgress(0);
          break;
        case "End":
          e.preventDefault();
          seekProgress(1);
          break;
      }
    },
    [toggle, step, seekProgress],
  );

  // Space toggles play/pause from anywhere on the page (the media convention),
  // unless the user is typing in a field, focused on the slider (which owns
  // its own handler), or focused on an interactive control — Space must
  // ACTIVATE a focused button (Restart, speed) or link (Back to library),
  // not hijack it into a play/pause toggle.
  useEffect(() => {
    const onSpace = (e: KeyboardEvent) => {
      if (e.key !== " ") return;
      const t = e.target as HTMLElement | null;
      const tag = t?.tagName;
      const typing =
        tag === "INPUT" || tag === "TEXTAREA" || t?.isContentEditable;
      const onSlider = t?.getAttribute("role") === "slider";
      const onControl = Boolean(t?.closest?.("button, a"));
      if (typing || onSlider || onControl) return;
      e.preventDefault();
      toggle();
    };
    window.addEventListener("keydown", onSpace);
    return () => window.removeEventListener("keydown", onSpace);
  }, [toggle]);

  const pct = Math.round(progress * 100);

  return (
    <div
      className="glass flex flex-col gap-3 rounded-2xl p-4 sm:flex-row sm:items-center sm:gap-4"
      aria-label="Replay transport"
    >
      {/* Play / restart cluster — the primary verbs (Fitts: big, leading). */}
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={toggle}
          aria-label={isActive ? "Pause replay" : "Play replay"}
          aria-pressed={isActive}
          className={cn(
            "flex size-11 items-center justify-center rounded-full",
            "bg-[var(--color-accent)] text-[var(--color-accent-fg)]",
            "transition-[transform,box-shadow] duration-[120ms] ease-[var(--ease-spring)]",
            "hover:shadow-[var(--shadow-glow-accent)] active:scale-[0.94]",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)]",
          )}
        >
          {isActive ? (
            <Pause className="size-5 fill-current" aria-hidden="true" />
          ) : (
            <Play className="size-5 translate-x-px fill-current" aria-hidden="true" />
          )}
        </button>
        <button
          type="button"
          onClick={restart}
          aria-label="Restart replay from the beginning"
          className={cn(
            "flex size-9 items-center justify-center rounded-full",
            "text-[var(--color-fg-muted)] transition-colors duration-[120ms]",
            "hover:bg-[var(--color-glass)] hover:text-[var(--color-fg)]",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)]",
          )}
        >
          <RotateCcw className="size-4" aria-hidden="true" />
        </button>
      </div>

      {/* The pipeline-mapped scrubber. */}
      <div className="flex flex-1 items-center gap-3">
        <span className="font-mono text-2xs tabular-nums text-[var(--color-fg-muted)]">
          {formatMs(elapsedMs)}
        </span>

        <div
          ref={trackRef}
          role="slider"
          tabIndex={0}
          aria-label="Replay timeline"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          aria-valuetext={`${formatMs(elapsedMs)} of ${formatMs(durationMs)}`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onKeyDown={onKeyDown}
          className={cn(
            "group relative h-9 flex-1 cursor-pointer select-none touch-none",
            "focus-visible:outline-none",
          )}
        >
          {/* Rail */}
          <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 overflow-hidden rounded-full bg-[var(--color-surface-3)]">
            {/* Played fill — races toward the verdict (Goal-Gradient). */}
            <div
              className="h-full rounded-full bg-[var(--color-accent)] transition-[width] duration-75 ease-linear group-focus-visible:bg-[var(--color-accent-strong)]"
              style={{ width: `${pct}%` }}
            />
          </div>

          {/* Stage ticks — each node_complete, phase-tinted. */}
          {durationMs > 0 &&
            stageTicks.map((t, i) => {
              const left = (t.offsetMs / durationMs) * 100;
              const reached = t.offsetMs <= elapsedMs + 0.5;
              return (
                <span
                  key={`${t.node}-${i}`}
                  className="pointer-events-none absolute top-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-[var(--color-base)] transition-transform"
                  style={{
                    left: `${left}%`,
                    background: reached
                      ? PHASE_TINT[nodePhase(t.node)] ?? "var(--color-fg-muted)"
                      : "var(--color-line-strong)",
                    transform: `translate(-50%, -50%) scale(${reached ? 1 : 0.7})`,
                  }}
                  title={nodeLabel(t.node)}
                />
              );
            })}

          {/* Playhead thumb */}
          <span
            className="pointer-events-none absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--color-fg)] shadow-[0_0_0_3px_var(--color-accent),0_2px_6px_oklch(0%_0_0/40%)] transition-[left] duration-75 ease-linear"
            style={{ left: `${pct}%` }}
          />
        </div>

        <span className="font-mono text-2xs tabular-nums text-[var(--color-fg-subtle)]">
          {formatMs(durationMs)}
        </span>
      </div>

      {/* Speed — segmented control (Hick's Law). */}
      <fieldset className="flex shrink-0 items-center gap-2">
        <legend className="sr-only">Playback speed</legend>
        <span className="font-mono text-2xs uppercase tracking-[0.16em] text-[var(--color-fg-subtle)]">
          Speed
        </span>
        <div className="inline-flex items-center gap-0.5 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-1)] p-1">
          {REPLAY_SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={speed === s}
              onClick={() => setSpeed(s)}
              className={cn(
                "rounded-md px-2.5 py-1 font-mono text-2xs font-medium tabular-nums transition-colors",
                speed === s
                  ? "bg-[var(--color-accent)] text-[var(--color-accent-fg)]"
                  : "text-[var(--color-fg-subtle)] hover:text-[var(--color-fg-muted)]",
              )}
            >
              {s}×
            </button>
          ))}
        </div>
      </fieldset>

      {isEnded && (
        <span className="sr-only" role="status">
          Replay finished
        </span>
      )}
    </div>
  );
}
