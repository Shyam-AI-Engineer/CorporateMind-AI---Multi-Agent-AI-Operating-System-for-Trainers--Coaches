import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { RankedContact } from "@/features/hr/types";
import type { HRContact } from "@/features/hr/types";

// ── Shared spies (captured in factory closures) ───────────────────────────────

const mockPush = vi.fn();
const mockRank = vi.fn();
const mockAddRecipients = vi.fn();
const mockReset = vi.fn();

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeRanked(contactId: string, score = 9): RankedContact {
  return {
    contact_id: contactId,
    score,
    reason: `Good fit — ${contactId}`,
    contact: {
      id: contactId,
      company_id: "co-1",
      full_name: `Contact ${contactId}`,
      title: "HR Manager",
      email: `${contactId}@example.com`,
      email_deliverable: true,
      preferred_language: null,
      source_type: "webinar_registration",
      is_contactable: true,
      opted_in_at: "2024-01-01T00:00:00Z",
      created_at: "2024-01-01T00:00:00Z",
    },
  };
}

const MOCK_RANKINGS = [makeRanked("c1"), makeRanked("c2", 8)];

const MOCK_CONTACTS: HRContact[] = [
  {
    id: "c1",
    company_id: "co-1",
    full_name: "Contact c1",
    title: "HR Manager",
    email: "c1@example.com",
    email_deliverable: true,
    preferred_language: null,
    source_type: "webinar_registration",
    is_contactable: true,
    opted_in_at: "2024-01-01T00:00:00Z",
    created_at: "2024-01-01T00:00:00Z",
  },
];

// ── Module mocks ─────────────────────────────────────────────────────────────
// Each mock factory is hoisted by vitest — spies are captured via closures.

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

// next/link renders as a plain anchor in jsdom.
vi.mock("next/link", async () => {
  const { createElement } = await import("react");
  return {
    default: ({
      href,
      children,
      className,
    }: {
      href: string;
      children: React.ReactNode;
      className?: string;
    }) => createElement("a", { href, className }, children),
  };
});

vi.mock("@/features/hr/api/use-contacts", () => ({
  useRankContacts: () => ({
    mutate: mockRank,
    isPending: false,
    data: { rankings: MOCK_RANKINGS },
    error: null,
    reset: mockReset,
  }),
}));

vi.mock("@/features/campaigns/api/use-campaigns", () => ({
  useAddRecipients: () => ({
    mutate: mockAddRecipients,
    isPending: false,
  }),
  useCampaigns: () => ({
    data: {
      items: [
        {
          id: "camp-1",
          workspace_id: "ws-1",
          name: "Q2 Campaign",
          channel: "email",
          status: "draft",
          recipient_count: 0,
          scheduled_at: null,
          started_at: null,
          completed_at: null,
          created_at: "2024-01-01T00:00:00Z",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    },
    isLoading: false,
  }),
}));

vi.mock("@/features/trainer/api/use-trainer-profile", () => ({
  useTrainerProfile: () => ({ data: null, isLoading: false }),
}));

vi.mock("@/hooks/use-workspace", () => ({
  useWorkspace: () => ({ workspaceId: "ws-1" }),
}));

// Import after mocks are registered.
const { RankContactsDialog } = await import("./rank-contacts-dialog");

// ── Helpers ──────────────────────────────────────────────────────────────────

function renderDialog(props: Partial<{ open: boolean }> = {}) {
  return render(
    <RankContactsDialog
      contacts={MOCK_CONTACTS}
      open={props.open ?? true}
      onOpenChange={vi.fn()}
    />,
  );
}

// Advances the dialog from step 1 → step 2 by filling and submitting the form.
function advanceToStep2() {
  // mockRank simulates immediate success by calling onSuccess.
  mockRank.mockImplementation(
    (_req: unknown, opts?: { onSuccess?: () => void }) => {
      opts?.onSuccess?.();
    },
  );
  fireEvent.change(screen.getByLabelText(/your niche/i), {
    target: { value: "Leadership" },
  });
  fireEvent.click(screen.getByRole("button", { name: /rank contacts/i }));
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("RankContactsDialog", () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockRank.mockClear();
    mockAddRecipients.mockClear();
    mockReset.mockClear();
  });

  describe("step 1 — rank form", () => {
    it("renders the rank form on open", () => {
      renderDialog();
      expect(screen.queryByText(/rank contacts by fit/i)).not.toBeNull();
      expect(screen.queryByLabelText(/your niche/i)).not.toBeNull();
    });

    it("calls rank mutate with correct payload when form is submitted", () => {
      mockRank.mockImplementation(() => {}); // don't advance step
      renderDialog();
      fireEvent.change(screen.getByLabelText(/your niche/i), {
        target: { value: "Sales Training" },
      });
      fireEvent.change(screen.getByLabelText(/topics/i), {
        target: { value: "Mindset, Communication" },
      });
      fireEvent.click(screen.getByRole("button", { name: /rank contacts/i }));
      expect(mockRank).toHaveBeenCalledWith(
        expect.objectContaining({
          trainer_niche: "Sales Training",
          trainer_topics: ["Mindset", "Communication"],
        }),
        expect.objectContaining({ onSuccess: expect.any(Function) }),
      );
    });
  });

  describe("step transition", () => {
    it("transitions to step 2 when rank succeeds", () => {
      renderDialog();
      advanceToStep2();
      // Step 2 title should now be visible
      expect(
        screen.queryByText(/select contacts to add/i),
      ).not.toBeNull();
    });

    it("renders RankResultsPanel with ranking data in step 2", () => {
      renderDialog();
      advanceToStep2();
      // Both ranked contacts should appear (score ≥ 7 by default threshold)
      expect(screen.queryByText("Contact c1")).not.toBeNull();
      expect(screen.queryByText("Contact c2")).not.toBeNull();
    });

    it("renders CampaignPicker with draft campaigns in step 2", () => {
      renderDialog();
      advanceToStep2();
      expect(screen.queryByText("Q2 Campaign")).not.toBeNull();
    });
  });

  describe("step 2 — back button", () => {
    it("returns to step 1 when Back is clicked", () => {
      renderDialog();
      advanceToStep2();
      fireEvent.click(screen.getByRole("button", { name: /← back/i }));
      expect(screen.queryByLabelText(/your niche/i)).not.toBeNull();
    });

    it("resets rank data when Back is clicked", () => {
      renderDialog();
      advanceToStep2();
      fireEvent.click(screen.getByRole("button", { name: /← back/i }));
      expect(mockReset).toHaveBeenCalled();
    });
  });

  describe("step 2 — add recipients", () => {
    it("calls addRecipients with selected contact ids and campaign id", () => {
      mockAddRecipients.mockImplementation(() => {});
      renderDialog();
      advanceToStep2();

      // Select both visible contacts via select-all header checkbox
      fireEvent.click(screen.getByRole("checkbox", { name: /select all/i }));

      // Pick the draft campaign
      fireEvent.change(screen.getByRole("combobox"), {
        target: { value: "camp-1" },
      });

      fireEvent.click(screen.getByRole("button", { name: /add 2 contacts/i }));

      expect(mockAddRecipients).toHaveBeenCalledWith(
        expect.objectContaining({
          campaignId: "camp-1",
          contactIds: expect.arrayContaining(["c1", "c2"]),
        }),
        expect.objectContaining({ onSuccess: expect.any(Function) }),
      );
    });

    it("navigates to campaign detail page on success", () => {
      mockAddRecipients.mockImplementation(
        (_req: unknown, opts?: { onSuccess?: () => void }) => {
          opts?.onSuccess?.();
        },
      );
      renderDialog();
      advanceToStep2();

      fireEvent.click(screen.getByRole("checkbox", { name: /select all/i }));
      fireEvent.change(screen.getByRole("combobox"), {
        target: { value: "camp-1" },
      });
      fireEvent.click(screen.getByRole("button", { name: /add/i }));

      expect(mockPush).toHaveBeenCalledWith("/campaigns/camp-1");
    });

    it("Add button is disabled when no contacts are selected", () => {
      renderDialog();
      advanceToStep2();
      // No selection, no campaign
      const btn = screen.getByRole("button", { name: /add contacts/i });
      expect((btn as HTMLButtonElement).disabled).toBe(true);
    });
  });
});
