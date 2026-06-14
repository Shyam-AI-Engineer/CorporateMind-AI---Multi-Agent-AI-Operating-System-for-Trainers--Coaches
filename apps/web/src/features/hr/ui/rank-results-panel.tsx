"use client";

import { useState, useMemo } from "react";
import { AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { RankedContact } from "@/features/hr/types";

export interface RankResultsPanelProps {
  rankings: RankedContact[];
  onSelectionChange: (contactIds: string[]) => void;
}

type Threshold = 0 | 7 | 8 | 9;

const THRESHOLDS: { label: string; value: Threshold }[] = [
  { label: "All", value: 0 },
  { label: "7+", value: 7 },
  { label: "8+", value: 8 },
  { label: "9+", value: 9 },
];

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round((score / 10) * 100);
  const color =
    score >= 7 ? "bg-green-500" : score >= 4 ? "bg-amber-400" : "bg-red-400";
  const textColor =
    score >= 7
      ? "text-green-600"
      : score >= 4
        ? "text-amber-500"
        : "text-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`tabular-nums text-xs font-medium ${textColor}`}>
        {score}/10
      </span>
    </div>
  );
}

export function RankResultsPanel({
  rankings,
  onSelectionChange,
}: RankResultsPanelProps) {
  const [threshold, setThreshold] = useState<Threshold>(7);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Stats across ALL rankings regardless of threshold.
  const qualified = rankings.filter((r) => r.score >= 7).length;
  const medium = rankings.filter((r) => r.score >= 4 && r.score < 7).length;
  const poor = rankings.filter((r) => r.score < 4).length;

  const visible = useMemo(
    () => rankings.filter((r) => threshold === 0 || r.score >= threshold),
    [rankings, threshold],
  );

  const visibleContactable = useMemo(
    () => visible.filter((r) => r.contact.is_contactable),
    [visible],
  );

  const allVisibleSelected =
    visibleContactable.length > 0 &&
    visibleContactable.every((r) => selected.has(r.contact_id));

  function toggleRow(contactId: string) {
    const next = new Set(selected);
    if (next.has(contactId)) {
      next.delete(contactId);
    } else {
      next.add(contactId);
    }
    setSelected(next);
    onSelectionChange(Array.from(next));
  }

  function toggleAll() {
    const next = new Set(selected);
    if (allVisibleSelected) {
      visibleContactable.forEach((r) => next.delete(r.contact_id));
    } else {
      visibleContactable.forEach((r) => next.add(r.contact_id));
    }
    setSelected(next);
    onSelectionChange(Array.from(next));
  }

  if (rankings.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-10 text-center">
        <p className="text-sm text-muted-foreground">No contacts were ranked.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Score summary counts */}
      <div className="flex gap-5 text-xs">
        <span>
          <span className="font-semibold text-green-600">{qualified}</span>{" "}
          <span className="text-muted-foreground">Qualified (7+)</span>
        </span>
        <span>
          <span className="font-semibold text-amber-500">{medium}</span>{" "}
          <span className="text-muted-foreground">Medium (4–6)</span>
        </span>
        <span>
          <span className="font-semibold text-red-500">{poor}</span>{" "}
          <span className="text-muted-foreground">Poor (0–3)</span>
        </span>
      </div>

      {/* Threshold filter + selection counter */}
      <div className="flex items-center gap-1">
        <span className="text-xs text-muted-foreground mr-1">Show:</span>
        {THRESHOLDS.map((t) => (
          <button
            key={t.value}
            type="button"
            onClick={() => setThreshold(t.value)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              threshold === t.value
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-muted/80"
            }`}
          >
            {t.label}
          </button>
        ))}
        <span className="ml-auto text-xs text-muted-foreground">
          {selected.size > 0 ? `${selected.size} selected` : ""}
        </span>
      </div>

      {/* Results table */}
      {visible.length === 0 ? (
        <p className="py-6 text-center text-xs text-muted-foreground">
          No contacts at this score threshold.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border max-h-72 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 border-b bg-muted/40">
              <tr className="text-left text-xs text-muted-foreground">
                <th className="px-3 py-2.5 w-8">
                  <input
                    type="checkbox"
                    aria-label="Select all"
                    checked={allVisibleSelected}
                    onChange={toggleAll}
                    className="rounded"
                  />
                </th>
                <th className="px-3 py-2.5 font-medium">Name</th>
                <th className="px-3 py-2.5 font-medium">Title</th>
                <th className="px-3 py-2.5 font-medium">Score</th>
                <th className="px-3 py-2.5 font-medium hidden sm:table-cell">
                  Reason
                </th>
                <th className="px-3 py-2.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {visible.map((r) => {
                const isContactable = r.contact.is_contactable;
                const isChecked = selected.has(r.contact_id);
                return (
                  <tr
                    key={r.contact_id}
                    className={`transition-colors ${
                      isContactable ? "hover:bg-muted/30" : "opacity-60"
                    } ${isChecked ? "bg-primary/5" : ""}`}
                  >
                    <td className="px-3 py-2.5">
                      <input
                        type="checkbox"
                        aria-label={r.contact.full_name}
                        disabled={!isContactable}
                        checked={isChecked}
                        onChange={() => toggleRow(r.contact_id)}
                        className="rounded disabled:cursor-not-allowed"
                        title={
                          !isContactable
                            ? "No opt-in record — cannot be sent to"
                            : undefined
                        }
                      />
                    </td>
                    <td className="px-3 py-2.5">
                      <p className="font-medium truncate max-w-[140px]">
                        {r.contact.full_name}
                      </p>
                    </td>
                    <td className="px-3 py-2.5 text-muted-foreground truncate max-w-[120px]">
                      {r.contact.title}
                    </td>
                    <td className="px-3 py-2.5">
                      <ScoreBar score={r.score} />
                    </td>
                    <td className="px-3 py-2.5 text-xs text-muted-foreground hidden sm:table-cell">
                      <span className="line-clamp-2">{r.reason}</span>
                    </td>
                    <td className="px-3 py-2.5">
                      {isContactable ? (
                        <Badge variant="outline" className="text-[10px]">
                          Opt-in ✓
                        </Badge>
                      ) : (
                        <span
                          title="No opt-in record — cannot be sent to"
                          className="inline-flex items-center gap-1 text-[10px] text-amber-600"
                        >
                          <AlertTriangle className="h-3 w-3" />
                          No opt-in
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
