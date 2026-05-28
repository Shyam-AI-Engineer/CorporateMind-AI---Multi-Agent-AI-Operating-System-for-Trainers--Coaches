"use client";

import { useContacts } from "@/features/hr/api/use-contacts";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { SOURCE_TYPE_LABELS } from "@/features/hr/types";
import type { SourceType } from "@/features/hr/types";

interface ContactTableProps {
  onImport: () => void;
}

export function ContactTable({ onImport }: ContactTableProps) {
  const { data, isLoading, isError, refetch } = useContacts();

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <p className="text-sm text-muted-foreground">Failed to load contacts.</p>
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  const contacts = data?.items ?? [];

  if (contacts.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <p className="text-sm text-muted-foreground">
          No contactable HR contacts yet. Import your first one.
        </p>
        <Button size="sm" onClick={onImport}>
          Import contact
        </Button>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/40">
          <tr className="text-left text-xs text-muted-foreground">
            <th className="px-4 py-3 font-medium">Name</th>
            <th className="px-4 py-3 font-medium">Title</th>
            <th className="px-4 py-3 font-medium">Email</th>
            <th className="px-4 py-3 font-medium">Source</th>
            <th className="px-4 py-3 font-medium">Language</th>
            <th className="px-4 py-3 font-medium">Imported</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {contacts.map((c) => (
            <tr key={c.id} className="hover:bg-muted/30 transition-colors">
              <td className="px-4 py-3 font-medium">{c.full_name}</td>
              <td className="px-4 py-3 text-muted-foreground max-w-[200px] truncate">
                {c.title}
              </td>
              <td className="px-4 py-3 text-muted-foreground">{c.email}</td>
              <td className="px-4 py-3">
                <Badge variant="outline">
                  {SOURCE_TYPE_LABELS[c.source_type as SourceType] ?? c.source_type}
                </Badge>
              </td>
              <td className="px-4 py-3 text-muted-foreground">
                {c.preferred_language ?? "—"}
              </td>
              <td className="px-4 py-3 text-muted-foreground">
                {new Date(c.created_at).toLocaleDateString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
