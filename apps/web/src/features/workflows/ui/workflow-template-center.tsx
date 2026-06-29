"use client";

import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useWorkspace } from "@/hooks/use-workspace";
import {
  useWorkflowTemplates,
  useWorkflowTemplate,
  useCreateTemplate,
  useUpdateTemplate,
  useDeleteTemplate,
  useDuplicateTemplate,
  useAddStep,
  useUpdateStep,
  useDeleteStep,
  useReorderSteps,
} from "@/features/workflows/api/use-workflows";
import type {
  OwnerRole,
  WorkflowCategory,
  WorkflowStepOut,
  WorkflowTemplateOut,
} from "@/features/workflows/types";

// ── Constants ─────────────────────────────────────────────────────────────────

const CATEGORIES: WorkflowCategory[] = [
  "new_corporate_lead",
  "proposal_review",
  "enterprise_sales",
  "training_delivery",
  "customer_followup",
  "renewal_process",
  "onboarding",
  "other",
];

const OWNER_ROLES: OwnerRole[] = ["owner", "admin", "member", "viewer"];

function categoryLabel(c: WorkflowCategory): string {
  return c.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
}

// ── Owner-role badge ──────────────────────────────────────────────────────────

function OwnerRoleBadge({ role }: { role: OwnerRole }) {
  const colors: Record<OwnerRole, string> = {
    owner: "bg-purple-100 text-purple-700 border-purple-200",
    admin: "bg-blue-100 text-blue-700 border-blue-200",
    member: "bg-slate-100 text-slate-600 border-slate-200",
    viewer: "bg-gray-100 text-gray-500 border-gray-200",
  };
  return (
    <span
      data-testid={`owner-role-badge-${role}`}
      className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${colors[role]}`}
    >
      {role}
    </span>
  );
}

// ── Category badge ────────────────────────────────────────────────────────────

function CategoryBadge({ category }: { category: WorkflowCategory }) {
  return (
    <span
      data-testid={`category-badge-${category}`}
      className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700 border border-indigo-200"
    >
      {categoryLabel(category)}
    </span>
  );
}

// ── Duplicate dialog ──────────────────────────────────────────────────────────

interface DuplicateDialogProps {
  template: WorkflowTemplateOut;
  workspaceId: string;
  onClose: () => void;
}

function DuplicateDialog({ template, workspaceId, onClose }: DuplicateDialogProps) {
  const duplicate = useDuplicateTemplate(workspaceId);
  return (
    <div
      data-testid="duplicate-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div className="w-full max-w-sm rounded-lg bg-background p-6 shadow-xl space-y-4">
        <h3 className="font-semibold">Duplicate Template</h3>
        <p className="text-sm text-muted-foreground">
          Create a copy of &quot;{template.name}&quot;?
        </p>
        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            data-testid="duplicate-dialog-cancel"
            onClick={onClose}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            data-testid="duplicate-dialog-confirm"
            disabled={duplicate.isPending}
            onClick={() =>
              duplicate.mutate(template.id, { onSuccess: onClose })
            }
          >
            Duplicate
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Add-step form ─────────────────────────────────────────────────────────────

interface AddStepFormProps {
  templateId: string;
  workspaceId: string;
  onClose: () => void;
}

function AddStepForm({ templateId, workspaceId, onClose }: AddStepFormProps) {
  const [title, setTitle] = useState("");
  const [ownerRole, setOwnerRole] = useState<OwnerRole>("member");
  const [hours, setHours] = useState("0");
  const [required, setRequired] = useState(true);
  const addStep = useAddStep(workspaceId);

  const handleSubmit = () => {
    if (!title.trim()) return;
    addStep.mutate(
      {
        templateId,
        data: { title, owner_role: ownerRole, estimated_hours: hours, required },
      },
      { onSuccess: onClose },
    );
  };

  return (
    <div data-testid="add-step-form" className="rounded-lg border p-4 space-y-3 bg-muted/30">
      <h4 className="text-sm font-semibold">Add Step</h4>
      <input
        data-testid="step-title-input"
        type="text"
        placeholder="Step title..."
        className="w-full rounded border bg-background px-3 py-1.5 text-sm"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <div className="flex flex-wrap gap-2">
        <select
          data-testid="step-owner-role-select"
          className="rounded border bg-background px-2 py-1 text-sm"
          value={ownerRole}
          onChange={(e) => setOwnerRole(e.target.value as OwnerRole)}
        >
          {OWNER_ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <input
          data-testid="step-hours-input"
          type="number"
          min="0"
          step="0.5"
          placeholder="Hours"
          className="w-24 rounded border bg-background px-2 py-1 text-sm"
          value={hours}
          onChange={(e) => setHours(e.target.value)}
        />
        <label className="flex items-center gap-1 text-sm">
          <input
            data-testid="step-required-checkbox"
            type="checkbox"
            checked={required}
            onChange={(e) => setRequired(e.target.checked)}
          />
          Required
        </label>
      </div>
      <div className="flex gap-2">
        <Button
          size="sm"
          data-testid="add-step-submit"
          disabled={addStep.isPending || !title.trim()}
          onClick={handleSubmit}
        >
          Add Step
        </Button>
        <Button variant="outline" size="sm" data-testid="add-step-cancel" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

// ── Step list ─────────────────────────────────────────────────────────────────

interface StepListProps {
  template: WorkflowTemplateOut;
  workspaceId: string;
}

function StepList({ template, workspaceId }: StepListProps) {
  const [localSteps, setLocalSteps] = useState<WorkflowStepOut[]>(template.steps);
  const [showAddForm, setShowAddForm] = useState(false);
  const deleteStep = useDeleteStep(workspaceId);
  const reorder = useReorderSteps(workspaceId);

  const moveStep = (idx: number, dir: -1 | 1) => {
    const next = [...localSteps];
    const target = idx + dir;
    if (target < 0 || target >= next.length) return;
    [next[idx], next[target]] = [next[target], next[idx]];
    setLocalSteps(next);
  };

  const commitOrder = () => {
    reorder.mutate({
      templateId: template.id,
      data: { step_ids: localSteps.map((s) => s.id) },
    });
  };

  // Sync if template steps change (e.g., after add/delete)
  const stepsChanged = JSON.stringify(localSteps.map((s) => s.id)) !==
    JSON.stringify(template.steps.map((s) => s.id));

  return (
    <div data-testid="step-list" className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">
          Steps{" "}
          <span data-testid="step-count" className="text-muted-foreground">
            ({template.steps.length})
          </span>
        </h4>
        <div className="flex gap-2">
          {stepsChanged && (
            <Button
              variant="outline"
              size="sm"
              data-testid="commit-order-btn"
              disabled={reorder.isPending}
              onClick={commitOrder}
            >
              Save order
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            data-testid="add-step-btn"
            onClick={() => setShowAddForm(true)}
          >
            + Add step
          </Button>
        </div>
      </div>

      {localSteps.length === 0 && !showAddForm && (
        <p data-testid="no-steps-message" className="text-sm text-muted-foreground">
          No steps yet. Add your first step.
        </p>
      )}

      {localSteps.map((step, idx) => (
        <div
          key={step.id}
          data-testid={`step-item-${step.id}`}
          className="flex items-center gap-2 rounded-lg border bg-background p-3"
        >
          <span
            data-testid={`step-order-${step.id}`}
            className="w-6 shrink-0 text-center text-xs font-bold text-muted-foreground"
          >
            {idx + 1}
          </span>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <p data-testid={`step-title-${step.id}`} className="text-sm font-medium">
                {step.title}
              </p>
              <OwnerRoleBadge role={step.owner_role} />
              {step.required && (
                <span
                  data-testid={`step-required-badge-${step.id}`}
                  className="rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-semibold text-red-600 border border-red-200"
                >
                  Required
                </span>
              )}
            </div>
            {step.description && (
              <p className="mt-0.5 text-xs text-muted-foreground">{step.description}</p>
            )}
            <p
              data-testid={`step-hours-${step.id}`}
              className="mt-0.5 text-xs text-muted-foreground"
            >
              {step.estimated_hours}h
            </p>
          </div>

          <div className="flex shrink-0 gap-1">
            <Button
              variant="ghost"
              size="sm"
              data-testid={`move-up-btn-${step.id}`}
              disabled={idx === 0}
              onClick={() => moveStep(idx, -1)}
              className="text-xs px-2"
            >
              ↑
            </Button>
            <Button
              variant="ghost"
              size="sm"
              data-testid={`move-down-btn-${step.id}`}
              disabled={idx === localSteps.length - 1}
              onClick={() => moveStep(idx, 1)}
              className="text-xs px-2"
            >
              ↓
            </Button>
            <Button
              variant="ghost"
              size="sm"
              data-testid={`delete-step-btn-${step.id}`}
              disabled={deleteStep.isPending}
              onClick={() =>
                deleteStep.mutate({ stepId: step.id, templateId: template.id })
              }
              className="text-xs text-destructive hover:text-destructive"
            >
              Delete
            </Button>
          </div>
        </div>
      ))}

      {showAddForm && (
        <AddStepForm
          templateId={template.id}
          workspaceId={workspaceId}
          onClose={() => setShowAddForm(false)}
        />
      )}
    </div>
  );
}

// ── Template detail panel ─────────────────────────────────────────────────────

interface TemplateDetailProps {
  templateId: string;
  workspaceId: string;
  onBack: () => void;
}

function TemplateDetail({ templateId, workspaceId, onBack }: TemplateDetailProps) {
  const { data, isLoading, isError } = useWorkflowTemplate(templateId);
  const updateTemplate = useUpdateTemplate(workspaceId);
  const [duplicateTarget, setDuplicateTarget] = useState<WorkflowTemplateOut | null>(null);

  const totalHours = data?.steps.reduce(
    (sum, s) => sum + parseFloat(s.estimated_hours || "0"),
    0,
  ) ?? 0;

  if (isLoading) {
    return (
      <div data-testid="template-detail-skeleton" className="space-y-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div
        data-testid="template-detail-error"
        className="rounded-lg border border-destructive/30 p-6 text-center text-sm text-destructive"
      >
        Failed to load template.
      </div>
    );
  }

  return (
    <div data-testid="template-detail" className="space-y-4">
      {duplicateTarget && (
        <DuplicateDialog
          template={duplicateTarget}
          workspaceId={workspaceId}
          onClose={() => setDuplicateTarget(null)}
        />
      )}

      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" data-testid="back-to-list-btn" onClick={onBack}>
          ← Back
        </Button>
      </div>

      {/* Metadata */}
      <div className="rounded-lg border p-4 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-1">
            <h3 data-testid="template-detail-name" className="font-semibold">
              {data.name}
            </h3>
            {data.description && (
              <p
                data-testid="template-detail-description"
                className="text-sm text-muted-foreground"
              >
                {data.description}
              </p>
            )}
          </div>
          <div className="flex shrink-0 gap-2">
            <Button
              variant="outline"
              size="sm"
              data-testid="duplicate-template-btn"
              onClick={() => setDuplicateTarget(data)}
            >
              Duplicate
            </Button>
            <Button
              variant="outline"
              size="sm"
              data-testid="toggle-active-btn"
              disabled={updateTemplate.isPending}
              onClick={() =>
                updateTemplate.mutate({ id: data.id, data: { is_active: !data.is_active } })
              }
            >
              {data.is_active ? "Deactivate" : "Activate"}
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 pt-1">
          <CategoryBadge category={data.category} />
          <span
            data-testid="template-step-count"
            className="text-xs text-muted-foreground"
          >
            {data.steps.length} step{data.steps.length !== 1 ? "s" : ""}
          </span>
          <span
            data-testid="template-total-hours"
            className="text-xs text-muted-foreground"
          >
            ~{totalHours.toFixed(1)}h total
          </span>
          {!data.is_active && (
            <span
              data-testid="template-inactive-badge"
              className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500 border"
            >
              Inactive
            </span>
          )}
        </div>
      </div>

      <StepList template={data} workspaceId={workspaceId} />
    </div>
  );
}

// ── Template list item ────────────────────────────────────────────────────────

interface TemplateCardProps {
  template: WorkflowTemplateOut;
  workspaceId: string;
  onSelect: (id: string) => void;
}

function TemplateCard({ template, workspaceId, onSelect }: TemplateCardProps) {
  const deleteTemplate = useDeleteTemplate(workspaceId);
  const totalHours = template.steps.reduce(
    (sum, s) => sum + parseFloat(s.estimated_hours || "0"),
    0,
  );

  return (
    <div
      data-testid={`template-card-${template.id}`}
      className={`rounded-lg border p-4 space-y-2 cursor-pointer hover:border-primary/40 transition-colors ${
        !template.is_active ? "opacity-60" : ""
      }`}
      onClick={() => onSelect(template.id)}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p data-testid={`template-name-${template.id}`} className="font-medium text-sm">
            {template.name}
          </p>
          {template.description && (
            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
              {template.description}
            </p>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          data-testid={`delete-template-btn-${template.id}`}
          disabled={deleteTemplate.isPending}
          onClick={(e) => {
            e.stopPropagation();
            deleteTemplate.mutate(template.id);
          }}
          className="shrink-0 text-xs text-destructive hover:text-destructive"
        >
          Delete
        </Button>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <CategoryBadge category={template.category} />
        <span
          data-testid={`template-steps-count-${template.id}`}
          className="text-xs text-muted-foreground"
        >
          {template.steps.length} step{template.steps.length !== 1 ? "s" : ""}
        </span>
        <span
          data-testid={`template-hours-${template.id}`}
          className="text-xs text-muted-foreground"
        >
          ~{totalHours.toFixed(1)}h
        </span>
        {!template.is_active && (
          <span
            data-testid={`template-inactive-${template.id}`}
            className="text-xs text-muted-foreground"
          >
            (inactive)
          </span>
        )}
      </div>
    </div>
  );
}

// ── Create template form ──────────────────────────────────────────────────────

interface CreateTemplateFormProps {
  workspaceId: string;
  onClose: () => void;
}

function CreateTemplateForm({ workspaceId, onClose }: CreateTemplateFormProps) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState<WorkflowCategory>("other");
  const [description, setDescription] = useState("");
  const createTemplate = useCreateTemplate(workspaceId);

  const handleSubmit = () => {
    if (!name.trim()) return;
    createTemplate.mutate(
      {
        workspace_id: workspaceId,
        name,
        category,
        description: description.trim() || null,
      },
      { onSuccess: onClose },
    );
  };

  return (
    <div data-testid="create-template-form" className="rounded-lg border p-4 space-y-3 bg-muted/30">
      <h4 className="text-sm font-semibold">New Template</h4>
      <input
        data-testid="template-name-input"
        type="text"
        placeholder="Template name..."
        className="w-full rounded border bg-background px-3 py-1.5 text-sm"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <select
        data-testid="template-category-select"
        className="w-full rounded border bg-background px-2 py-1.5 text-sm"
        value={category}
        onChange={(e) => setCategory(e.target.value as WorkflowCategory)}
      >
        {CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {categoryLabel(c)}
          </option>
        ))}
      </select>
      <textarea
        data-testid="template-description-input"
        placeholder="Description (optional)..."
        className="w-full rounded border bg-background px-3 py-1.5 text-sm"
        rows={2}
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <div className="flex gap-2">
        <Button
          size="sm"
          data-testid="create-template-submit"
          disabled={createTemplate.isPending || !name.trim()}
          onClick={handleSubmit}
        >
          Create
        </Button>
        <Button
          variant="outline"
          size="sm"
          data-testid="create-template-cancel"
          onClick={onClose}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}

// ── Category filter ───────────────────────────────────────────────────────────

interface CategoryFilterProps {
  value: WorkflowCategory | "";
  onChange: (v: WorkflowCategory | "") => void;
}

function CategoryFilter({ value, onChange }: CategoryFilterProps) {
  return (
    <select
      data-testid="category-filter"
      className="rounded border bg-background px-2 py-1 text-sm"
      value={value}
      onChange={(e) => onChange(e.target.value as WorkflowCategory | "")}
    >
      <option value="">All categories</option>
      {CATEGORIES.map((c) => (
        <option key={c} value={c}>
          {categoryLabel(c)}
        </option>
      ))}
    </select>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function WorkflowTemplateCenter() {
  const { workspaceId } = useWorkspace();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<WorkflowCategory | "">("");
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [prevCursors, setPrevCursors] = useState<string[]>([]);

  const { data, isLoading, isError } = useWorkflowTemplates(workspaceId, {
    cursor,
    category: categoryFilter || undefined,
  });

  if (!workspaceId) {
    return (
      <div data-testid="workflows-no-workspace" className="p-6 text-muted-foreground">
        Select a workspace to view workflow templates.
      </div>
    );
  }

  if (selectedId) {
    return (
      <TemplateDetail
        templateId={selectedId}
        workspaceId={workspaceId}
        onBack={() => setSelectedId(null)}
      />
    );
  }

  const handleNext = () => {
    if (data?.next_cursor) {
      setPrevCursors((p) => [...p, cursor ?? ""]);
      setCursor(data.next_cursor);
    }
  };

  const handlePrev = () => {
    const prev = [...prevCursors];
    const last = prev.pop() ?? undefined;
    setPrevCursors(prev);
    setCursor(last === "" ? undefined : last);
  };

  const handleCategoryChange = (v: WorkflowCategory | "") => {
    setCategoryFilter(v);
    setCursor(undefined);
    setPrevCursors([]);
  };

  return (
    <div data-testid="workflow-template-center" className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">Workflow Templates</h2>
        <Button
          size="sm"
          data-testid="new-template-btn"
          onClick={() => setShowCreate(true)}
        >
          + New Template
        </Button>
      </div>

      {/* Filter */}
      <div data-testid="template-filters" className="flex items-center gap-2">
        <CategoryFilter value={categoryFilter} onChange={handleCategoryChange} />
        {categoryFilter && (
          <Button
            variant="ghost"
            size="sm"
            data-testid="clear-category-filter"
            onClick={() => handleCategoryChange("")}
            className="text-xs"
          >
            Clear
          </Button>
        )}
      </div>

      {/* Create form */}
      {showCreate && (
        <CreateTemplateForm
          workspaceId={workspaceId}
          onClose={() => setShowCreate(false)}
        />
      )}

      {/* Content */}
      {isLoading && (
        <div data-testid="template-list-skeleton" className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      )}

      {isError && !isLoading && (
        <div
          data-testid="template-list-error"
          className="rounded-lg border border-destructive/30 p-6 text-center text-sm text-destructive"
        >
          Failed to load templates. Please try again.
        </div>
      )}

      {!isLoading && !isError && data?.items.length === 0 && (
        <div
          data-testid="template-list-empty"
          className="rounded-lg border p-8 text-center text-sm text-muted-foreground"
        >
          No templates yet. Create your first workflow template.
        </div>
      )}

      {!isLoading && !isError && data && data.items.length > 0 && (
        <div data-testid="template-list" className="space-y-3">
          {data.items.map((t) => (
            <TemplateCard
              key={t.id}
              template={t}
              workspaceId={workspaceId}
              onSelect={setSelectedId}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {!isLoading && !isError && (
        <div className="flex items-center gap-2">
          {prevCursors.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              data-testid="template-list-prev-btn"
              onClick={handlePrev}
            >
              Previous
            </Button>
          )}
          {data?.has_more && (
            <Button
              variant="outline"
              size="sm"
              data-testid="template-list-next-btn"
              onClick={handleNext}
            >
              Next
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
