"use client";

import { AlertCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { usePortfolio, useCoverage } from "@/features/analytics/api/use-analytics";

// ── helpers ───────────────────────────────────────────────────────────────────

function pct(value: number): string {
  return `${value.toFixed(1)}%`;
}

function SummaryCard({
  testId,
  label,
  value,
}: {
  testId: string;
  label: string;
  value: string | number;
}) {
  return (
    <Card data-testid={testId}>
      <CardHeader className="pb-1">
        <CardTitle className="text-xs font-medium text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-bold">{value}</p>
      </CardContent>
    </Card>
  );
}

// ── panel ─────────────────────────────────────────────────────────────────────

export function PortfolioCoveragePanel({
  workspaceId,
}: {
  workspaceId: string;
}) {
  const portfolio = usePortfolio(workspaceId);
  const coverage = useCoverage(workspaceId);

  const isLoading = portfolio.isLoading || coverage.isLoading;
  const p = portfolio.data;
  const c = coverage.data;

  return (
    <div
      data-testid="portfolio-coverage-panel"
      className="space-y-6"
    >
      {/* ── Loading skeletons ──────────────────────────────────────────────── */}
      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} data-testid="skeleton" className="h-24 w-full" />
          ))}
        </div>
      )}

      {/* ── Portfolio error ────────────────────────────────────────────────── */}
      {portfolio.isError && (
        <div
          data-testid="portfolio-error"
          className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to load portfolio data. Please try again.
        </div>
      )}

      {/* ── Coverage error ─────────────────────────────────────────────────── */}
      {coverage.isError && (
        <div
          data-testid="coverage-error"
          className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to load coverage data. Please try again.
        </div>
      )}

      {/* ── Insufficient data ──────────────────────────────────────────────── */}
      {!portfolio.isLoading && !portfolio.isError && p?.insufficient_data && (
        <div
          data-testid="portfolio-insufficient"
          className="rounded-md border p-6 text-center text-sm text-muted-foreground"
        >
          No recommendation history available. Generate recommendations to unlock
          portfolio analysis.
        </div>
      )}

      {/* ── Section 1: Portfolio Summary cards ────────────────────────────── */}
      {!portfolio.isLoading && !portfolio.isError && p && !p.insufficient_data && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <SummaryCard
            testId="card-total-recommendations"
            label="Total Recommendations"
            value={p.total_recommendations}
          />
          <SummaryCard
            testId="card-dominant-type"
            label="Dominant Type"
            value={p.dominant_type ?? "—"}
          />
          <SummaryCard
            testId="card-least-used-type"
            label="Least Used Type"
            value={p.least_used_type ?? "—"}
          />
          <SummaryCard
            testId="card-diversity-index"
            label="Diversity Index"
            value={pct(p.portfolio_balance.diversity_index)}
          />
        </div>
      )}

      {/* ── Section 2: Recommendation Distribution ────────────────────────── */}
      {!portfolio.isLoading && !portfolio.isError && p && !p.insufficient_data && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Recommendation Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            {p.recommendation_types.length === 0 ? (
              <p
                data-testid="distribution-table-empty"
                className="text-sm text-muted-foreground"
              >
                Need more recommendation history to evaluate distribution.
              </p>
            ) : (
              <div
                data-testid="distribution-table"
                className="overflow-x-auto"
              >
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs text-muted-foreground">
                      <th className="pb-2 text-left font-medium">Type</th>
                      <th className="pb-2 text-right font-medium">Count</th>
                      <th className="pb-2 text-right font-medium">%</th>
                      <th className="pb-2 text-right font-medium">Acted Rate</th>
                      <th className="pb-2 text-right font-medium">Success Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {p.recommendation_types.map((item) => (
                      <tr
                        key={item.recommendation_type}
                        data-testid={`distribution-row-${item.recommendation_type}`}
                        className="border-b last:border-0"
                      >
                        <td className="py-2 capitalize">{item.recommendation_type}</td>
                        <td className="py-2 text-right">{item.count}</td>
                        <td className="py-2 text-right">{pct(item.percentage)}</td>
                        <td className="py-2 text-right">{pct(item.acted_rate)}</td>
                        <td className="py-2 text-right">{pct(item.success_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Section 3: Portfolio Balance ───────────────────────────────────── */}
      {!portfolio.isLoading && !portfolio.isError && p && !p.insufficient_data && (
        <Card data-testid="portfolio-balance">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Portfolio Balance</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Balance Rating</span>
              <span
                data-testid="balance-rating"
                className="rounded-full px-2 py-0.5 text-xs font-medium capitalize"
              >
                {p.portfolio_balance.balance_rating}
              </span>
            </div>
            <div className="space-y-1">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>Diversity Index</span>
                <span>{pct(p.portfolio_balance.diversity_index)}</span>
              </div>
              <div
                data-testid="diversity-gauge"
                className="h-2 w-full overflow-hidden rounded-full bg-muted"
              >
                <div
                  className="h-full rounded-full bg-primary transition-all"
                  style={{ width: `${Math.min(p.portfolio_balance.diversity_index, 100)}%` }}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Section 4: Coverage Table ──────────────────────────────────────── */}
      {!coverage.isLoading && !coverage.isError && c && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Coverage</CardTitle>
          </CardHeader>
          <CardContent>
            {c.coverage.length === 0 ? (
              <p
                data-testid="coverage-table-empty"
                className="text-sm text-muted-foreground"
              >
                No recommendation history available.
              </p>
            ) : (
              <div
                data-testid="coverage-table"
                className="overflow-x-auto"
              >
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs text-muted-foreground">
                      <th className="pb-2 text-left font-medium">Type</th>
                      <th className="pb-2 text-center font-medium">Present</th>
                      <th className="pb-2 text-right font-medium">Count</th>
                      <th className="pb-2 text-right font-medium">Last Generated</th>
                      <th className="pb-2 text-right font-medium">Days Since</th>
                      <th className="pb-2 text-right font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.coverage.map((item) => {
                      const isStale =
                        item.days_since_last_generated !== null &&
                        item.days_since_last_generated > 30;
                      const status = !item.present
                        ? "missing"
                        : isStale
                          ? "stale"
                          : "healthy";
                      return (
                        <tr
                          key={item.recommendation_type}
                          data-testid={`coverage-row-${item.recommendation_type}`}
                          className="border-b last:border-0"
                        >
                          <td className="py-2 capitalize">{item.recommendation_type}</td>
                          <td className="py-2 text-center">
                            {item.present ? "Yes" : "No"}
                          </td>
                          <td className="py-2 text-right">{item.count}</td>
                          <td className="py-2 text-right">
                            {item.last_generated_at ?? "—"}
                          </td>
                          <td className="py-2 text-right">
                            {item.days_since_last_generated ?? "—"}
                          </td>
                          <td className="py-2 text-right">
                            <span
                              data-testid={`coverage-status-${item.recommendation_type}`}
                              className="capitalize"
                            >
                              {status}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Section 5: Missing / Stale Types ──────────────────────────────── */}
      {!coverage.isLoading && !coverage.isError && c && (
        <div className="grid gap-4 md:grid-cols-2">
          <Card data-testid="missing-types-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Missing Recommendation Types</CardTitle>
            </CardHeader>
            <CardContent>
              {c.missing_types.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  All recommendation types have been generated.
                </p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {c.missing_types.map((t) => (
                    <li
                      key={t}
                      data-testid={`missing-type-${t}`}
                      className="capitalize text-destructive"
                    >
                      {t}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card data-testid="stale-types-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Stale Recommendation Types</CardTitle>
            </CardHeader>
            <CardContent>
              {c.stale_types.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No stale recommendation types.
                </p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {c.stale_types.map((t) => (
                    <li
                      key={t}
                      data-testid={`stale-type-${t}`}
                      className="capitalize text-yellow-600"
                    >
                      {t}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
