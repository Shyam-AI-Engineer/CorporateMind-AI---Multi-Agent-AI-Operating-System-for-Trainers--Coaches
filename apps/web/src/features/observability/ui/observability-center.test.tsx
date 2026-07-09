/**
 * Frontend unit tests — Sprint 57: Observability & Diagnostics Center (part 1).
 * Covers: types/constants, PlatformHealthCards, ModuleHealthTable,
 *         CacheHealthPanel, DatabaseHealthPanel.
 * NO jest-dom matchers.
 */

import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type {
  ApiHealth,
  CacheHealth,
  DatabaseHealth,
  ModuleHealth,
  ModuleHealthItem,
  PlatformSummary,
  RecentErrors,
} from "@/features/observability/types";
import {
  HEALTH_STATUS_LABELS,
  MODULE_DISPLAY_NAMES,
  SEVERITY_LABELS,
} from "@/features/observability/types";
import { PlatformHealthCards } from "@/features/observability/ui/PlatformHealthCards";
import { ModuleHealthTable } from "@/features/observability/ui/ModuleHealthTable";
import { CacheHealthPanel } from "@/features/observability/ui/CacheHealthPanel";
import { DatabaseHealthPanel } from "@/features/observability/ui/DatabaseHealthPanel";

afterEach(() => vi.clearAllMocks());

// ── Shared fixtures ────────────────────────────────────────────────────────────

const NOW = "2026-07-09T10:00:00Z";

const healthySummary: PlatformSummary = {
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

const degradedSummary: PlatformSummary = {
  ...healthySummary,
  overall_health_score: 0.6,
  database_health: "down",
  cache_health: "degraded",
  warning_modules: 2,
};

const healthyCache: CacheHealth = {
  redis_available: true,
  estimated_hit_ratio: 0.75,
  estimated_miss_ratio: 0.25,
  ttl_configuration: { observability_summary: 300, observability_modules: 300, reporting_list: 300 },
  checked_at: NOW,
};

const unhealthyCache: CacheHealth = {
  redis_available: false,
  estimated_hit_ratio: 0.0,
  estimated_miss_ratio: 0.0,
  ttl_configuration: {},
  checked_at: NOW,
};

const healthyDb: DatabaseHealth = {
  connection_ok: true,
  estimated_latency_ms: 2.5,
  table_count: 42,
  migration_version: "abc123def456",
  checked_at: NOW,
};

const downDb: DatabaseHealth = {
  connection_ok: false,
  estimated_latency_ms: -1,
  table_count: 0,
  migration_version: "unknown",
  checked_at: NOW,
};

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

function makeModuleHealth(overrides: Partial<ModuleHealth> = {}): ModuleHealth {
  const items = [
    makeModuleItem({ module: "customers", record_count: 500 }),
    makeModuleItem({ module: "billing", healthy: false, cache_enabled: true }),
    makeModuleItem({ module: "executive_dashboard", record_count: 0, cache_enabled: false }),
  ];
  return {
    modules: items,
    total: items.length,
    healthy: 2,
    warning: 1,
    ...overrides,
  };
}

// ── Types and constants ────────────────────────────────────────────────────────

describe("HEALTH_STATUS_LABELS", () => {
  it("contains healthy label", () => {
    expect(HEALTH_STATUS_LABELS.healthy).toBe("Healthy");
  });

  it("contains degraded label", () => {
    expect(HEALTH_STATUS_LABELS.degraded).toBe("Degraded");
  });

  it("contains down label", () => {
    expect(HEALTH_STATUS_LABELS.down).toBe("Down");
  });

  it("has exactly 3 keys", () => {
    expect(Object.keys(HEALTH_STATUS_LABELS).length).toBe(3);
  });
});

describe("MODULE_DISPLAY_NAMES", () => {
  const requiredModules = [
    "customers", "training", "billing", "payments",
    "workflows", "approvals", "notifications", "audit",
    "admin", "integrations", "reporting", "executive_dashboard",
  ];

  it.each(requiredModules)("has display name for %s", (mod) => {
    expect(MODULE_DISPLAY_NAMES[mod]).not.toBeUndefined();
    expect(MODULE_DISPLAY_NAMES[mod].length).toBeGreaterThan(0);
  });

  it("has 12 entries", () => {
    expect(Object.keys(MODULE_DISPLAY_NAMES).length).toBe(12);
  });

  it("executive_dashboard label is readable", () => {
    expect(MODULE_DISPLAY_NAMES.executive_dashboard).toBe("Executive Dashboard");
  });
});

describe("SEVERITY_LABELS", () => {
  it("has warning label", () => {
    expect(SEVERITY_LABELS.warning).toBe("Warning");
  });

  it("has critical label", () => {
    expect(SEVERITY_LABELS.critical).toBe("Critical");
  });
});

// ── PlatformHealthCards ────────────────────────────────────────────────────────

describe("PlatformHealthCards", () => {
  it("renders the container", () => {
    render(<PlatformHealthCards summary={healthySummary} />);
    const el = screen.getByTestId("platform-health-cards");
    expect(el).not.toBeNull();
  });

  it("shows 100% score ring when fully healthy", () => {
    render(<PlatformHealthCards summary={healthySummary} />);
    const ring = screen.getByTestId("score-ring");
    expect(ring.textContent).toContain("100%");
  });

  it("shows 60% score ring for degraded summary", () => {
    render(<PlatformHealthCards summary={degradedSummary} />);
    const ring = screen.getByTestId("score-ring");
    expect(ring.textContent).toContain("60%");
  });

  it("renders 4 health cards (API, DB, Cache, Storage)", () => {
    render(<PlatformHealthCards summary={healthySummary} />);
    const cards = screen.getAllByTestId("health-card");
    expect(cards.length).toBe(4);
  });

  it("shows api_health value in a card", () => {
    render(<PlatformHealthCards summary={healthySummary} />);
    const values = screen.getAllByTestId("health-value");
    const texts = values.map((v) => v.textContent);
    expect(texts.some((t) => t?.includes("healthy"))).toBe(true);
  });

  it("shows down status for database", () => {
    render(<PlatformHealthCards summary={degradedSummary} />);
    const values = screen.getAllByTestId("health-value");
    const texts = values.map((v) => v.textContent);
    expect(texts.some((t) => t?.includes("down"))).toBe(true);
  });

  it("renders dots for each health card", () => {
    render(<PlatformHealthCards summary={healthySummary} />);
    const dots = screen.getAllByTestId("health-dot");
    expect(dots.length).toBe(4);
  });

  it("score ring shows 'Overall Health' label", () => {
    render(<PlatformHealthCards summary={healthySummary} />);
    const ring = screen.getByTestId("score-ring");
    expect(ring.textContent).toContain("Overall Health");
  });

  it("renders 0% score when score is 0", () => {
    const zeroSummary = { ...healthySummary, overall_health_score: 0.0 };
    render(<PlatformHealthCards summary={zeroSummary} />);
    expect(screen.getByTestId("score-ring").textContent).toContain("0%");
  });
});

// ── ModuleHealthTable ──────────────────────────────────────────────────────────

describe("ModuleHealthTable", () => {
  it("renders the table container", () => {
    render(<ModuleHealthTable health={makeModuleHealth()} />);
    expect(screen.getByTestId("module-health-table")).not.toBeNull();
  });

  it("shows no-modules message when modules is empty", () => {
    const empty: ModuleHealth = { modules: [], total: 0, healthy: 0, warning: 0 };
    render(<ModuleHealthTable health={empty} />);
    expect(screen.getByTestId("no-modules")).not.toBeNull();
  });

  it("renders a row per module", () => {
    const health = makeModuleHealth();
    render(<ModuleHealthTable health={health} />);
    const rows = screen.getAllByTestId(/^module-row-/);
    expect(rows.length).toBe(3);
  });

  it("renders row for customers module", () => {
    render(<ModuleHealthTable health={makeModuleHealth()} />);
    expect(screen.getByTestId("module-row-customers")).not.toBeNull();
  });

  it("shows Healthy badge for healthy module", () => {
    render(<ModuleHealthTable health={makeModuleHealth()} />);
    const status = screen.getByTestId("module-status-customers");
    expect(status.textContent).toBe("Healthy");
  });

  it("shows Warning badge for unhealthy module", () => {
    render(<ModuleHealthTable health={makeModuleHealth()} />);
    const status = screen.getByTestId("module-status-billing");
    expect(status.textContent).toBe("Warning");
  });

  it("shows record count for customers", () => {
    render(<ModuleHealthTable health={makeModuleHealth()} />);
    const row = screen.getByTestId("module-row-customers");
    expect(row.textContent).toContain("500");
  });

  it("shows cache Yes for cache-enabled module", () => {
    render(<ModuleHealthTable health={makeModuleHealth()} />);
    const cache = screen.getByTestId("module-cache-customers");
    expect(cache.textContent).toBe("Yes");
  });

  it("shows cache No for non-cached module", () => {
    render(<ModuleHealthTable health={makeModuleHealth()} />);
    const cache = screen.getByTestId("module-cache-executive_dashboard");
    expect(cache.textContent).toBe("No");
  });

  it("shows warning badge when warnings > 0", () => {
    render(<ModuleHealthTable health={makeModuleHealth()} />);
    expect(screen.getByTestId("warning-badge")).not.toBeNull();
  });

  it("warning badge says '1 warning'", () => {
    render(<ModuleHealthTable health={makeModuleHealth()} />);
    expect(screen.getByTestId("warning-badge").textContent).toContain("1 warning");
  });

  it("no warning badge when warning = 0", () => {
    const health = makeModuleHealth({ warning: 0, healthy: 3 });
    render(<ModuleHealthTable health={health} />);
    expect(screen.queryByTestId("warning-badge")).toBeNull();
  });

  it("shows summary text '2 of 3 healthy'", () => {
    render(<ModuleHealthTable health={makeModuleHealth()} />);
    expect(screen.getByTestId("module-health-table").textContent).toContain("2 of 3 healthy");
  });

  it("uses MODULE_DISPLAY_NAMES for module name", () => {
    render(<ModuleHealthTable health={makeModuleHealth()} />);
    expect(screen.getByTestId("module-health-table").textContent).toContain("Customers");
  });

  it("plural warnings label", () => {
    const health = makeModuleHealth({ warning: 2, healthy: 1 });
    render(<ModuleHealthTable health={health} />);
    expect(screen.getByTestId("warning-badge").textContent).toContain("2 warnings");
  });
});

// ── CacheHealthPanel ───────────────────────────────────────────────────────────

describe("CacheHealthPanel", () => {
  it("renders the panel", () => {
    render(<CacheHealthPanel health={healthyCache} />);
    expect(screen.getByTestId("cache-health-panel")).not.toBeNull();
  });

  it("shows Available badge when redis_available=true", () => {
    render(<CacheHealthPanel health={healthyCache} />);
    expect(screen.getByTestId("redis-status").textContent).toBe("Available");
  });

  it("shows Unavailable badge when redis_available=false", () => {
    render(<CacheHealthPanel health={unhealthyCache} />);
    expect(screen.getByTestId("redis-status").textContent).toBe("Unavailable");
  });

  it("renders TTL config section", () => {
    render(<CacheHealthPanel health={healthyCache} />);
    expect(screen.getByTestId("ttl-config")).not.toBeNull();
  });

  it("shows TTL value for observability_summary", () => {
    render(<CacheHealthPanel health={healthyCache} />);
    const config = screen.getByTestId("ttl-config");
    expect(config.textContent).toContain("300s");
  });

  it("renders ratio bars", () => {
    render(<CacheHealthPanel health={healthyCache} />);
    const bars = screen.getAllByTestId("ratio-bar");
    expect(bars.length).toBe(2);
  });

  it("hit ratio bar has correct width style", () => {
    render(<CacheHealthPanel health={healthyCache} />);
    const bars = screen.getAllByTestId("ratio-bar");
    const hitBar = bars[0];
    expect(hitBar.getAttribute("style")).toContain("75%");
  });

  it("miss ratio bar has correct width style", () => {
    render(<CacheHealthPanel health={healthyCache} />);
    const bars = screen.getAllByTestId("ratio-bar");
    const missBar = bars[1];
    expect(missBar.getAttribute("style")).toContain("25%");
  });

  it("shows three TTL entries", () => {
    render(<CacheHealthPanel health={healthyCache} />);
    const config = screen.getByTestId("ttl-config");
    const entries = config.querySelectorAll("div");
    expect(entries.length).toBe(3);
  });

  it("empty TTL config renders empty section", () => {
    render(<CacheHealthPanel health={unhealthyCache} />);
    const config = screen.getByTestId("ttl-config");
    expect(config.querySelectorAll("div").length).toBe(0);
  });

  it("zero hit ratio shows 0% bar", () => {
    render(<CacheHealthPanel health={unhealthyCache} />);
    const bars = screen.getAllByTestId("ratio-bar");
    expect(bars[0].getAttribute("style")).toContain("0%");
  });
});

// ── DatabaseHealthPanel ────────────────────────────────────────────────────────

describe("DatabaseHealthPanel", () => {
  it("renders the panel", () => {
    render(<DatabaseHealthPanel health={healthyDb} />);
    expect(screen.getByTestId("database-health-panel")).not.toBeNull();
  });

  it("shows Connected badge when connection_ok=true", () => {
    render(<DatabaseHealthPanel health={healthyDb} />);
    expect(screen.getByTestId("connection-status").textContent).toBe("Connected");
  });

  it("shows Disconnected badge when connection_ok=false", () => {
    render(<DatabaseHealthPanel health={downDb} />);
    expect(screen.getByTestId("connection-status").textContent).toBe("Disconnected");
  });

  it("shows latency value", () => {
    render(<DatabaseHealthPanel health={healthyDb} />);
    expect(screen.getByTestId("latency-value").textContent).toContain("2.5ms");
  });

  it("shows N/A for negative latency", () => {
    render(<DatabaseHealthPanel health={downDb} />);
    expect(screen.getByTestId("latency-value").textContent).toBe("N/A");
  });

  it("shows table count", () => {
    render(<DatabaseHealthPanel health={healthyDb} />);
    expect(screen.getByTestId("table-count").textContent).toBe("42");
  });

  it("shows 0 table count when down", () => {
    render(<DatabaseHealthPanel health={downDb} />);
    expect(screen.getByTestId("table-count").textContent).toBe("0");
  });

  it("shows migration version", () => {
    render(<DatabaseHealthPanel health={healthyDb} />);
    expect(screen.getByTestId("migration-version").textContent).toContain("abc123def456");
  });

  it("shows dash for unknown migration version", () => {
    render(<DatabaseHealthPanel health={downDb} />);
    expect(screen.getByTestId("migration-version").textContent).toBe("—");
  });
});
