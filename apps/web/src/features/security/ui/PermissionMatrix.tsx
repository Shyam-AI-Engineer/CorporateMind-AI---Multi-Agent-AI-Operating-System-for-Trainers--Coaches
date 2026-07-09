"use client";

import React from "react";
import type { PermissionOverview } from "@/features/security/types";

interface PermissionMatrixProps {
  overview: PermissionOverview;
}

export function PermissionMatrix({ overview }: PermissionMatrixProps) {
  if (overview.total_workspaces === 0) {
    return (
      <div data-testid="permission-matrix" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
          Permission Matrix
        </h3>
        <p data-testid="no-workspaces" className="text-sm text-gray-500 dark:text-gray-400">
          No workspaces found.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="permission-matrix" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Permission Matrix
        </h3>
        <span data-testid="workspace-count" className="text-xs text-gray-500 dark:text-gray-400">
          {overview.total_workspaces} workspace{overview.total_workspaces !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-xs">
          <thead>
            <tr className="border-b border-gray-100 dark:border-gray-800">
              <th className="pb-2 text-left font-medium text-gray-500 dark:text-gray-400">
                Workspace
              </th>
              <th className="pb-2 text-right font-medium text-gray-500 dark:text-gray-400">
                Owners
              </th>
              <th className="pb-2 text-right font-medium text-gray-500 dark:text-gray-400">
                Admins
              </th>
              <th className="pb-2 text-right font-medium text-gray-500 dark:text-gray-400">
                Members
              </th>
              <th className="pb-2 text-right font-medium text-gray-500 dark:text-gray-400">
                Viewers
              </th>
            </tr>
          </thead>
          <tbody>
            {overview.workspaces.map((ws) => (
              <tr
                key={ws.workspace_id}
                data-testid={`workspace-row-${ws.workspace_id}`}
                className="border-b border-gray-50 dark:border-gray-800/50 last:border-0"
              >
                <td className="py-1.5 text-left font-mono text-gray-700 dark:text-gray-300">
                  <span data-testid={`ws-id-${ws.workspace_id}`}>
                    {ws.workspace_id.slice(0, 8)}…
                  </span>
                </td>
                <td
                  data-testid={`ws-owners-${ws.workspace_id}`}
                  className="py-1.5 text-right tabular-nums text-gray-900 dark:text-gray-100"
                >
                  {ws.owners}
                </td>
                <td
                  data-testid={`ws-admins-${ws.workspace_id}`}
                  className="py-1.5 text-right tabular-nums text-gray-900 dark:text-gray-100"
                >
                  {ws.admins}
                </td>
                <td
                  data-testid={`ws-members-${ws.workspace_id}`}
                  className="py-1.5 text-right tabular-nums text-gray-900 dark:text-gray-100"
                >
                  {ws.members}
                </td>
                <td
                  data-testid={`ws-viewers-${ws.workspace_id}`}
                  className="py-1.5 text-right tabular-nums text-gray-900 dark:text-gray-100"
                >
                  {ws.viewers}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
