import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type HealthState = "ok" | "down" | "checking";

/** Polls /healthz so the shell can render a live status dot. */
export function useHealth(): { state: HealthState; isFetching: boolean } {
  const query = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => api.health(signal),
    refetchInterval: 20_000,
    staleTime: 10_000,
    retry: 0,
  });

  const state: HealthState = query.isError ? "down" : query.data ? "ok" : "checking";

  return { state, isFetching: query.isFetching };
}
