import { useQuery } from "@tanstack/react-query";

import { api, deriveQuotaState, type QuotaState } from "@/lib/api";

/** Polls /api/quota and derives the human-facing pill state. */
export function useQuota(): { quota: QuotaState; isLoading: boolean } {
  const query = useQuery({
    queryKey: ["quota"],
    queryFn: ({ signal }) => api.quota(signal),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 0,
  });

  return {
    quota: deriveQuotaState(query.data),
    isLoading: query.isLoading,
  };
}
