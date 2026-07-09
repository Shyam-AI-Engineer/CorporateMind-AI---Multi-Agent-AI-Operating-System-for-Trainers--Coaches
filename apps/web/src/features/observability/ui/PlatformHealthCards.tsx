"use client";

import React from "react";
import type { PlatformSummary } from "@/features/observability/types";

interface HealthCardProps {
  label: string;
  value: string;
  status: "healthy" | "degraded" | "down" | "ok" | "error";
}

function HealthCard({ label, value, status }: HealthCardProps) {
  const isGood = status === "healthy" || status === "ok";
  const isWarn = status === "degraded";
  const borderCls = isGood
    ? "border-green-200 dark:border-green-800"
    : isWarn
    ? "border-yellow-200 dark:border-yellow-800"
    : "border-red-200 dark:border-red-800";
  const dotCls = isGood
    ? "bg-green-500"
    : isWarn
    ? "bg-yellow-500"
    : "bg-red-500";

  return (
    <div
      data-testid="health-card"
      className={`rounded-lg border-2 bg-white dark:bg-gray-900 p-4 ${borderCls}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-600 dark:text-gray-400">{label}</span>
        <span data-testid="health-dot" className={`h-2.5 w-2.5 rounded-full ${dotCls}`} />
      </div>
      <p data-testid="health-value" className="mt-2 text-lg font-semibold text-gray-900 dark:text-gray-100">
        {value}
      </p>
    </div>
  );
}

interface ScoreRingProps {
  score: number;
}

function ScoreRing({ score }: ScoreRingProps) {
  const pct = Math.round(score * 100);
  const color = pct >= 90 ? "text-green-600" : pct >= 70 ? "text-yellow-500" : "text-red-500";
  return (
    <div data-testid="score-ring" className="flex flex-col items-center justify-center rounded-lg border-2 border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
      <span className={`text-4xl font-bold ${color}`}>{pct}%</span>
      <span className="mt-1 text-sm font-medium text-gray-600 dark:text-gray-400">Overall Health</span>
    </div>
  );
}

interface PlatformHealthCardsProps {
  summary: PlatformSummary;
}

export function PlatformHealthCards({ summary }: PlatformHealthCardsProps) {
  return (
    <div data-testid="platform-health-cards" className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
      <ScoreRing score={summary.overall_health_score} />
      <HealthCard label="API" value={summary.api_health} status={summary.api_health} />
      <HealthCard label="Database" value={summary.database_health} status={summary.database_health} />
      <HealthCard label="Cache" value={summary.cache_health} status={summary.cache_health} />
      <HealthCard label="Storage" value={summary.storage_health} status={summary.storage_health} />
    </div>
  );
}
