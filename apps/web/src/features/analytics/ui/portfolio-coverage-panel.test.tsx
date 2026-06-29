import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

// ── Hook mocks ────────────────────────────────────────────────────────────────

vi.mock("@/features/analytics/api/use-analytics", () => ({
  usePortfolio: vi.fn(),
  useCoverage: vi.fn(),
}));

import {
  usePortfolio,
  useCoverage,
} from "@/features/analytics/api/use-analytics";
import type { PortfolioOut, CoverageOut } from "@/features/analytics/types";
import { PortfolioCoveragePanel } from "./portfolio-coverage-panel";

const mockUsePortfolio = vi.mocked(usePortfolio);
const mockUseCoverage = vi.mocked(useCoverage);

// ── Fixtures ──────────────────────────────────────────────────────────────────

const fullPortfolio: PortfolioOut = {
  generated_at: "2026-06-25T10:00:00Z",
  total_recommendations: 100,
  recommendation_types: [
    {
      recommendation_type: "topic",
      count: 40,
      percentage: 40.0,
      acted_rate: 65.0,
      success_rate: 45.0,
    },
    {
      recommendation_type: "channel",
      count: 30,
      percentage: 30.0,
      acted_rate: 55.0,
      success_rate: 35.0,
    },
    {
      recommendation_type: "industry",
      count: 30,
      percentage: 30.0,
      acted_rate: 50.0,
      success_rate: 30.0,
    },
  ],
  dominant_type: "topic",
  least_used_type: "channel",
  portfolio_balance: {
    diversity_index: 78.5,
    balance_rating: "good",
  },
  insufficient_data: false,
};

const fullCoverage: CoverageOut = {
  generated_at: "2026-06-25T10:00:00Z",
  coverage: [
    {
      recommendation_type: "campaign",
      present: true,
      count: 10,
      last_generated_at: "2026-06-20",
      days_since_last_generated: 5,
    },
    {
      recommendation_type: "channel",
      present: true,
      count: 30,
      last_generated_at: "2026-06-10",
      days_since_last_generated: 15,
    },
    {
      recommendation_type: "industry",
      present: false,
      count: 0,
      last_generated_at: null,
      days_since_last_generated: null,
    },
    {
      recommendation_type: "pricing",
      present: true,
      count: 5,
      last_generated_at: "2026-05-01",
      days_since_last_generated: 55,
    },
    {
      recommendation_type: "topic",
      present: true,
      count: 40,
      last_generated_at: "2026-06-24",
      days_since_last_generated: 1,
    },
  ],
  missing_types: ["industry"],
  stale_types: ["pricing"],
};

function setStates(
  p: Partial<ReturnType<typeof usePortfolio>>,
  c: Partial<ReturnType<typeof useCoverage>>,
) {
  mockUsePortfolio.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    ...p,
  } as ReturnType<typeof usePortfolio>);
  mockUseCoverage.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    ...c,
  } as ReturnType<typeof useCoverage>);
}

const WS = "ws-portfolio-1";

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("PortfolioCoveragePanel", () => {
  beforeEach(() => vi.clearAllMocks());

  // ── Root ────────────────────────────────────────────────────────────────────

  it("renders the root panel element", () => {
    setStates({ isLoading: true }, { isLoading: true });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("portfolio-coverage-panel")).not.toBeNull();
  });

  // ── Loading states ──────────────────────────────────────────────────────────

  it("shows skeletons while portfolio is loading", () => {
    setStates({ isLoading: true }, { isLoading: false, data: fullCoverage });
    const { container } = render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(container.querySelectorAll("[data-testid='skeleton']").length).toBeGreaterThan(0);
  });

  it("shows skeletons while coverage is loading", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: true });
    const { container } = render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(container.querySelectorAll("[data-testid='skeleton']").length).toBeGreaterThan(0);
  });

  // ── Error states ────────────────────────────────────────────────────────────

  it("shows portfolio-error when portfolio query fails", () => {
    setStates({ isError: true }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("portfolio-error")).not.toBeNull();
    expect(screen.getByText(/failed to load portfolio data/i)).not.toBeNull();
  });

  it("shows coverage-error when coverage query fails", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isError: true });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("coverage-error")).not.toBeNull();
    expect(screen.getByText(/failed to load coverage data/i)).not.toBeNull();
  });

  it("portfolio error does not affect coverage section", () => {
    setStates({ isError: true }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("portfolio-error")).not.toBeNull();
    expect(screen.getByTestId("coverage-table")).not.toBeNull();
  });

  it("coverage error does not affect portfolio section", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isError: true });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("coverage-error")).not.toBeNull();
    expect(screen.getByTestId("card-total-recommendations")).not.toBeNull();
  });

  // ── Insufficient data ───────────────────────────────────────────────────────

  it("shows portfolio-insufficient when insufficient_data is true", () => {
    const insuffP: PortfolioOut = { ...fullPortfolio, insufficient_data: true };
    setStates({ isLoading: false, data: insuffP }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("portfolio-insufficient")).not.toBeNull();
    expect(screen.getByText(/no recommendation history available/i)).not.toBeNull();
  });

  // ── Section 1: Summary cards ────────────────────────────────────────────────

  it("renders card-total-recommendations with correct value", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    const card = screen.getByTestId("card-total-recommendations");
    expect(card.textContent).toContain("100");
  });

  it("renders card-dominant-type with correct value", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    const card = screen.getByTestId("card-dominant-type");
    expect(card.textContent).toContain("topic");
  });

  it("renders card-least-used-type with correct value", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    const card = screen.getByTestId("card-least-used-type");
    expect(card.textContent).toContain("channel");
  });

  it("renders card-diversity-index as percentage", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    const card = screen.getByTestId("card-diversity-index");
    expect(card.textContent).toContain("78.5%");
  });

  // ── Section 2: Distribution Table ──────────────────────────────────────────

  it("renders distribution-table when recommendation_types is non-empty", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("distribution-table")).not.toBeNull();
  });

  it("renders distribution-row for each type", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("distribution-row-topic")).not.toBeNull();
    expect(screen.getByTestId("distribution-row-channel")).not.toBeNull();
    expect(screen.getByTestId("distribution-row-industry")).not.toBeNull();
  });

  it("shows distribution-table-empty when recommendation_types is empty", () => {
    const emptyP: PortfolioOut = { ...fullPortfolio, recommendation_types: [] };
    setStates({ isLoading: false, data: emptyP }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("distribution-table-empty")).not.toBeNull();
  });

  it("distribution row contains percentage value", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    const row = screen.getByTestId("distribution-row-topic");
    expect(row.textContent).toContain("40.0%");
  });

  it("distribution row contains acted_rate value", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    const row = screen.getByTestId("distribution-row-topic");
    expect(row.textContent).toContain("65.0%");
  });

  // ── Section 3: Portfolio Balance ────────────────────────────────────────────

  it("renders portfolio-balance section", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("portfolio-balance")).not.toBeNull();
  });

  it("renders balance-rating with correct text", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("balance-rating").textContent).toContain("good");
  });

  it("renders diversity-gauge element", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("diversity-gauge")).not.toBeNull();
  });

  // ── Section 4: Coverage Table ───────────────────────────────────────────────

  it("renders coverage-table when coverage is non-empty", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("coverage-table")).not.toBeNull();
  });

  it("renders coverage-row for each type", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("coverage-row-campaign")).not.toBeNull();
    expect(screen.getByTestId("coverage-row-industry")).not.toBeNull();
    expect(screen.getByTestId("coverage-row-pricing")).not.toBeNull();
  });

  it("shows coverage-table-empty when coverage array is empty", () => {
    const emptyC: CoverageOut = { ...fullCoverage, coverage: [] };
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: emptyC });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("coverage-table-empty")).not.toBeNull();
  });

  it("coverage row for missing type shows Not Present", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    const row = screen.getByTestId("coverage-row-industry");
    expect(row.textContent).toContain("No");
  });

  it("coverage-status for stale type shows stale", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("coverage-status-pricing").textContent).toContain("stale");
  });

  it("coverage-status for healthy type shows healthy", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("coverage-status-topic").textContent).toContain("healthy");
  });

  // ── Section 5: Missing / Stale cards ───────────────────────────────────────

  it("renders missing-types-card", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("missing-types-card")).not.toBeNull();
  });

  it("renders stale-types-card", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("stale-types-card")).not.toBeNull();
  });

  it("lists missing type by testid", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("missing-type-industry")).not.toBeNull();
  });

  it("lists stale type by testid", () => {
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: fullCoverage });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByTestId("stale-type-pricing")).not.toBeNull();
  });

  it("shows all-present message when missing_types is empty", () => {
    const noMissing: CoverageOut = { ...fullCoverage, missing_types: [] };
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: noMissing });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByText(/all recommendation types have been generated/i)).not.toBeNull();
  });

  it("shows no-stale message when stale_types is empty", () => {
    const noStale: CoverageOut = { ...fullCoverage, stale_types: [] };
    setStates({ isLoading: false, data: fullPortfolio }, { isLoading: false, data: noStale });
    render(<PortfolioCoveragePanel workspaceId={WS} />);
    expect(screen.getByText(/no stale recommendation types/i)).not.toBeNull();
  });
});
