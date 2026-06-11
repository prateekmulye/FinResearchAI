# FinResearch — Design System

**Mood:** _Glass-SaaS shell × Terminal data surfaces._ A Linear/Vercel-grade
glassmorphism app shell (glass nav, soft aurora gradients, rounded geometry,
spring motion) **wrapping** Bloomberg-terminal data surfaces (dense, monospace,
tabular numerics, amber/green/red signal colors, live streaming feeds).
**Dark-first, no light theme.**

This file is the source of truth for WP-7..10. Tokens are implemented in
`src/styles/index.css` under Tailwind v4 `@theme`; use the token names below
(never raw hex). When in doubt: **the glass shell refines; the terminal informs.**

---

## 1. The one rule that makes the fusion work

The two visual languages do **not** sit side by side — that clashes. They nest:

> **The refined glass shell is the _frame/moderator_. Bloomberg-style density is
> restricted to inner "terminal tiles" within an asymmetric bento grid. The shell
> moderates the technical noise.** _(NotebookLM: Aesthetic-Usability / System Fusion.)_

Practically: a `GlassCard` (or `glass-strong` nav) is the container; dense
mono data (`terminal-tile`, tables, token streams, node labels) lives **inside**
it. Never put a backdrop-blur on a data tile — keep blur on the top-level shell
only (GPU budget; avoids halation behind numbers).

**Onion-Peel progressive disclosure:** show editorial summaries by default;
reveal raw metadata (tool-call hashes, raw logs, full deltas) on demand via glass
drawers. Keeps a recruiter oriented; rewards the engineer who digs.

---

## 2. Color — OKLCH, AAA on primary data

OKLCH so the luminous signal glow stays perceptually uniform across blurred glass
layers. Contrast targets, honestly stated: **7:1 (AAA)** on primary data values
(`--color-fg`, >12:1 on base) to prevent halation; secondary/subtle data text
(`--color-fg-muted`, `--color-fg-subtle` ≈ 4.7:1) meets **4.5:1 (AA)**, not AAA.

### Surfaces (asphalt blue-black, 4-step elevation)

| Token                 | Value                   | Use                                 |
| --------------------- | ----------------------- | ----------------------------------- |
| `--color-base`        | `oklch(12% .015 260)`   | Page background (behind the aurora) |
| `--color-surface-1`   | `oklch(15.5% .016 260)` | Resting card / terminal-tile fill   |
| `--color-surface-2`   | `oklch(19% .018 260)`   | Inputs, raised cards                |
| `--color-surface-3`   | `oklch(24% .02 260)`    | Popovers, active table rows         |
| `--color-line`        | `white / 8%`            | Hairline dividers, default borders  |
| `--color-line-strong` | `white / 14%`           | Emphasized borders, scrollbar thumb |

### Glass (the SaaS shell)

| Token                  | Value         | Use                              |
| ---------------------- | ------------- | -------------------------------- |
| `--color-glass`        | `white / 5%`  | Standard glass fill (`.glass`)   |
| `--color-glass-strong` | `white / 8%`  | Nav, floating glass, active pill |
| `--color-glass-border` | `white / 12%` | Glass edge highlight             |
| `--blur-glass`         | `16px`        | Standard shell blur              |
| `--blur-glass-strong`  | `28px`        | Floating nav / modal blur        |

### Text

| Token               | Value                 | Use                                |
| ------------------- | --------------------- | ---------------------------------- |
| `--color-fg`        | `oklch(96% .008 260)` | Primary (>12:1 on base)            |
| `--color-fg-muted`  | `oklch(74% .012 260)` | Secondary / descriptions           |
| `--color-fg-subtle` | `oklch(58% .012 260)` | Tertiary / mono kickers / disabled |

### Functional accent (azure) — interaction, never decoration

| Token                   | Value                | Use                                          |
| ----------------------- | -------------------- | -------------------------------------------- |
| `--color-accent`        | `oklch(70% .13 245)` | Links, focus ring, caret, active signal, CTA |
| `--color-accent-strong` | `oklch(78% .14 245)` | Accent hover                                 |
| `--color-accent-fg`     | `oklch(16% .03 260)` | Text on accent fills                         |

Azure is **functional only** — if it's azure, it's interactive or "the live
signal." Don't tint decorative chrome with it.

### Signal colors (Bloomberg energy) — meaning-bearing

These carry semantics across **both** the decision verdict and the live debate.
**Never rely on color alone** — always pair with a glyph and/or the literal word
(Von Restorff + accessibility).

| Token                  | Value                | Meaning                                 |
| ---------------------- | -------------------- | --------------------------------------- |
| `--color-bull`         | `oklch(72% .15 152)` | BUY · bull · positive · healthy · done  |
| `--color-bear`         | `oklch(64% .19 22)`  | SELL · bear · negative · error          |
| `--color-hold`         | `oklch(80% .15 78)`  | HOLD · amber · warn · degraded · replay |
| `--color-conservative` | `oklch(70% .1 230)`  | Conservative risk persona (cool)        |
| `--color-aggressive`   | `oklch(74% .16 35)`  | Aggressive risk persona (hot)           |

`*-dim` variants (e.g. `--color-bull-dim`) are the low-alpha fills for badges.

---

## 3. Typography

- **UI / display: Inter Variable** (self-hosted, `@fontsource-variable/inter`).
  Nav, labels, headings, body. "Professional maturity." Body floor **16px /
  1.55**. Headings use `tracking-tight`.
- **Data: JetBrains Mono Variable** (self-hosted). **All** numerics, tickers,
  node ids, token streams, cost/latency, code, mono kickers. Always
  `font-variant-numeric: tabular-nums` (set globally on `.font-mono`) — kills
  horizontal jitter as SSE values update.
- **Scale: 1.25 Major Third**, tokens `--text-2xs … --text-4xl` with paired
  line-heights. `2xs` (11px) is the dense-terminal floor; don't go smaller.

**Mono kicker pattern:** uppercase, `tracking-[0.18em]`, `--text-2xs`, in
`--color-accent` or `--color-fg-subtle` — the recurring "eyebrow" that signals a
terminal section (see `PageHeader`, `EmptyState`).

---

## 4. Spacing, radius, elevation

- **Spacing:** Tailwind's default 4px scale. Card padding `p-5 sm:p-6`; section
  rhythm `space-y-8`; max content width `max-w-7xl`.
- **Radius:** `--radius-xs .25rem` → `--radius-2xl 1.75rem`. Glass cards/nav use
  `2xl`; terminal tiles use `md`; pills are fully round.
- **Elevation:** `--shadow-glass` (resting), `--shadow-raised` (modal/popover),
  `--shadow-glow-accent` (accent CTA hover). Shadows are **base-tinted, never
  pure black**, with a 1px inner top highlight for the "lit glass" edge.

---

## 5. Motion — one physics language across shell + terminal

Shared spring bridges the static-terminal feel and the fluid shell:
**`{ stiffness: 150, damping: 15, mass: 0.1 }`** (exposed as CSS vars for JS).

| Token              | Value                      | Use                                       |
| ------------------ | -------------------------- | ----------------------------------------- |
| `--duration-micro` | 120ms                      | Hover / press (Button `active:scale-.97`) |
| `--duration-fast`  | 200ms                      | The SSE **luminous-accent flash**         |
| `--duration-base`  | 320ms                      | Page + card transitions (< Doherty 400ms) |
| `--duration-slow`  | 600ms                      | Onion-peel drawer reveal                  |
| `--ease-spring`    | `cubic-bezier(.16,1,.3,1)` | Glass settle, drawers, buttons            |

**Doherty Threshold:** interactive feedback < 50ms, any animation < 400ms.

**Signature interactions:**

- **Luminous-accent flash** (`@keyframes fin-accent-flash` / `.animate-accent-flash`):
  on `node_complete`, the node tile dips to `scale(.95)` then snaps to `1.1` and
  settles — "load before release." Welds the number/state change to visible
  motion (causality, not decoration). Use it whenever live data lands on a tile.
- **Breathing** (`.animate-breathe`, 2600ms): the active/live element (health
  dot, the currently-generating node). Scale 1→1.05, opacity .8→1.
- **Nav active pill:** one shared Motion `layoutId="nav-active-pill"` slides
  between tabs (continuous element, spring). Deliberate exception to the shared
  spring: it hardcodes `{ stiffness: 380, damping: 32, mass: 0.8 }` — a tighter,
  faster settle tuned for high-frequency tab switching.
- **Page transition:** 280ms fade + 8px lift, spring easing, keyed on pathname.
- **Aurora:** two blurred blobs on 64s/88s linear rotations (transform-only,
  compositor thread, zero JS).

**Reduced motion:** a global `@media (prefers-reduced-motion: reduce)` block
zeroes all durations and kills the breathe/flash/aurora; `useReducedMotion()`
additionally opts JS-driven Motion springs out. Everything must remain fully
usable and legible static.

---

## 6. Texture — the "glue"

One fixed fractal-noise overlay (`#fin-grain` filter in `index.html`, applied via
`.grain` on the shell root, ~3.5% opacity, `mix-blend-mode: overlay`). Reads as
Bloomberg CRT phosphor + editorial paper at once; its job is to keep the surface
from looking like flat "AI slop." Defined once, GPU-cached, never in the React tree.

---

## 7. Component vocabulary (WP-6 inventory)

Shell: `AppShell`, `TopNav`, `Footer`, `AuroraBackground`, `PageTransition`,
`Wordmark`, `HealthDot`, `QuotaPill`.
UI: `Button` (primary/glass/ghost/outline), `GlassCard`, `PageHeader`,
`EmptyState`, `SignalBadge` (BUY/SELL/HOLD).
Analyze feature: `AnalyzeForm`, `LiveFeed`, `nodeLabels`.

**Conventions WP-7..10 must keep:**

1. Glass frames contain terminal tiles — never the reverse.
2. Every numeric is `font-mono` + tabular.
3. Signal color always backed by glyph + word.
4. Mono uppercase kicker introduces terminal sections.
5. New live surfaces fire the luminous-accent flash on data arrival and ship a
   parallel `aria-live` semantic log (the canvas, when added, is `aria-hidden`).
6. Respect the focus-visible azure ring; AA contrast minimum everywhere, AAA on primary data values (secondary/subtle data text is AA — see §2).
