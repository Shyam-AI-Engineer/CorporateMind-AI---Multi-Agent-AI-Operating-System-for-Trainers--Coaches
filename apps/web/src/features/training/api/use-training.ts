"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  CancelEngagement,
  CancelSession,
  CheckOutAttendance,
  CompleteEngagement,
  CompleteSession,
  CoordinatorAssign,
  IssueCertificate,
  RevokeCertificate,
  SessionTrainerAssign,
  TrainerAssign,
  TrainingAttendance,
  TrainingAttendanceCreate,
  TrainingAttendanceFilters,
  TrainingAttendanceListOut,
  TrainingAttendanceUpdate,
  TrainingCertificate,
  TrainingCertificateCreate,
  TrainingCertificateFilters,
  TrainingCertificateListOut,
  TrainingCertificateUpdate,
  TrainingEngagement,
  TrainingEngagementCreate,
  TrainingEngagementFilters,
  TrainingEngagementListOut,
  TrainingEngagementUpdate,
  TrainingFeedback,
  TrainingFeedbackCreate,
  TrainingFeedbackFilters,
  TrainingFeedbackListOut,
  TrainingFeedbackUpdate,
  TrainingSession,
  TrainingSessionCreate,
  TrainingSessionFilters,
  TrainingSessionListOut,
  TrainingSessionUpdate,
} from "@/features/training/types";

const STALE_MS = 300_000;

const LIST_KEY = (workspaceId: string, filters?: Partial<TrainingEngagementFilters>) =>
  ["training", "list", workspaceId, filters ?? {}] as const;

const DETAIL_KEY = (id: string) => ["training", "detail", id] as const;

function useInvalidateTraining(workspaceId: string | null | undefined) {
  const qc = useQueryClient();
  return (engagementId?: string) => {
    if (workspaceId) {
      void qc.invalidateQueries({ queryKey: ["training", "list", workspaceId] });
    }
    if (engagementId) void qc.invalidateQueries({ queryKey: DETAIL_KEY(engagementId) });
  };
}

export function useTrainingEngagements(filters: TrainingEngagementFilters | null | undefined) {
  const workspaceId = filters?.workspace_id ?? "";
  return useQuery<{ data: TrainingEngagementListOut }>({
    queryKey: LIST_KEY(workspaceId, filters ?? {}),
    queryFn: () => {
      if (!workspaceId) throw new Error("workspace_id required");
      const params = new URLSearchParams({ workspace_id: workspaceId });
      if (filters?.status) params.set("status", filters.status);
      if (filters?.trainer_id) params.set("trainer_id", filters.trainer_id);
      if (filters?.customer_id) params.set("customer_id", filters.customer_id);
      if (filters?.delivery_mode) params.set("delivery_mode", filters.delivery_mode);
      if (filters?.date_from) params.set("date_from", filters.date_from);
      if (filters?.date_to) params.set("date_to", filters.date_to);
      if (filters?.search) params.set("search", filters.search);
      if (filters?.cursor) params.set("cursor", filters.cursor);
      if (filters?.limit) params.set("limit", String(filters.limit));
      return api.get<{ data: TrainingEngagementListOut }>(
        `/api/v1/training-engagements?${params}`
      );
    },
    staleTime: STALE_MS,
    enabled: !!workspaceId,
  });
}

export function useTrainingEngagement(engagementId: string | null | undefined) {
  return useQuery<{ data: TrainingEngagement }>({
    queryKey: DETAIL_KEY(engagementId ?? ""),
    queryFn: () =>
      api.get<{ data: TrainingEngagement }>(
        `/api/v1/training-engagements/${engagementId}`
      ),
    staleTime: STALE_MS,
    enabled: !!engagementId,
  });
}

export function useCreateTrainingEngagement(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateTraining(workspaceId);
  return useMutation<{ data: TrainingEngagement }, Error, TrainingEngagementCreate>({
    mutationFn: (body) =>
      api.post<{ data: TrainingEngagement }>("/api/v1/training-engagements/", body),
    onSuccess: () => invalidate(),
  });
}

export function useUpdateTrainingEngagement(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateTraining(workspaceId);
  return useMutation<
    { data: TrainingEngagement },
    Error,
    { id: string; body: TrainingEngagementUpdate }
  >({
    mutationFn: ({ id, body }) =>
      api.patch<{ data: TrainingEngagement }>(
        `/api/v1/training-engagements/${id}`,
        body
      ),
    onSuccess: (_, { id }) => invalidate(id),
  });
}

export function useStartEngagement(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateTraining(workspaceId);
  return useMutation<{ data: TrainingEngagement }, Error, string>({
    mutationFn: (id) =>
      api.post<{ data: TrainingEngagement }>(
        `/api/v1/training-engagements/${id}/start`,
        {}
      ),
    onSuccess: (_, id) => invalidate(id),
  });
}

export function useCompleteEngagement(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateTraining(workspaceId);
  return useMutation<
    { data: TrainingEngagement },
    Error,
    { id: string; body: CompleteEngagement }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: TrainingEngagement }>(
        `/api/v1/training-engagements/${id}/complete`,
        body
      ),
    onSuccess: (_, { id }) => invalidate(id),
  });
}

export function useCancelEngagement(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateTraining(workspaceId);
  return useMutation<
    { data: TrainingEngagement },
    Error,
    { id: string; body: CancelEngagement }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: TrainingEngagement }>(
        `/api/v1/training-engagements/${id}/cancel`,
        body
      ),
    onSuccess: (_, { id }) => invalidate(id),
  });
}

export function useAssignTrainer(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateTraining(workspaceId);
  return useMutation<
    { data: TrainingEngagement },
    Error,
    { id: string; body: TrainerAssign }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: TrainingEngagement }>(
        `/api/v1/training-engagements/${id}/assign-trainer`,
        body
      ),
    onSuccess: (_, { id }) => invalidate(id),
  });
}

export function useAssignCoordinator(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateTraining(workspaceId);
  return useMutation<
    { data: TrainingEngagement },
    Error,
    { id: string; body: CoordinatorAssign }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: TrainingEngagement }>(
        `/api/v1/training-engagements/${id}/assign-coordinator`,
        body
      ),
    onSuccess: (_, { id }) => invalidate(id),
  });
}

// ── Training Session hooks ─────────────────────────────────────────────────────

const SESSION_LIST_KEY = (
  workspaceId: string,
  filters?: Partial<TrainingSessionFilters>,
) => ["training", "sessions", "list", workspaceId, filters ?? {}] as const;

const SESSION_DETAIL_KEY = (id: string) =>
  ["training", "sessions", "detail", id] as const;

const ENGAGEMENT_SESSIONS_KEY = (engagementId: string) =>
  ["training", "sessions", "by-engagement", engagementId] as const;

function useInvalidateSessions(workspaceId: string | null | undefined) {
  const qc = useQueryClient();
  return (sessionId?: string, engagementId?: string) => {
    if (workspaceId) {
      void qc.invalidateQueries({
        queryKey: ["training", "sessions", "list", workspaceId],
      });
    }
    if (sessionId) {
      void qc.invalidateQueries({ queryKey: SESSION_DETAIL_KEY(sessionId) });
    }
    if (engagementId) {
      void qc.invalidateQueries({
        queryKey: ENGAGEMENT_SESSIONS_KEY(engagementId),
      });
    }
  };
}

export function useTrainingSessions(
  filters: TrainingSessionFilters | null | undefined,
) {
  const workspaceId = filters?.workspace_id ?? "";
  return useQuery<{ data: TrainingSessionListOut }>({
    queryKey: SESSION_LIST_KEY(workspaceId, filters ?? {}),
    queryFn: () => {
      if (!workspaceId) throw new Error("workspace_id required");
      const params = new URLSearchParams({ workspace_id: workspaceId });
      if (filters?.engagement_id) params.set("engagement_id", filters.engagement_id);
      if (filters?.trainer_id) params.set("trainer_id", filters.trainer_id);
      if (filters?.status) params.set("status", filters.status);
      if (filters?.date_from) params.set("date_from", filters.date_from);
      if (filters?.date_to) params.set("date_to", filters.date_to);
      if (filters?.cursor) params.set("cursor", filters.cursor);
      if (filters?.limit) params.set("limit", String(filters.limit));
      return api.get<{ data: TrainingSessionListOut }>(
        `/api/v1/training-sessions?${params}`,
      );
    },
    staleTime: STALE_MS,
    enabled: !!workspaceId,
  });
}

export function useEngagementSessions(engagementId: string | null | undefined) {
  return useQuery<{ data: TrainingSession[] }>({
    queryKey: ENGAGEMENT_SESSIONS_KEY(engagementId ?? ""),
    queryFn: () =>
      api.get<{ data: TrainingSession[] }>(
        `/api/v1/training-engagements/${engagementId}/sessions`,
      ),
    staleTime: STALE_MS,
    enabled: !!engagementId,
  });
}

export function useTrainingSession(sessionId: string | null | undefined) {
  return useQuery<{ data: TrainingSession }>({
    queryKey: SESSION_DETAIL_KEY(sessionId ?? ""),
    queryFn: () =>
      api.get<{ data: TrainingSession }>(
        `/api/v1/training-sessions/${sessionId}`,
      ),
    staleTime: STALE_MS,
    enabled: !!sessionId,
  });
}

export function useCreateTrainingSession(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateSessions(workspaceId);
  return useMutation<{ data: TrainingSession }, Error, TrainingSessionCreate>({
    mutationFn: (body) =>
      api.post<{ data: TrainingSession }>("/api/v1/training-sessions/", body),
    onSuccess: (data) =>
      invalidate(data.data.id, data.data.engagement_id),
  });
}

export function useUpdateTrainingSession(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateSessions(workspaceId);
  return useMutation<
    { data: TrainingSession },
    Error,
    { id: string; engagementId: string; body: TrainingSessionUpdate }
  >({
    mutationFn: ({ id, body }) =>
      api.patch<{ data: TrainingSession }>(
        `/api/v1/training-sessions/${id}`,
        body,
      ),
    onSuccess: (_, { id, engagementId }) => invalidate(id, engagementId),
  });
}

export function useStartSession(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateSessions(workspaceId);
  return useMutation<
    { data: TrainingSession },
    Error,
    { id: string; engagementId: string }
  >({
    mutationFn: ({ id }) =>
      api.post<{ data: TrainingSession }>(
        `/api/v1/training-sessions/${id}/start`,
        {},
      ),
    onSuccess: (_, { id, engagementId }) => invalidate(id, engagementId),
  });
}

export function useCompleteSession(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateSessions(workspaceId);
  return useMutation<
    { data: TrainingSession },
    Error,
    { id: string; engagementId: string; body: CompleteSession }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: TrainingSession }>(
        `/api/v1/training-sessions/${id}/complete`,
        body,
      ),
    onSuccess: (_, { id, engagementId }) => invalidate(id, engagementId),
  });
}

export function useCancelSession(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateSessions(workspaceId);
  return useMutation<
    { data: TrainingSession },
    Error,
    { id: string; engagementId: string; body: CancelSession }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: TrainingSession }>(
        `/api/v1/training-sessions/${id}/cancel`,
        body,
      ),
    onSuccess: (_, { id, engagementId }) => invalidate(id, engagementId),
  });
}

export function useAssignSessionTrainer(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateSessions(workspaceId);
  return useMutation<
    { data: TrainingSession },
    Error,
    { id: string; engagementId: string; body: SessionTrainerAssign }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: TrainingSession }>(
        `/api/v1/training-sessions/${id}/assign-trainer`,
        body,
      ),
    onSuccess: (_, { id, engagementId }) => invalidate(id, engagementId),
  });
}

// ── Attendance hooks ───────────────────────────────────────────────────────────

const ATTENDANCE_LIST_KEY = (
  workspaceId: string,
  filters?: Partial<TrainingAttendanceFilters>,
) => ["training", "attendance", "list", workspaceId, filters ?? {}] as const;

const ATTENDANCE_DETAIL_KEY = (id: string) =>
  ["training", "attendance", "detail", id] as const;

const SESSION_ATTENDANCE_KEY = (sessionId: string) =>
  ["training", "attendance", "by-session", sessionId] as const;

function useInvalidateAttendance(workspaceId: string | null | undefined) {
  const qc = useQueryClient();
  return (attendanceId?: string, sessionId?: string) => {
    if (workspaceId) {
      void qc.invalidateQueries({
        queryKey: ["training", "attendance", "list", workspaceId],
      });
    }
    if (attendanceId) {
      void qc.invalidateQueries({ queryKey: ATTENDANCE_DETAIL_KEY(attendanceId) });
    }
    if (sessionId) {
      void qc.invalidateQueries({ queryKey: SESSION_ATTENDANCE_KEY(sessionId) });
    }
  };
}

export function useAttendanceList(
  filters: TrainingAttendanceFilters | null | undefined,
) {
  const workspaceId = filters?.workspace_id ?? "";
  return useQuery<{ data: TrainingAttendanceListOut }>({
    queryKey: ATTENDANCE_LIST_KEY(workspaceId, filters ?? {}),
    queryFn: () => {
      if (!workspaceId) throw new Error("workspace_id required");
      const params = new URLSearchParams({ workspace_id: workspaceId });
      if (filters?.session_id) params.set("session_id", filters.session_id);
      if (filters?.attendance_status)
        params.set("attendance_status", filters.attendance_status);
      if (filters?.company) params.set("company", filters.company);
      if (filters?.search) params.set("search", filters.search);
      if (filters?.cursor) params.set("cursor", filters.cursor);
      if (filters?.limit) params.set("limit", String(filters.limit));
      return api.get<{ data: TrainingAttendanceListOut }>(
        `/api/v1/training-attendance?${params}`,
      );
    },
    staleTime: STALE_MS,
    enabled: !!workspaceId,
  });
}

export function useSessionAttendance(sessionId: string | null | undefined) {
  return useQuery<{ data: TrainingAttendance[] }>({
    queryKey: SESSION_ATTENDANCE_KEY(sessionId ?? ""),
    queryFn: () =>
      api.get<{ data: TrainingAttendance[] }>(
        `/api/v1/training-sessions/${sessionId}/attendance`,
      ),
    staleTime: STALE_MS,
    enabled: !!sessionId,
  });
}

export function useAttendanceRecord(attendanceId: string | null | undefined) {
  return useQuery<{ data: TrainingAttendance }>({
    queryKey: ATTENDANCE_DETAIL_KEY(attendanceId ?? ""),
    queryFn: () =>
      api.get<{ data: TrainingAttendance }>(
        `/api/v1/training-attendance/${attendanceId}`,
      ),
    staleTime: STALE_MS,
    enabled: !!attendanceId,
  });
}

export function useRegisterParticipant(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateAttendance(workspaceId);
  return useMutation<{ data: TrainingAttendance }, Error, TrainingAttendanceCreate>({
    mutationFn: (body) =>
      api.post<{ data: TrainingAttendance }>("/api/v1/training-attendance/", body),
    onSuccess: (data) => invalidate(data.data.id, data.data.session_id),
  });
}

export function useUpdateAttendance(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateAttendance(workspaceId);
  return useMutation<
    { data: TrainingAttendance },
    Error,
    { id: string; sessionId: string; body: TrainingAttendanceUpdate }
  >({
    mutationFn: ({ id, body }) =>
      api.patch<{ data: TrainingAttendance }>(
        `/api/v1/training-attendance/${id}`,
        body,
      ),
    onSuccess: (_, { id, sessionId }) => invalidate(id, sessionId),
  });
}

export function useMarkPresent(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateAttendance(workspaceId);
  return useMutation<
    { data: TrainingAttendance },
    Error,
    { id: string; sessionId: string }
  >({
    mutationFn: ({ id }) =>
      api.post<{ data: TrainingAttendance }>(
        `/api/v1/training-attendance/${id}/present`,
        {},
      ),
    onSuccess: (_, { id, sessionId }) => invalidate(id, sessionId),
  });
}

export function useMarkLate(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateAttendance(workspaceId);
  return useMutation<
    { data: TrainingAttendance },
    Error,
    { id: string; sessionId: string }
  >({
    mutationFn: ({ id }) =>
      api.post<{ data: TrainingAttendance }>(
        `/api/v1/training-attendance/${id}/late`,
        {},
      ),
    onSuccess: (_, { id, sessionId }) => invalidate(id, sessionId),
  });
}

export function useMarkAbsent(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateAttendance(workspaceId);
  return useMutation<
    { data: TrainingAttendance },
    Error,
    { id: string; sessionId: string }
  >({
    mutationFn: ({ id }) =>
      api.post<{ data: TrainingAttendance }>(
        `/api/v1/training-attendance/${id}/absent`,
        {},
      ),
    onSuccess: (_, { id, sessionId }) => invalidate(id, sessionId),
  });
}

export function useMarkLeftEarly(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateAttendance(workspaceId);
  return useMutation<
    { data: TrainingAttendance },
    Error,
    { id: string; sessionId: string }
  >({
    mutationFn: ({ id }) =>
      api.post<{ data: TrainingAttendance }>(
        `/api/v1/training-attendance/${id}/left-early`,
        {},
      ),
    onSuccess: (_, { id, sessionId }) => invalidate(id, sessionId),
  });
}

export function useCheckOut(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateAttendance(workspaceId);
  return useMutation<
    { data: TrainingAttendance },
    Error,
    { id: string; sessionId: string; body: CheckOutAttendance }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: TrainingAttendance }>(
        `/api/v1/training-attendance/${id}/check-out`,
        body,
      ),
    onSuccess: (_, { id, sessionId }) => invalidate(id, sessionId),
  });
}

// ── Certificate hooks ──────────────────────────────────────────────────────────

const CERT_LIST_KEY = (
  workspaceId: string,
  filters?: Partial<TrainingCertificateFilters>,
) => ["training", "certificates", "list", workspaceId, filters ?? {}] as const;

const CERT_DETAIL_KEY = (id: string) =>
  ["training", "certificates", "detail", id] as const;

function useInvalidateCertificates(workspaceId: string | null | undefined) {
  const qc = useQueryClient();
  return (certId?: string, sessionId?: string) => {
    if (workspaceId) {
      void qc.invalidateQueries({
        queryKey: ["training", "certificates", "list", workspaceId],
      });
    }
    if (certId) {
      void qc.invalidateQueries({ queryKey: CERT_DETAIL_KEY(certId) });
    }
    if (sessionId) {
      void qc.invalidateQueries({
        queryKey: ["training", "certificates", "list"],
      });
    }
  };
}

export function useCertificateList(
  filters: TrainingCertificateFilters | null | undefined,
) {
  const workspaceId = filters?.workspace_id ?? "";
  return useQuery<{ data: TrainingCertificateListOut }>({
    queryKey: CERT_LIST_KEY(workspaceId, filters ?? {}),
    queryFn: () => {
      if (!workspaceId) throw new Error("workspace_id required");
      const params = new URLSearchParams({ workspace_id: workspaceId });
      if (filters?.session_id) params.set("session_id", filters.session_id);
      if (filters?.status) params.set("status", filters.status);
      if (filters?.issued_by) params.set("issued_by", filters.issued_by);
      if (filters?.search) params.set("search", filters.search);
      if (filters?.cursor) params.set("cursor", filters.cursor);
      if (filters?.limit) params.set("limit", String(filters.limit));
      return api.get<{ data: TrainingCertificateListOut }>(
        `/api/v1/training-certificates?${params}`,
      );
    },
    staleTime: STALE_MS,
    enabled: !!workspaceId,
  });
}

export function useCertificate(certId: string | null | undefined) {
  return useQuery<{ data: TrainingCertificate }>({
    queryKey: CERT_DETAIL_KEY(certId ?? ""),
    queryFn: () =>
      api.get<{ data: TrainingCertificate }>(
        `/api/v1/training-certificates/${certId}`,
      ),
    staleTime: STALE_MS,
    enabled: !!certId,
  });
}

export function useCreateCertificate(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateCertificates(workspaceId);
  return useMutation<
    { data: TrainingCertificate },
    Error,
    TrainingCertificateCreate
  >({
    mutationFn: (body) =>
      api.post<{ data: TrainingCertificate }>(
        "/api/v1/training-certificates/",
        body,
      ),
    onSuccess: (data) =>
      invalidate(data.data.id, data.data.session_id),
  });
}

export function useUpdateCertificate(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateCertificates(workspaceId);
  return useMutation<
    { data: TrainingCertificate },
    Error,
    { id: string; sessionId: string; body: TrainingCertificateUpdate }
  >({
    mutationFn: ({ id, body }) =>
      api.patch<{ data: TrainingCertificate }>(
        `/api/v1/training-certificates/${id}`,
        body,
      ),
    onSuccess: (_, { id, sessionId }) => invalidate(id, sessionId),
  });
}

export function useIssueCertificate(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateCertificates(workspaceId);
  return useMutation<
    { data: TrainingCertificate },
    Error,
    { id: string; sessionId: string; body: IssueCertificate }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: TrainingCertificate }>(
        `/api/v1/training-certificates/${id}/issue`,
        body,
      ),
    onSuccess: (_, { id, sessionId }) => invalidate(id, sessionId),
  });
}

export function useRevokeCertificate(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateCertificates(workspaceId);
  return useMutation<
    { data: TrainingCertificate },
    Error,
    { id: string; sessionId: string; body: RevokeCertificate }
  >({
    mutationFn: ({ id, body }) =>
      api.post<{ data: TrainingCertificate }>(
        `/api/v1/training-certificates/${id}/revoke`,
        body,
      ),
    onSuccess: (_, { id, sessionId }) => invalidate(id, sessionId),
  });
}

// ── Feedback hooks ────────────────────────────────────────────────────────────

const FEEDBACK_LIST_KEY = (
  workspaceId: string,
  filters?: Partial<TrainingFeedbackFilters>,
) => ["training-feedback", "list", workspaceId, filters ?? {}] as const;

const FEEDBACK_DETAIL_KEY = (id: string) =>
  ["training-feedback", "detail", id] as const;

function useInvalidateFeedback(workspaceId: string | null | undefined) {
  const qc = useQueryClient();
  return (feedbackId: string, sessionId: string) => {
    if (workspaceId) {
      qc.invalidateQueries({ queryKey: ["training-feedback", "list", workspaceId] });
    }
    qc.invalidateQueries({ queryKey: FEEDBACK_DETAIL_KEY(feedbackId) });
    qc.invalidateQueries({ queryKey: ["training-feedback", "session", sessionId] });
  };
}

export function useFeedbackList(
  filters: TrainingFeedbackFilters | null | undefined,
) {
  return useQuery<{ data: TrainingFeedbackListOut }>({
    queryKey: FEEDBACK_LIST_KEY(filters?.workspace_id ?? "", filters ?? {}),
    queryFn: () => {
      const params = new URLSearchParams();
      if (filters?.workspace_id) params.set("workspace_id", filters.workspace_id);
      if (filters?.session_id) params.set("session_id", filters.session_id);
      if (filters?.customer_id) params.set("customer_id", filters.customer_id);
      if (filters?.trainer_id) params.set("trainer_id", filters.trainer_id);
      if (filters?.min_rating != null) params.set("min_rating", String(filters.min_rating));
      if (filters?.search) params.set("search", filters.search);
      if (filters?.cursor) params.set("cursor", filters.cursor);
      if (filters?.limit != null) params.set("limit", String(filters.limit));
      return api.get<{ data: TrainingFeedbackListOut }>(
        `/api/v1/training-feedback?${params.toString()}`,
      );
    },
    enabled: !!filters?.workspace_id,
    staleTime: STALE_MS,
  });
}

export function useFeedbackDetail(feedbackId: string | null | undefined) {
  return useQuery<{ data: TrainingFeedback }>({
    queryKey: FEEDBACK_DETAIL_KEY(feedbackId ?? ""),
    queryFn: () =>
      api.get<{ data: TrainingFeedback }>(
        `/api/v1/training-feedback/${feedbackId}`,
      ),
    enabled: !!feedbackId,
    staleTime: STALE_MS,
  });
}

export function useSessionFeedback(sessionId: string | null | undefined) {
  return useQuery<{ data: TrainingFeedback[] }>({
    queryKey: ["training-feedback", "session", sessionId ?? ""],
    queryFn: () =>
      api.get<{ data: TrainingFeedback[] }>(
        `/api/v1/training-sessions/${sessionId}/feedback`,
      ),
    enabled: !!sessionId,
    staleTime: STALE_MS,
  });
}

export function useCustomerFeedback(
  customerId: string | null | undefined,
  workspaceId: string | null | undefined,
) {
  return useQuery<{ data: TrainingFeedback[] }>({
    queryKey: ["training-feedback", "customer", customerId ?? "", workspaceId ?? ""],
    queryFn: () =>
      api.get<{ data: TrainingFeedback[] }>(
        `/api/v1/customers/${customerId}/feedback?workspace_id=${workspaceId}`,
      ),
    enabled: !!customerId && !!workspaceId,
    staleTime: STALE_MS,
  });
}

export function useCreateFeedback(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateFeedback(workspaceId);
  return useMutation<
    { data: TrainingFeedback },
    Error,
    TrainingFeedbackCreate
  >({
    mutationFn: (body) =>
      api.post<{ data: TrainingFeedback }>("/api/v1/training-feedback/", body),
    onSuccess: (data) => invalidate(data.data.id, data.data.session_id),
  });
}

export function useUpdateFeedback(workspaceId: string | null | undefined) {
  const invalidate = useInvalidateFeedback(workspaceId);
  return useMutation<
    { data: TrainingFeedback },
    Error,
    { id: string; sessionId: string; body: TrainingFeedbackUpdate }
  >({
    mutationFn: ({ id, body }) =>
      api.patch<{ data: TrainingFeedback }>(
        `/api/v1/training-feedback/${id}`,
        body,
      ),
    onSuccess: (_, { id, sessionId }) => invalidate(id, sessionId),
  });
}
