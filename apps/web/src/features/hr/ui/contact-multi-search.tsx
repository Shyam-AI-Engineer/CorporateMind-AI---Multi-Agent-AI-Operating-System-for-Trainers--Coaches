"use client";

import { useState, useMemo } from "react";
import { X, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import type { HRContact } from "@/features/hr/types";

interface ContactMultiSearchProps {
  contacts: HRContact[];
  selected: HRContact[];
  onAdd: (c: HRContact) => void;
  onRemove: (id: string) => void;
  onClearAll?: () => void;
}

export function ContactMultiSearch({
  contacts,
  selected,
  onAdd,
  onRemove,
  onClearAll,
}: ContactMultiSearchProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  const selectedIds = useMemo(() => new Set(selected.map((c) => c.id)), [selected]);

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return contacts
      .filter(
        (c) =>
          !selectedIds.has(c.id) &&
          (q.length === 0 ||
            c.full_name.toLowerCase().includes(q) ||
            c.email.toLowerCase().includes(q))
      )
      .slice(0, 8);
  }, [contacts, query, selectedIds]);

  return (
    <div className="space-y-2">
      {/* Selected contact chips */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5 rounded-md border bg-muted/20 p-2 max-h-32 overflow-y-auto">
          {selected.map((c) => (
            <span
              key={c.id}
              className="inline-flex items-center gap-1 rounded-full border bg-background px-2 py-0.5 text-xs"
            >
              <span className="truncate max-w-[140px]">{c.full_name}</span>
              {!c.is_contactable && (
                <Badge variant="destructive" className="text-[9px] px-1 py-0">!</Badge>
              )}
              <button
                type="button"
                onClick={() => onRemove(c.id)}
                className="shrink-0 text-muted-foreground hover:text-foreground"
                aria-label={`Remove ${c.full_name}`}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
          {onClearAll && (
            <button
              type="button"
              onClick={onClearAll}
              className="text-xs text-muted-foreground hover:text-destructive underline-offset-2 hover:underline self-center"
            >
              Clear all
            </button>
          )}
        </div>
      )}

      {/* Search to add more */}
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
        <Input
          className="pl-8"
          placeholder="Search contacts to add…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 160)}
          autoComplete="off"
        />
        {open && filtered.length > 0 && (
          <ul className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md text-sm overflow-hidden max-h-52 overflow-y-auto">
            {filtered.map((c) => (
              <li
                key={c.id}
                onMouseDown={() => {
                  onAdd(c);
                  setQuery("");
                  // Keep the dropdown open so the user can keep adding
                }}
                className="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-muted gap-2"
              >
                <div className="min-w-0">
                  <p className="font-medium truncate">{c.full_name}</p>
                  <p className="text-xs text-muted-foreground truncate">
                    {c.title} · {c.email}
                  </p>
                </div>
                {!c.is_contactable && (
                  <Badge variant="destructive" className="shrink-0 text-[10px]">
                    Non-contactable
                  </Badge>
                )}
              </li>
            ))}
          </ul>
        )}
        {open && query.length > 0 && filtered.length === 0 && (
          <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md px-3 py-2 text-sm text-muted-foreground">
            No contacts match &ldquo;{query}&rdquo;
          </div>
        )}
      </div>
    </div>
  );
}
