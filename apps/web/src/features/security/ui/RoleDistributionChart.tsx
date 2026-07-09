"use client";

import React from "react";
import type { RoleDistribution } from "@/features/security/types";
import { ROLE_LABELS } from "@/features/security/types";

interface RoleDistributionChartProps {
  distribution: RoleDistribution;
}

const ROLE_COLORS: Record<string, string> = {
  owner: "bg-purple-500",
  admin: "bg-blue-500",
  member: "bg-green-500",
  viewer: "bg-gray-400",
};

export function RoleDistributionChart({ distribution }: RoleDistributionChartProps) {
  const total = distribution.total_members;

  return (
    <div data-testid="role-distribution-chart" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Role Distribution
        </h3>
        <span data-testid="total-members" className="text-xs text-gray-500 dark:text-gray-400">
          {total} member{total !== 1 ? "s" : ""}
        </span>
      </div>

      {total === 0 ? (
        <p data-testid="no-members" className="text-sm text-gray-500 dark:text-gray-400">
          No active workspace members found.
        </p>
      ) : (
        <>
          {/* Stacked bar */}
          <div data-testid="role-bar" className="flex h-3 w-full overflow-hidden rounded-full mb-4">
            {distribution.roles.map((rc) => {
              const widthPct = total > 0 ? (rc.count / total) * 100 : 0;
              return (
                <div
                  key={rc.role}
                  data-testid={`bar-segment-${rc.role}`}
                  className={`${ROLE_COLORS[rc.role] ?? "bg-gray-300"}`}
                  style={{ width: `${widthPct}%` }}
                  title={`${ROLE_LABELS[rc.role] ?? rc.role}: ${rc.count}`}
                />
              );
            })}
          </div>

          {/* Legend */}
          <div className="space-y-2">
            {distribution.roles.map((rc) => (
              <div
                key={rc.role}
                data-testid={`role-row-${rc.role}`}
                className="flex items-center justify-between"
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-block h-2 w-2 rounded-full ${ROLE_COLORS[rc.role] ?? "bg-gray-300"}`}
                  />
                  <span className="text-xs text-gray-700 dark:text-gray-300">
                    {ROLE_LABELS[rc.role] ?? rc.role}
                  </span>
                </div>
                <span
                  data-testid={`role-count-${rc.role}`}
                  className="text-xs font-medium tabular-nums text-gray-900 dark:text-gray-100"
                >
                  {rc.count}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
