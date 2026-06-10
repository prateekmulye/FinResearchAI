/**
 * dossierRange — the range-selector vocabulary for the price panel. Each option
 * maps a human label to the `days` query param the prices endpoint takes. MAX
 * uses the backend's clamp ceiling (10 years) so "MAX" means "everything stored"
 * without a magic number leaking into the component.
 */
export type RangeKey = "3M" | "6M" | "1Y" | "MAX";

export const RANGE_OPTIONS: { key: RangeKey; days: number; label: string }[] = [
  { key: "3M", days: 90, label: "3M" },
  { key: "6M", days: 182, label: "6M" },
  { key: "1Y", days: 365, label: "1Y" },
  { key: "MAX", days: 3650, label: "MAX" },
];

export const DEFAULT_RANGE: RangeKey = "1Y";

export function daysForRange(key: RangeKey): number {
  return RANGE_OPTIONS.find((o) => o.key === key)?.days ?? 365;
}
