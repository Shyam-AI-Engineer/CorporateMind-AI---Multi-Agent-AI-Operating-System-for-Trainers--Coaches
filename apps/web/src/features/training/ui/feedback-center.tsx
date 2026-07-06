"use client";

import { useState } from "react";
import {
  useFeedbackList,
  useCreateFeedback,
  useUpdateFeedback,
} from "@/features/training/api/use-training";
import type {
  TrainingFeedback,
  TrainingFeedbackCreate,
  TrainingFeedbackUpdate,
  TrainingFeedbackFilters,
} from "@/features/training/types";

// ── Rating display ─────────────────────────────────────────────────────────────

function RatingStars({ value }: { value: number | null }) {
  if (value === null) return <span data-testid="rating-null" className="text-muted-foreground text-xs">—</span>;
  return (
    <span data-testid="rating-stars" className="text-amber-500 text-sm">
      {"★".repeat(value)}{"☆".repeat(5 - value)}
      <span className="ml-1 text-xs text-muted-foreground">({value})</span>
    </span>
  );
}

// ── Recommend badge ────────────────────────────────────────────────────────────

function RecommendBadge({ value }: { value: boolean | null }) {
  if (value === null) return <span data-testid="recommend-null" className="text-muted-foreground text-xs">—</span>;
  return (
    <span
      data-testid={value ? "recommend-yes" : "recommend-no"}
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        value ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
      }`}
    >
      {value ? "Yes" : "No"}
    </span>
  );
}

// ── Create dialog ─────────────────────────────────────────────────────────────

interface CreateDialogProps {
  sessionId: string;
  workspaceId: string;
  onClose: () => void;
  onCreate: (req: TrainingFeedbackCreate) => void;
}

function CreateFeedbackDialog({ sessionId, workspaceId, onClose, onCreate }: CreateDialogProps) {
  const [attendanceId, setAttendanceId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [overall, setOverall] = useState<string>("");
  const [trainerR, setTrainerR] = useState<string>("");
  const [contentR, setContentR] = useState<string>("");
  const [materialsR, setMaterialsR] = useState<string>("");
  const [venueR, setVenueR] = useState<string>("");
  const [recommend, setRecommend] = useState<string>("");
  const [comments, setComments] = useState("");
  const [error, setError] = useState("");

  const toRating = (v: string) => (v ? parseInt(v, 10) : undefined);
  const toRecommend = (v: string) =>
    v === "yes" ? true : v === "no" ? false : undefined;

  const handleSubmit = () => {
    if (!attendanceId.trim()) { setError("attendance_id required"); return; }
    if (!customerId.trim()) { setError("customer_id required"); return; }
    onCreate({
      workspace_id: workspaceId,
      attendance_id: attendanceId.trim(),
      session_id: sessionId,
      customer_id: customerId.trim(),
      overall_rating: toRating(overall),
      trainer_rating: toRating(trainerR),
      content_rating: toRating(contentR),
      materials_rating: toRating(materialsR),
      venue_rating: toRating(venueR),
      would_recommend: toRecommend(recommend),
      comments: comments.trim() || undefined,
    });
  };

  return (
    <div data-testid="create-feedback-dialog" className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold">Submit Feedback</h2>
        {error && <p data-testid="create-error" className="mb-3 text-sm text-red-600">{error}</p>}
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground">Attendance ID</label>
            <input
              data-testid="input-attendance-id"
              value={attendanceId}
              onChange={(e) => setAttendanceId(e.target.value)}
              className="mt-1 w-full rounded border px-3 py-2 text-sm"
              placeholder="UUID"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Customer ID</label>
            <input
              data-testid="input-customer-id"
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
              className="mt-1 w-full rounded border px-3 py-2 text-sm"
              placeholder="UUID"
            />
          </div>
          {(["overall", "trainer", "content", "materials", "venue"] as const).map((key) => {
            const map = {
              overall: [overall, setOverall],
              trainer: [trainerR, setTrainerR],
              content: [contentR, setContentR],
              materials: [materialsR, setMaterialsR],
              venue: [venueR, setVenueR],
            } as Record<string, [string, (v: string) => void]>;
            const [val, setter] = map[key];
            return (
              <div key={key}>
                <label className="text-xs font-medium text-muted-foreground capitalize">{key} Rating</label>
                <select
                  data-testid={`select-${key}-rating`}
                  value={val}
                  onChange={(e) => setter(e.target.value)}
                  className="mt-1 w-full rounded border px-3 py-2 text-sm"
                >
                  <option value="">— not rated —</option>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={String(n)}>{n} star{n > 1 ? "s" : ""}</option>
                  ))}
                </select>
              </div>
            );
          })}
          <div>
            <label className="text-xs font-medium text-muted-foreground">Would Recommend</label>
            <select
              data-testid="select-would-recommend"
              value={recommend}
              onChange={(e) => setRecommend(e.target.value)}
              className="mt-1 w-full rounded border px-3 py-2 text-sm"
            >
              <option value="">— not answered —</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Comments</label>
            <textarea
              data-testid="input-comments"
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              rows={3}
              className="mt-1 w-full rounded border px-3 py-2 text-sm"
            />
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} data-testid="btn-cancel-create" className="rounded border px-4 py-2 text-sm">
            Cancel
          </button>
          <button onClick={handleSubmit} data-testid="btn-submit-feedback" className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
            Submit
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Feedback drawer ────────────────────────────────────────────────────────────

interface FeedbackDrawerProps {
  feedback: TrainingFeedback;
  workspaceId: string;
  onClose: () => void;
  onUpdate: (req: { id: string; sessionId: string; body: TrainingFeedbackUpdate }) => void;
}

function FeedbackDrawer({ feedback, workspaceId: _wid, onClose, onUpdate }: FeedbackDrawerProps) {
  const [editMode, setEditMode] = useState(false);
  const [overall, setOverall] = useState<string>(feedback.overall_rating != null ? String(feedback.overall_rating) : "");
  const [trainerR, setTrainerR] = useState<string>(feedback.trainer_rating != null ? String(feedback.trainer_rating) : "");
  const [contentR, setContentR] = useState<string>(feedback.content_rating != null ? String(feedback.content_rating) : "");
  const [materialsR, setMaterialsR] = useState<string>(feedback.materials_rating != null ? String(feedback.materials_rating) : "");
  const [venueR, setVenueR] = useState<string>(feedback.venue_rating != null ? String(feedback.venue_rating) : "");
  const [recommend, setRecommend] = useState<string>(
    feedback.would_recommend === true ? "yes" : feedback.would_recommend === false ? "no" : ""
  );
  const [comments, setComments] = useState(feedback.comments ?? "");

  const toRating = (v: string) => (v ? parseInt(v, 10) : undefined);
  const toRecommend = (v: string) =>
    v === "yes" ? true : v === "no" ? false : undefined;

  const handleSave = () => {
    onUpdate({
      id: feedback.id,
      sessionId: feedback.session_id,
      body: {
        overall_rating: toRating(overall),
        trainer_rating: toRating(trainerR),
        content_rating: toRating(contentR),
        materials_rating: toRating(materialsR),
        venue_rating: toRating(venueR),
        would_recommend: toRecommend(recommend),
        comments: comments.trim() || undefined,
      },
    });
    setEditMode(false);
  };

  return (
    <div
      data-testid="feedback-drawer"
      className="fixed right-0 top-0 h-full w-[440px] overflow-y-auto border-l bg-white p-6 shadow-xl"
    >
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Feedback Detail</h2>
        <button onClick={onClose} data-testid="drawer-close" className="text-muted-foreground hover:text-foreground">✕</button>
      </div>

      <div className="space-y-4 text-sm">
        {!editMode ? (
          <>
            <div>
              <span className="text-muted-foreground">Overall: </span>
              <span data-testid="drawer-overall-rating"><RatingStars value={feedback.overall_rating} /></span>
            </div>
            <div>
              <span className="text-muted-foreground">Trainer: </span>
              <span data-testid="drawer-trainer-rating"><RatingStars value={feedback.trainer_rating} /></span>
            </div>
            <div>
              <span className="text-muted-foreground">Content: </span>
              <span data-testid="drawer-content-rating"><RatingStars value={feedback.content_rating} /></span>
            </div>
            <div>
              <span className="text-muted-foreground">Materials: </span>
              <span data-testid="drawer-materials-rating"><RatingStars value={feedback.materials_rating} /></span>
            </div>
            {feedback.venue_rating !== null && (
              <div>
                <span className="text-muted-foreground">Venue: </span>
                <span data-testid="drawer-venue-rating"><RatingStars value={feedback.venue_rating} /></span>
              </div>
            )}
            <div>
              <span className="text-muted-foreground">Recommend: </span>
              <span data-testid="drawer-would-recommend"><RecommendBadge value={feedback.would_recommend} /></span>
            </div>
            {feedback.comments && (
              <div>
                <span className="text-muted-foreground">Comments: </span>
                <p data-testid="drawer-comments" className="mt-1 text-sm">{feedback.comments}</p>
              </div>
            )}
            <div>
              <span className="text-muted-foreground">Submitted: </span>
              <span data-testid="drawer-submitted-at">
                {new Date(feedback.submitted_at).toLocaleDateString()}
              </span>
            </div>
            <button
              data-testid="btn-edit-feedback"
              onClick={() => setEditMode(true)}
              className="mt-4 rounded border px-4 py-2 text-sm hover:bg-muted"
            >
              Edit Feedback
            </button>
          </>
        ) : (
          <>
            {(["overall", "trainer", "content", "materials", "venue"] as const).map((key) => {
              const map = {
                overall: [overall, setOverall],
                trainer: [trainerR, setTrainerR],
                content: [contentR, setContentR],
                materials: [materialsR, setMaterialsR],
                venue: [venueR, setVenueR],
              } as Record<string, [string, (v: string) => void]>;
              const [val, setter] = map[key];
              return (
                <div key={key}>
                  <label className="text-xs font-medium text-muted-foreground capitalize">{key} Rating</label>
                  <select
                    data-testid={`edit-${key}-rating`}
                    value={val}
                    onChange={(e) => setter(e.target.value)}
                    className="mt-1 w-full rounded border px-3 py-2 text-sm"
                  >
                    <option value="">— not rated —</option>
                    {[1, 2, 3, 4, 5].map((n) => (
                      <option key={n} value={String(n)}>{n} star{n > 1 ? "s" : ""}</option>
                    ))}
                  </select>
                </div>
              );
            })}
            <div>
              <label className="text-xs font-medium text-muted-foreground">Would Recommend</label>
              <select
                data-testid="edit-would-recommend"
                value={recommend}
                onChange={(e) => setRecommend(e.target.value)}
                className="mt-1 w-full rounded border px-3 py-2 text-sm"
              >
                <option value="">— not answered —</option>
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">Comments</label>
              <textarea
                data-testid="edit-comments"
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                rows={3}
                className="mt-1 w-full rounded border px-3 py-2 text-sm"
              />
            </div>
            <div className="flex gap-2">
              <button
                data-testid="btn-save-feedback"
                onClick={handleSave}
                className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
              >
                Save
              </button>
              <button
                data-testid="btn-cancel-edit"
                onClick={() => setEditMode(false)}
                className="rounded border px-4 py-2 text-sm"
              >
                Cancel
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Feedback table ─────────────────────────────────────────────────────────────

interface FeedbackTableProps {
  items: TrainingFeedback[];
  onSelect: (f: TrainingFeedback) => void;
}

function FeedbackTable({ items, onSelect }: FeedbackTableProps) {
  return (
    <div data-testid="feedback-table" className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr>
            <th className="px-3 py-2 text-left font-medium">Overall</th>
            <th className="px-3 py-2 text-left font-medium">Trainer</th>
            <th className="px-3 py-2 text-left font-medium">Content</th>
            <th className="px-3 py-2 text-left font-medium">Recommend</th>
            <th className="px-3 py-2 text-left font-medium">Comments</th>
            <th className="px-3 py-2 text-left font-medium">Submitted</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-3 py-8 text-center text-muted-foreground" data-testid="empty-row">
                No feedback records
              </td>
            </tr>
          ) : (
            items.map((f) => (
              <tr
                key={f.id}
                data-testid="feedback-row"
                onClick={() => onSelect(f)}
                className="cursor-pointer border-t hover:bg-muted/30"
              >
                <td className="px-3 py-2"><RatingStars value={f.overall_rating} /></td>
                <td className="px-3 py-2"><RatingStars value={f.trainer_rating} /></td>
                <td className="px-3 py-2"><RatingStars value={f.content_rating} /></td>
                <td className="px-3 py-2"><RecommendBadge value={f.would_recommend} /></td>
                <td className="max-w-[200px] truncate px-3 py-2 text-muted-foreground">
                  {f.comments ?? "—"}
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {new Date(f.submitted_at).toLocaleDateString()}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

// ── Main FeedbackCenter ────────────────────────────────────────────────────────

interface FeedbackCenterProps {
  sessionId: string;
  workspaceId: string;
  customerId?: string;
}

export function FeedbackCenter({ sessionId, workspaceId, customerId }: FeedbackCenterProps) {
  const [search, setSearch] = useState("");
  const [minRating, setMinRating] = useState<string>("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [selected, setSelected] = useState<TrainingFeedback | null>(null);

  const filters: TrainingFeedbackFilters = {
    workspace_id: workspaceId,
    session_id: sessionId,
    customer_id: customerId,
    search: search || undefined,
    min_rating: minRating ? parseInt(minRating, 10) : undefined,
    cursor: cursor ?? undefined,
  };

  const { data, isLoading, isError } = useFeedbackList(filters);
  const items: TrainingFeedback[] = data?.data?.items ?? [];
  const total: number = data?.data?.total ?? 0;
  const hasMore: boolean = data?.data?.has_more ?? false;
  const nextCursor: string | null = data?.data?.next_cursor ?? null;

  const createMutation = useCreateFeedback(workspaceId);
  const updateMutation = useUpdateFeedback(workspaceId);

  // KPI computations from current page items
  const ratedItems = items.filter((f) => f.overall_rating !== null);
  const avgRating =
    ratedItems.length > 0
      ? (ratedItems.reduce((sum, f) => sum + (f.overall_rating ?? 0), 0) / ratedItems.length).toFixed(1)
      : null;
  const recommendCount = items.filter((f) => f.would_recommend === true).length;
  const recommendRate =
    items.length > 0 ? Math.round((recommendCount / items.length) * 100) : null;
  const withComments = items.filter((f) => f.comments && f.comments.trim()).length;

  const handleCreate = (req: TrainingFeedbackCreate) => {
    createMutation.mutate(req, { onSuccess: () => setShowCreate(false) });
  };

  const handleUpdate = (args: { id: string; sessionId: string; body: TrainingFeedbackUpdate }) => {
    updateMutation.mutate(args, { onSuccess: () => setSelected(null) });
  };

  return (
    <div data-testid="feedback-center" className="space-y-4">
      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div data-testid="kpi-total" className="rounded-lg border bg-white p-4">
          <p className="text-xs text-muted-foreground">Total Feedback</p>
          <p className="mt-1 text-2xl font-semibold">{total}</p>
        </div>
        <div data-testid="kpi-avg-rating" className="rounded-lg border bg-white p-4">
          <p className="text-xs text-muted-foreground">Avg Rating</p>
          <p className="mt-1 text-2xl font-semibold">{avgRating ?? "—"}</p>
        </div>
        <div data-testid="kpi-recommend-rate" className="rounded-lg border bg-white p-4">
          <p className="text-xs text-muted-foreground">Recommend Rate</p>
          <p className="mt-1 text-2xl font-semibold">
            {recommendRate !== null ? `${recommendRate}%` : "—"}
          </p>
        </div>
        <div data-testid="kpi-with-comments" className="rounded-lg border bg-white p-4">
          <p className="text-xs text-muted-foreground">With Comments</p>
          <p className="mt-1 text-2xl font-semibold">{withComments}</p>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          data-testid="search-input"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setCursor(null); }}
          placeholder="Search comments…"
          className="rounded border px-3 py-2 text-sm"
        />
        <select
          data-testid="filter-min-rating"
          value={minRating}
          onChange={(e) => { setMinRating(e.target.value); setCursor(null); }}
          className="rounded border px-3 py-2 text-sm"
        >
          <option value="">All ratings</option>
          {[1, 2, 3, 4, 5].map((n) => (
            <option key={n} value={String(n)}>{n}+ stars</option>
          ))}
        </select>
        <button
          data-testid="btn-add-feedback"
          onClick={() => setShowCreate(true)}
          className="ml-auto rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
        >
          + Add Feedback
        </button>
      </div>

      {/* State guards */}
      {isLoading && <p data-testid="loading-state" className="text-sm text-muted-foreground">Loading…</p>}
      {isError && <p data-testid="error-state" className="text-sm text-red-600">Failed to load feedback.</p>}

      {/* Table */}
      {!isLoading && !isError && (
        <FeedbackTable items={items} onSelect={setSelected} />
      )}

      {/* Pagination */}
      {hasMore && (
        <button
          data-testid="btn-load-more"
          onClick={() => setCursor(nextCursor)}
          className="rounded border px-4 py-2 text-sm hover:bg-muted"
        >
          Load more
        </button>
      )}

      {/* Dialogs / Drawer */}
      {showCreate && (
        <CreateFeedbackDialog
          sessionId={sessionId}
          workspaceId={workspaceId}
          onClose={() => setShowCreate(false)}
          onCreate={handleCreate}
        />
      )}
      {selected && (
        <FeedbackDrawer
          feedback={selected}
          workspaceId={workspaceId}
          onClose={() => setSelected(null)}
          onUpdate={handleUpdate}
        />
      )}
    </div>
  );
}
