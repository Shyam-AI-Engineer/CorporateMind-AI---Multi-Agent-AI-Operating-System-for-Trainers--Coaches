"use client";

import { useState, useMemo } from "react";
import { X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import type { HRContact } from "@/features/hr/types";

interface ContactSearchProps {
  contacts: HRContact[];
  selected: HRContact | null;
  onSelect: (c: HRContact) => void;
  onClear: () => void;
  placeholder?: string;
}

export function ContactSearch({
  contacts,
  selected,
  onSelect,
  onClear,
  placeholder = "Search by name or email…",
}: ContactSearchProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    const list =
      q.length === 0
        ? contacts
        : contacts.filter(
            (c) =>
              c.full_name.toLowerCase().includes(q) ||
              c.email.toLowerCase().includes(q)
          );
    return list.slice(0, 8);
  }, [contacts, query]);

  if (selected) {
    return (
      <div className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm bg-muted/30">
        <div className="flex-1 min-w-0">
          <span className="font-medium">{selected.full_name}</span>
          <span className="text-muted-foreground"> · {selected.email}</span>
          {!selected.is_contactable && (
            <Badge variant="destructive" className="ml-2 text-[10px]">
              Non-contactable
            </Badge>
          )}
        </div>
        <button
          type="button"
          onClick={() => {
            onClear();
            setQuery("");
          }}
          className="shrink-0 text-muted-foreground hover:text-foreground"
          aria-label="Clear contact"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div className="relative">
      <Input
        placeholder={placeholder}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        // Delay matches mouseDown timing so dropdown clicks register before blur closes the list
        onBlur={() => setTimeout(() => setOpen(false), 160)}
        autoComplete="off"
      />
      {open && filtered.length > 0 && (
        <ul className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md text-sm overflow-hidden max-h-52 overflow-y-auto">
          {filtered.map((c) => (
            <li
              key={c.id}
              onMouseDown={() => {
                onSelect(c);
                setOpen(false);
                setQuery("");
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
  );
}
