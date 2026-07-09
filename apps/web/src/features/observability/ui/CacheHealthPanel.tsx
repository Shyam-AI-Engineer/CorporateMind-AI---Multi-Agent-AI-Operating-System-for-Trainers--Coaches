"use client";

import React from "react";
import type { CacheHealth } from "@/features/observability/types";

interface CacheHealthPanelProps {
  health: CacheHealth;
}

function RatioBar({ ratio, color }: { ratio: number; color: string }) {
  const pct = Math.round(ratio * 100);
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-600 dark:text-gray-400">{pct}%</span>
      </div>
      <div className="h-2 rounded-full bg-gray-200 dark:bg-gray-700">
        <div
          data-testid="ratio-bar"
          className={`h-2 rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function CacheHealthPanel({ health }: CacheHealthPanelProps) {
  return (
    <div data-testid="cache-health-panel" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Redis Cache</h3>
        <span
          data-testid="redis-status"
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
            health.redis_available
              ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
              : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
          }`}
        >
          {health.redis_available ? "Available" : "Unavailable"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Hit Ratio</p>
          <RatioBar ratio={health.estimated_hit_ratio} color="bg-green-500" />
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Miss Ratio</p>
          <RatioBar ratio={health.estimated_miss_ratio} color="bg-yellow-400" />
        </div>
      </div>

      <div>
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">TTL Configuration</p>
        <div data-testid="ttl-config" className="space-y-1">
          {Object.entries(health.ttl_configuration).map(([key, ttl]) => (
            <div key={key} className="flex items-center justify-between text-xs">
              <span className="text-gray-600 dark:text-gray-400">{key.replace(/_/g, " ")}</span>
              <span className="font-mono text-gray-800 dark:text-gray-200">{ttl}s</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
