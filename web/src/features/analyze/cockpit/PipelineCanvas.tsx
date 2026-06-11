/**
 * PipelineCanvas — the hero. An xyflow graph of the 12 (or 10) pipeline nodes,
 * laid out left->right in stages, that animates as the run streams.
 *
 * It is DECORATIVE-but-causal: `aria-hidden`, non-interactive (pan/zoom/drag
 * locked), and shadowed by the LiveFeed `role="status"` spine for screen
 * readers. Node visuals are a pure function of the stream-derived NodeStatus
 * map; edges animate (traveling-signal dot + marching ants) only while data is
 * actively flowing across them (NLM: weld motion to causality, 60fps via
 * transform/opacity + non-scaling stroke + pre-allocated layout = no CLS).
 *
 * @xyflow/react and its CSS resolve into the lazy Analyze chunk (this module is
 * only reachable from the Analyze route).
 */
import {
  ReactFlow,
  type Node,
  type Edge,
  type NodeProps,
  Handle,
  Position,
  BaseEdge,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/base.css";
import { Check, Minus, X } from "lucide-react";
import { memo, useMemo } from "react";

import { nodeLabel, nodePhase } from "@/features/analyze/nodeLabels";
import { cn } from "@/lib/utils";

import {
  type EdgeFlow,
  type NodeStatus,
  type Topology,
  edgeFlow,
} from "./pipeline";

/* Spatial tokens (px) — pre-allocated so the canvas never reflows mid-run. */
const COL_W = 168;
const ROW_H = 86;
const NODE_W = 132;
const NODE_H = 60;
const PAD = 24;

type FinNodeData = { status: NodeStatus; tint: string };
type FinEdgeData = { flow: EdgeFlow; tint: string };

/** Per-node accent: personas carry their own signal color, others use azure. */
function tintFor(id: string): string {
  if (id === "bull") return "var(--color-bull)";
  if (id === "bear") return "var(--color-bear)";
  if (id === "risk_conservative") return "var(--color-conservative)";
  if (id === "risk_aggressive") return "var(--color-aggressive)";
  if (id === "reporter" || id === "risk_arbiter" || id === "facilitator")
    return "var(--color-accent)";
  return "var(--color-accent)";
}

/* ---------------------------------------------------------- custom node UI */

function FinNode({ data, id }: NodeProps & { data: FinNodeData }) {
  const { status, tint } = data;
  const running = status === "running";
  const complete = status === "complete";
  const error = status === "error";
  // A stopped run (abort / terminal phase): dim the node like pending, but
  // keep its surface so it still reads as "had started" — no motion at all.
  const halted = status === "halted";

  return (
    <div
      className={cn(
        "pipe-node relative flex flex-col justify-center gap-0.5 rounded-[10px] px-3 py-2",
        running && "animate-breathe",
        complete && "animate-accent-flash",
      )}
      style={{
        width: NODE_W,
        height: NODE_H,
        transformOrigin: "center",
        background:
          status === "pending"
            ? "var(--color-surface-1)"
            : "color-mix(in oklch, var(--color-surface-2), transparent 0%)",
        border: `1px solid ${
          error
            ? "var(--color-hold)"
            : complete || running
              ? tint
              : halted
                ? "var(--color-line-strong)"
                : "var(--color-line)"
        }`,
        boxShadow:
          running || complete
            ? `0 0 0 1px ${tint}, 0 0 18px -6px ${tint}`
            : "none",
        opacity: status === "pending" || halted ? 0.55 : 1,
      }}
    >
      {/* invisible handles keep edges anchored; the graph is non-interactive */}
      <Handle type="target" position={Position.Left} className="!opacity-0" isConnectable={false} />
      <Handle type="source" position={Position.Right} className="!opacity-0" isConnectable={false} />

      <div className="flex items-center gap-1.5">
        <span
          className="grid size-3.5 shrink-0 place-items-center rounded-full"
          style={{
            background: complete
              ? tint
              : error
                ? "var(--color-hold)"
                : "transparent",
            border: complete || error ? "none" : `1.5px solid ${
              running ? tint : "var(--color-line-strong)"
            }`,
          }}
        >
          {complete && <Check className="size-2.5 text-[var(--color-accent-fg)]" strokeWidth={3} />}
          {error && <X className="size-2.5 text-[var(--color-accent-fg)]" strokeWidth={3} />}
          {halted && <Minus className="size-2.5 text-[var(--color-fg-subtle)]" strokeWidth={3} />}
        </span>
        <span className="truncate text-xs font-medium leading-tight text-[var(--color-fg)]">
          {nodeLabel(id)}
        </span>
      </div>
      <span className="pl-5 font-mono text-[9px] uppercase tracking-[0.16em] text-[var(--color-fg-subtle)]">
        {nodePhase(id)}
      </span>
    </div>
  );
}

/* ---------------------------------------------------------- custom edge UI */

function FinEdge({
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps & { data?: FinEdgeData }) {
  const [path] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });
  const flow = data?.flow ?? "idle";
  const tint = data?.tint ?? "var(--color-accent)";
  const active = flow === "live";
  const settled = flow === "settled";

  return (
    <>
      <BaseEdge
        path={path}
        className="pipe-edge"
        style={{
          stroke: settled || active ? tint : "var(--color-line)",
          strokeWidth: 1.5,
          opacity: settled ? 0.5 : active ? 0.9 : 0.3,
        }}
      />
      {active && (
        <>
          {/* marching ants overlay on the live edge */}
          <path
            d={path}
            fill="none"
            className="pipe-edge edge-flow"
            style={{ stroke: tint, strokeWidth: 1.5, opacity: 0.9 }}
          />
          {/* the traveling-signal dot crawling source -> target */}
          <circle
            r={3}
            className="animate-signal-travel"
            style={{
              offsetPath: `path('${path}')`,
              fill: tint,
              filter: `drop-shadow(0 0 4px ${tint})`,
            }}
          />
        </>
      )}
    </>
  );
}

const nodeTypes = { fin: FinNode };
const edgeTypes = { fin: FinEdge };

/* ------------------------------------------------------------- the canvas */

// React.memo + the Cockpit-side useMemo on `statuses` means the canvas (and
// its node/edge useMemos) only re-renders when the topology or a node status
// actually changed — not on every parent render.
export const PipelineCanvas = memo(function PipelineCanvas({
  topology,
  statuses,
}: {
  topology: Topology;
  statuses: Record<string, NodeStatus>;
}) {
  const nodes: Node[] = useMemo(
    () =>
      topology.nodes.map((n) => ({
        id: n.id,
        type: "fin",
        position: { x: PAD + n.col * COL_W, y: PAD + n.row * ROW_H },
        data: { status: statuses[n.id] ?? "pending", tint: tintFor(n.id) },
        draggable: false,
        selectable: false,
        connectable: false,
        width: NODE_W,
        height: NODE_H,
      })),
    [topology, statuses],
  );

  const edges: Edge[] = useMemo(
    () =>
      topology.edges.map((e) => ({
        id: `${e.from}->${e.to}`,
        source: e.from,
        target: e.to,
        type: "fin",
        data: { flow: edgeFlow(e, statuses), tint: tintFor(e.from) },
      })),
    [topology, statuses],
  );

  const height = PAD * 2 + 3 * ROW_H + (NODE_H - ROW_H);

  return (
    <div
      aria-hidden="true"
      className="overflow-hidden rounded-xl border border-[var(--color-line)] bg-[var(--color-base)]/40"
      style={{ height }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        panOnScroll={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        preventScrolling={false}
        proOptions={{ hideAttribution: true }}
        minZoom={0.4}
        maxZoom={1.4}
      />
    </div>
  );
});
