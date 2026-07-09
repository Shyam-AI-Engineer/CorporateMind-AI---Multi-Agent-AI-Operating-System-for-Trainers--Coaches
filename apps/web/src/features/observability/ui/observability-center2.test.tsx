/**
 * Frontend unit tests — Sprint 57: Observability & Diagnostics Center (part 2).
 * Covers: observabilityKeys, ApiHealthPanel, DiagnosticsPanel, ObservabilityCenter.
 * NO jest-dom matchers.
 */

import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type {
  ApiHealth,
  ModuleHealth,
  ModuleHealthItem,
  PlatformSummary,
  RecentErrorItem,
  RecentErrors,
} from "@/features/observability/types";
import { observabilityKeys } from "@/features/observability/api/use-observability";
import { ApiHealthPanel } from "@/features/observability/ui/ApiHealthPanel";
import { DiagnosticsPanel } from "@/features/observability/ui/DiagnosticsPanel";
import { ObservabilityCenter } from "@/features/observability/ui/ObservabilityCenter";

afterEach(() => vi.clearAllMocks());

// ── QueryClient wrapper ────────────────────────────────────────────────────────

function withQueryClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

// ── Shared fixtures ────────────────────────────────────────────────────────────

const NOW = "2026-07-09T10:00:00Z";

const fastApiHealth: ApiHealth = {
  registered_routes: 245,
  average_response_bucket: "fast",
  error_rate: 0.0,
  checked_at: NOW,
};

const slowApiHealth: ApiHealth = {
  registered_routes: 245,
  average_response_bucket: "slow",
  error_rate: 0.05,
  checked_at: NOW,
};

function makeError(overrides: Partial<RecentErrorItem> = {}): RecentErrorItem {
  return {
    source: "billing",
    message: "invoice_create_failed",
    severity: "critical",
    occurred_at: NOW,
    ...overrides,
  };
}

function makeErrors(items: RecentErrorItem[] = []): RecentErrors {
  return {
    errors: items,
    total: items.length,
    checked_at: NOW,
  };
}

function makeModuleItem(overrides: Partial<ModuleHealthItem> = {}): ModuleHealthItem {
  return {
    module: "customers",
    healthy: true,
    enabled: true,
    record_count: 100,
    cache_enabled: true,
    checked_at: NOW,
    ...overrides,
  };
}

const mockSummary: PlatformSummary = {
  overall_health_score: 1.0,
  api_health: "healthy",
  database_health: "healthy",
  cache_health: "healthy",
  storage_health: "healthy",
  active_modules: 12,
  healthy_modules: 12,
  warning_modules: 0,
  checked_at: NOW,
};

// ── Module-level hook mocks ────────────────────────────────────────────────────

const mockUsePlatformSummary = vi.fn();
const mockUseCacheHealth = vi.fn();
const mockUseDatabaseHealth = vi.fn();
const mockUseApiHealth = vi.fn();
const mockUseModuleHealth = vi.fn();
const mockUseRecentErrors = vi.fn();

vi.mock("@/features/observability/api/use-observability", async (importOriginal) => {
  const original = (await importOriginal()) as Record<string, unknown>;
  return {
    ...original,
    usePlatformSummary: (...args: unknown[]) => mockUsePlatformSummary(...args),
    useCacheHealth: (...args: unknown[]) => mockUseCacheHealth(...args),
    useDatabaseHealth: (...args: unknown[]) => mockUseDatabaseHealth(...args),
    useApiHealth: (...args: unknown[]) => mockUseApiHealth(...args),
    useModuleHealth: (...args: unknown[]) => mockUseModuleHealth(...args),
    useRecentErrors: (...args: unknown[]) => mockUseRecentErrors(...args),
  };
});

// ── observabilityKeys ──────────────────────────────────────────────────────────

describe("observabilityKeys", () => {
  it("summary key is array starting with observability", () => {
    const key = observabilityKeys.summary();
    expect(key[0]).toBe("observability");
    expect(key[1]).toBe("summary");
  });

  it("cache key", () => {
    const key = observabilityKeys.cache();
    expect(key[0]).toBe("observability");
    expect(key[1]).toBe("cache");
  });

  it("database key", () => {
    const key = observabilityKeys.database();
    expect(key[0]).toBe("observability");
    expect(key[1]).toBe("database");
  });

  it("api key", () => {
    const key = observabilityKeys.api();
    expect(key[0]).toBe("observability");
    expect(key[1]).toBe("api");
  });

  it("modules key", () => {
    const key = observabilityKeys.modules();
    expect(key[0]).toBe("observability");
    expect(key[1]).toBe("modules");
  });

  it("errors key", () => {
    const key = observabilityKeys.errors();
    expect(key[0]).toBe("observability");
    expect(key[1]).toBe("errors");
  });

  it("all keys have different second element", () => {
    const keys = [
      observabilityKeys.summary(),
      observabilityKeys.cache(),
      observabilityKeys.database(),
      observabilityKeys.api(),
      observabilityKeys.modules(),
      observabilityKeys.errors(),
    ];
    const seconds = keys.map((k) => k[1]);
    const unique = new Set(seconds);
    expect(unique.size).toBe(6);
  });
});

// ── ApiHealthPanel ─────────────────────────────────────────────────────────────

describe("ApiHealthPanel", () => {
  it("renders the panel", () => {
    render(<ApiHealthPanel health={fastApiHealth} />);
    expect(screen.getByTestId("api-health-panel")).not.toBeNull();
  });

  it("shows route count", () => {
    render(<ApiHealthPanel health={fastApiHealth} />);
    expect(screen.getByTestId("route-count").textContent).toBe("245");
  });

  it("shows 0.00% error rate when clean", () => {
    render(<ApiHealthPanel health={fastApiHealth} />);
    expect(screen.getByTestId("error-rate").textContent).toBe("0.00%");
  });

  it("shows 5.00% error rate for 0.05 rate", () => {
    render(<ApiHealthPanel health={slowApiHealth} />);
    expect(screen.getByTestId("error-rate").textContent).toBe("5.00%");
  });

  it("shows fast response bucket badge", () => {
    render(<ApiHealthPanel health={fastApiHealth} />);
    expect(screen.getByTestId("response-bucket").textContent).toBe("fast");
  });

  it("shows slow response bucket badge", () => {
    render(<ApiHealthPanel health={slowApiHealth} />);
    expect(screen.getByTestId("response-bucket").textContent).toBe("slow");
  });

  it("shows moderate response bucket", () => {
    const moderateHealth: ApiHealth = { ...fastApiHealth, average_response_bucket: "moderate" };
    render(<ApiHealthPanel health={moderateHealth} />);
    expect(screen.getByTestId("response-bucket").textContent).toBe("moderate");
  });

  it("renders route count for different value", () => {
    const health: ApiHealth = { ...fastApiHealth, registered_routes: 50 };
    render(<ApiHealthPanel health={health} />);
    expect(screen.getByTestId("route-count").textContent).toBe("50");
  });

  it("shows 1.00% error rate for 0.01 rate", () => {
    const health: ApiHealth = { ...fastApiHealth, error_rate: 0.01 };
    render(<ApiHealthPanel health={health} />);
    expect(screen.getByTestId("error-rate").textContent).toBe("1.00%");
  });
});

// ── DiagnosticsPanel ──────────────────────────────────────────────────────────

describe("DiagnosticsPanel — empty", () => {
  it("renders panel", () => {
    render(<DiagnosticsPanel errors={makeErrors()} />);
    expect(screen.getByTestId("diagnostics-panel")).not.toBeNull();
  });

  it("shows no-errors message when empty", () => {
    render(<DiagnosticsPanel errors={makeErrors()} />);
    expect(screen.getByTestId("no-errors")).not.toBeNull();
  });

  it("no-errors message is positive", () => {
    render(<DiagnosticsPanel errors={makeErrors()} />);
    expect(screen.getByTestId("no-errors").textContent).toContain("No warnings");
  });

  it("does not render error items when empty", () => {
    render(<DiagnosticsPanel errors={makeErrors()} />);
    expect(screen.queryAllByTestId("error-item").length).toBe(0);
  });
});

describe("DiagnosticsPanel — with errors", () => {
  const errors = makeErrors([
    makeError({ severity: "critical", message: "payment_failed", source: "payments" }),
    makeError({ severity: "warning", message: "slow_query", source: "database" }),
  ]);

  it("renders error items", () => {
    render(<DiagnosticsPanel errors={errors} />);
    expect(screen.getAllByTestId("error-item").length).toBe(2);
  });

  it("shows critical severity badge", () => {
    render(<DiagnosticsPanel errors={errors} />);
    expect(screen.getByTestId("error-severity-critical")).not.toBeNull();
    expect(screen.getByTestId("error-severity-critical").textContent).toBe("critical");
  });

  it("shows warning severity badge", () => {
    render(<DiagnosticsPanel errors={errors} />);
    expect(screen.getByTestId("error-severity-warning")).not.toBeNull();
    expect(screen.getByTestId("error-severity-warning").textContent).toBe("warning");
  });

  it("shows event count in header", () => {
    render(<DiagnosticsPanel errors={errors} />);
    expect(screen.getByTestId("diagnostics-panel").textContent).toContain("2 events");
  });

  it("singular 'event' for total=1", () => {
    const single = makeErrors([makeError()]);
    render(<DiagnosticsPanel errors={single} />);
    expect(screen.getByTestId("diagnostics-panel").textContent).toContain("1 event");
  });

  it("does not show no-errors when there are errors", () => {
    render(<DiagnosticsPanel errors={errors} />);
    expect(screen.queryByTestId("no-errors")).toBeNull();
  });

  it("shows message text in error item", () => {
    render(<DiagnosticsPanel errors={errors} />);
    expect(screen.getByTestId("diagnostics-panel").textContent).toContain("payment_failed");
  });

  it("shows source in error item", () => {
    render(<DiagnosticsPanel errors={errors} />);
    expect(screen.getByTestId("diagnostics-panel").textContent).toContain("payments");
  });
});

// ── ObservabilityCenter ────────────────────────────────────────────────────────

function mockAllLoading() {
  const loadingState = { data: undefined, isLoading: true, isError: false };
  mockUsePlatformSummary.mockReturnValue(loadingState);
  mockUseCacheHealth.mockReturnValue(loadingState);
  mockUseDatabaseHealth.mockReturnValue(loadingState);
  mockUseApiHealth.mockReturnValue(loadingState);
  mockUseModuleHealth.mockReturnValue(loadingState);
  mockUseRecentErrors.mockReturnValue(loadingState);
}

function mockAllError() {
  const errState = { data: undefined, isLoading: false, isError: true };
  mockUsePlatformSummary.mockReturnValue(errState);
  mockUseCacheHealth.mockReturnValue(errState);
  mockUseDatabaseHealth.mockReturnValue(errState);
  mockUseApiHealth.mockReturnValue(errState);
  mockUseModuleHealth.mockReturnValue(errState);
  mockUseRecentErrors.mockReturnValue(errState);
}

function mockAllReady() {
  const makeModuleHealthData = (): ModuleHealth => ({
    modules: [makeModuleItem()],
    total: 1,
    healthy: 1,
    warning: 0,
  });
  mockUsePlatformSummary.mockReturnValue({ data: mockSummary, isLoading: false, isError: false });
  mockUseCacheHealth.mockReturnValue({ data: { redis_available: true, estimated_hit_ratio: 0.8, estimated_miss_ratio: 0.2, ttl_configuration: { obs: 300 }, checked_at: NOW }, isLoading: false, isError: false });
  mockUseDatabaseHealth.mockReturnValue({ data: { connection_ok: true, estimated_latency_ms: 3.2, table_count: 45, migration_version: "abc", checked_at: NOW }, isLoading: false, isError: false });
  mockUseApiHealth.mockReturnValue({ data: fastApiHealth, isLoading: false, isError: false });
  mockUseModuleHealth.mockReturnValue({ data: makeModuleHealthData(), isLoading: false, isError: false });
  mockUseRecentErrors.mockReturnValue({ data: makeErrors([]), isLoading: false, isError: false });
}

describe("ObservabilityCenter", () => {
  it("shows loading state", () => {
    mockAllLoading();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByTestId("observability-loading")).not.toBeNull();
  });

  it("loading message is informative", () => {
    mockAllLoading();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByTestId("observability-loading").textContent).toContain("Loading platform diagnostics");
  });

  it("shows error state", () => {
    mockAllError();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByTestId("observability-error")).not.toBeNull();
  });

  it("error message is helpful", () => {
    mockAllError();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByTestId("observability-error").textContent).toContain("Failed to load");
  });

  it("does not render center when loading", () => {
    mockAllLoading();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.queryByTestId("observability-center")).toBeNull();
  });

  it("renders center when all data available", () => {
    mockAllReady();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByTestId("observability-center")).not.toBeNull();
  });

  it("renders platform health cards when data loaded", () => {
    mockAllReady();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByTestId("platform-health-cards")).not.toBeNull();
  });

  it("renders cache health panel when data loaded", () => {
    mockAllReady();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByTestId("cache-health-panel")).not.toBeNull();
  });

  it("renders database health panel when data loaded", () => {
    mockAllReady();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByTestId("database-health-panel")).not.toBeNull();
  });

  it("renders api health panel when data loaded", () => {
    mockAllReady();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByTestId("api-health-panel")).not.toBeNull();
  });

  it("renders module health table when data loaded", () => {
    mockAllReady();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByTestId("module-health-table")).not.toBeNull();
  });

  it("renders diagnostics panel when data loaded", () => {
    mockAllReady();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByTestId("diagnostics-panel")).not.toBeNull();
  });

  it("renders Platform Overview section heading", () => {
    mockAllReady();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByRole("heading", { name: /Platform Overview/i })).not.toBeNull();
  });

  it("renders Infrastructure section heading", () => {
    mockAllReady();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByRole("heading", { name: /Infrastructure/i })).not.toBeNull();
  });

  it("renders Module Health section heading", () => {
    mockAllReady();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByRole("heading", { name: /Module Health/i })).not.toBeNull();
  });

  it("renders Diagnostics section heading", () => {
    mockAllReady();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByRole("heading", { name: /^Diagnostics$/i })).not.toBeNull();
  });

  it("shows 100% score when all healthy", () => {
    mockAllReady();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByTestId("score-ring").textContent).toContain("100%");
  });

  it("shows no-errors message when error list is empty", () => {
    mockAllReady();
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByTestId("no-errors")).not.toBeNull();
  });

  it("shows diagnostics with errors when present", () => {
    mockAllReady();
    mockUseRecentErrors.mockReturnValue({
      data: makeErrors([makeError()]),
      isLoading: false,
      isError: false,
    });
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getAllByTestId("error-item").length).toBe(1);
  });

  it("loading takes priority over partial data", () => {
    mockUsePlatformSummary.mockReturnValue({ data: mockSummary, isLoading: true, isError: false });
    mockUseCacheHealth.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    mockUseDatabaseHealth.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    mockUseApiHealth.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    mockUseModuleHealth.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    mockUseRecentErrors.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByTestId("observability-loading")).not.toBeNull();
  });

  it("error in any query shows error state", () => {
    mockAllReady();
    mockUseModuleHealth.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    render(withQueryClient(<ObservabilityCenter />));
    expect(screen.getByTestId("observability-error")).not.toBeNull();
  });
});
