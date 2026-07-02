"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  IndustryAnalysisOut,
  LeadConversionOut,
  LeadPipelineSummaryOut,
  SourceAnalysisOut,
  StageAnalysisOut,
} from "@/features/crm/types";

const STALE_MS = 15 * 60 * 1000; // 900s — matches backend Redis TTL

const PIPELINE_SUMMARY_KEY = (workspaceId: string) =>
  ["lead-pipeline", "summary", workspaceId] as const;
const PIPELINE_STAGES_KEY = (workspaceId: string) =>
  ["lead-pipeline", "stages", workspaceId] as const;
const PIPELINE_SOURCES_KEY = (workspaceId: string) =>
  ["lead-pipeline", "sources", workspaceId] as const;
const PIPELINE_INDUSTRIES_KEY = (workspaceId: string) =>
  ["lead-pipeline", "industries", workspaceId] as const;
const PIPELINE_CONVERSION_KEY = (workspaceId: string) =>
  ["lead-pipeline", "conversion", workspaceId] as const;

export function usePipelineSummary(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: PIPELINE_SUMMARY_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<LeadPipelineSummaryOut>(
        `/api/v1/lead-pipeline/summary?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: STALE_MS,
  });
}

export function usePipelineStages(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: PIPELINE_STAGES_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<StageAnalysisOut>(
        `/api/v1/lead-pipeline/stages?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: STALE_MS,
  });
}

export function usePipelineSources(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: PIPELINE_SOURCES_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<SourceAnalysisOut>(
        `/api/v1/lead-pipeline/sources?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: STALE_MS,
  });
}

export function usePipelineIndustries(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: PIPELINE_INDUSTRIES_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<IndustryAnalysisOut>(
        `/api/v1/lead-pipeline/industries?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: STALE_MS,
  });
}

export function usePipelineConversion(workspaceId: string | null | undefined) {
  return useQuery({
    queryKey: PIPELINE_CONVERSION_KEY(workspaceId ?? ""),
    queryFn: () =>
      api.get<LeadConversionOut>(
        `/api/v1/lead-pipeline/conversion?workspace_id=${workspaceId}`,
      ),
    enabled: !!workspaceId,
    staleTime: STALE_MS,
  });
}
