import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { CaptainCandidate, Dashboard, HistoryResponse, LabResponse, PerformanceResponse, Player, SquadInsights } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: () => request<Dashboard>("/api/dashboard"),
    staleTime: 5 * 60 * 1000,
  });
}

export function usePlayers() {
  return useQuery({
    queryKey: ["players"],
    queryFn: () => request<Player[]>("/api/players"),
    staleTime: 10 * 60 * 1000,
  });
}

export function useCaptain() {
  return useQuery({
    queryKey: ["captain"],
    queryFn: () =>
      request<{
        source: string;
        n: number;
        xi_ev: number;
        distribution: { p10: number; p50: number; p90: number };
        candidates: CaptainCandidate[];
      }>("/api/captain"),
    staleTime: 5 * 60 * 1000,
  });
}

export function usePerformance() {
  return useQuery({
    queryKey: ["performance"],
    queryFn: () => request<PerformanceResponse>("/api/performance"),
    staleTime: 10 * 60 * 1000,
  });
}

export function useSquadInsights() {
  return useQuery({
    queryKey: ["squad-insights"],
    queryFn: () => request<SquadInsights>("/api/squad-insights"),
    staleTime: 5 * 60 * 1000,
  });
}

export function useHistory() {
  return useQuery({
    queryKey: ["history"],
    queryFn: () => request<HistoryResponse>("/api/history"),
    staleTime: 5 * 60 * 1000,
  });
}

export function useLab() {
  return useQuery({
    queryKey: ["lab"],
    queryFn: () => request<LabResponse>("/api/lab"),
    staleTime: 5 * 60 * 1000,
  });
}

export function useSquadMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ids, budget }: { ids: number[]; budget: number }) =>
      request<{ ok: boolean }>("/api/squad", {
        method: "POST",
        body: JSON.stringify({ ids, budget }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["squad"] });
    },
  });
}

export function useRefresh() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => request<{ ok: boolean }>("/api/refresh", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries(),
  });
}
