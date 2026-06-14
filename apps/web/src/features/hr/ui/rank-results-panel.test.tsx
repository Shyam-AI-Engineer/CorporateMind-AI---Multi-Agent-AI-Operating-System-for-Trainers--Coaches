import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { RankResultsPanel } from "./rank-results-panel";
import type { RankedContact } from "@/features/hr/types";

// ── Fixtures ─────────────────────────────────────────────────────────────────

function makeRanked(
  contactId: string,
  score: number,
  isContactable = true,
): RankedContact {
  return {
    contact_id: contactId,
    score,
    reason: `Reason for ${contactId}`,
    contact: {
      id: contactId,
      company_id: "co-1",
      full_name: `Contact ${contactId}`,
      title: "HR Manager",
      email: `${contactId}@example.com`,
      email_deliverable: true,
      preferred_language: null,
      source_type: "webinar_registration",
      is_contactable: isContactable,
      opted_in_at: "2024-01-01T00:00:00Z",
      created_at: "2024-01-01T00:00:00Z",
    },
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("RankResultsPanel", () => {
  describe("rendering", () => {
    it("renders contacts at or above the default 7+ threshold", () => {
      const rankings = [
        makeRanked("c1", 9),
        makeRanked("c2", 7),
        makeRanked("c3", 3), // below threshold — should be hidden
      ];
      render(<RankResultsPanel rankings={rankings} onSelectionChange={vi.fn()} />);
      expect(screen.queryByText("Contact c1")).not.toBeNull();
      expect(screen.queryByText("Contact c2")).not.toBeNull();
      expect(screen.queryByText("Contact c3")).toBeNull();
    });

    it("shows empty state when no contacts were ranked", () => {
      render(<RankResultsPanel rankings={[]} onSelectionChange={vi.fn()} />);
      expect(screen.queryByText(/no contacts were ranked/i)).not.toBeNull();
    });

    it("shows score summary counts for qualified, medium and poor", () => {
      const rankings = [
        makeRanked("c1", 9),  // qualified
        makeRanked("c2", 5),  // medium
        makeRanked("c3", 2),  // poor
      ];
      render(<RankResultsPanel rankings={rankings} onSelectionChange={vi.fn()} />);
      expect(screen.queryByText("Qualified (7+)")).not.toBeNull();
      expect(screen.queryByText("Medium (4–6)")).not.toBeNull();
      expect(screen.queryByText("Poor (0–3)")).not.toBeNull();
    });
  });

  describe("threshold filter", () => {
    it("shows all contacts when All is selected", () => {
      const rankings = [makeRanked("c1", 9), makeRanked("c2", 3)];
      render(<RankResultsPanel rankings={rankings} onSelectionChange={vi.fn()} />);
      fireEvent.click(screen.getByRole("button", { name: "All" }));
      expect(screen.queryByText("Contact c2")).not.toBeNull();
    });

    it("hides contacts below 8 when 8+ is selected", () => {
      const rankings = [makeRanked("c1", 9), makeRanked("c2", 7)];
      render(<RankResultsPanel rankings={rankings} onSelectionChange={vi.fn()} />);
      fireEvent.click(screen.getByRole("button", { name: "8+" }));
      expect(screen.queryByText("Contact c1")).not.toBeNull();
      expect(screen.queryByText("Contact c2")).toBeNull();
    });

    it("shows empty message when no contacts meet the threshold", () => {
      const rankings = [makeRanked("c1", 5)];
      render(<RankResultsPanel rankings={rankings} onSelectionChange={vi.fn()} />);
      // Default threshold is 7+, score 5 is hidden
      expect(screen.queryByText(/no contacts at this score threshold/i)).not.toBeNull();
    });
  });

  describe("selection", () => {
    it("calls onSelectionChange with contact id when a row checkbox is clicked", () => {
      const onSelectionChange = vi.fn();
      render(
        <RankResultsPanel
          rankings={[makeRanked("c1", 9)]}
          onSelectionChange={onSelectionChange}
        />,
      );
      fireEvent.click(screen.getByRole("checkbox", { name: "Contact c1" }));
      expect(onSelectionChange).toHaveBeenCalledWith(["c1"]);
    });

    it("removes contact id when checkbox is unchecked", () => {
      const onSelectionChange = vi.fn();
      render(
        <RankResultsPanel
          rankings={[makeRanked("c1", 9)]}
          onSelectionChange={onSelectionChange}
        />,
      );
      const cb = screen.getByRole("checkbox", { name: "Contact c1" });
      fireEvent.click(cb); // select
      fireEvent.click(cb); // deselect
      const lastCall = onSelectionChange.mock.calls.at(-1)![0] as string[];
      expect(lastCall).not.toContain("c1");
    });

    it("select-all header checkbox selects all visible contactable contacts", () => {
      const onSelectionChange = vi.fn();
      const rankings = [makeRanked("c1", 9), makeRanked("c2", 8)];
      render(
        <RankResultsPanel rankings={rankings} onSelectionChange={onSelectionChange} />,
      );
      fireEvent.click(screen.getByRole("checkbox", { name: /select all/i }));
      const lastCall = onSelectionChange.mock.calls.at(-1)![0] as string[];
      expect(lastCall).toContain("c1");
      expect(lastCall).toContain("c2");
    });

    it("select-all deselects all when already fully selected", () => {
      const onSelectionChange = vi.fn();
      const rankings = [makeRanked("c1", 9)];
      render(
        <RankResultsPanel rankings={rankings} onSelectionChange={onSelectionChange} />,
      );
      const header = screen.getByRole("checkbox", { name: /select all/i });
      fireEvent.click(header); // select all
      fireEvent.click(header); // deselect all
      const lastCall = onSelectionChange.mock.calls.at(-1)![0] as string[];
      expect(lastCall).toHaveLength(0);
    });
  });

  describe("non-contactable contacts", () => {
    it("renders non-contactable contact with a disabled checkbox", () => {
      // Use All threshold to make the contact visible regardless of score
      const rankings = [makeRanked("c1", 9, false)];
      render(
        <RankResultsPanel rankings={rankings} onSelectionChange={vi.fn()} />,
      );
      // c1 has score 9 — visible by default threshold
      const cb = screen.getByRole("checkbox", { name: "Contact c1" });
      expect((cb as HTMLInputElement).disabled).toBe(true);
    });

    it("does not include non-contactable ids when select-all is clicked", () => {
      const onSelectionChange = vi.fn();
      const rankings = [
        makeRanked("c1", 9, true),   // contactable
        makeRanked("c2", 8, false),  // NOT contactable
      ];
      render(
        <RankResultsPanel rankings={rankings} onSelectionChange={onSelectionChange} />,
      );
      fireEvent.click(screen.getByRole("checkbox", { name: /select all/i }));
      const lastCall = onSelectionChange.mock.calls.at(-1)![0] as string[];
      expect(lastCall).toContain("c1");
      expect(lastCall).not.toContain("c2");
    });
  });
});
