"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type {
  ExtractFromTextRequest,
  TrainerProfile,
  TrainerProfileUpdate,
} from "@/features/trainer/types";

const PROFILE_KEY = ["trainer", "profile"] as const;

export function useTrainerProfile() {
  return useQuery({
    queryKey: PROFILE_KEY,
    queryFn: async (): Promise<TrainerProfile | null> => {
      try {
        return await api.get<TrainerProfile>("/api/v1/trainer/profile");
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
    staleTime: 60 * 1000,
    retry: (failureCount, err) => {
      if (err instanceof ApiError && err.status === 404) return false;
      return failureCount < 2;
    },
  });
}

export function useExtractProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: ExtractFromTextRequest) =>
      api.post<TrainerProfile>("/api/v1/trainer/extract", req),
    onSuccess: () => void qc.invalidateQueries({ queryKey: PROFILE_KEY }),
  });
}

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (update: TrainerProfileUpdate) =>
      api.patch<TrainerProfile>("/api/v1/trainer/profile", update),
    onSuccess: () => void qc.invalidateQueries({ queryKey: PROFILE_KEY }),
  });
}

export function useLockProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<TrainerProfile>("/api/v1/trainer/profile/lock", {}),
    onSuccess: () => void qc.invalidateQueries({ queryKey: PROFILE_KEY }),
  });
}
