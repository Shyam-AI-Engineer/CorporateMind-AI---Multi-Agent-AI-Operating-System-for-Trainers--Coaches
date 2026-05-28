"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ContactTable } from "@/features/hr/ui/contact-table";
import { ImportContactDialog } from "@/features/hr/ui/import-contact-dialog";
import { RankContactsDialog } from "@/features/hr/ui/rank-contacts-dialog";
import { useContacts } from "@/features/hr/api/use-contacts";

export default function HRPage() {
  const [importOpen, setImportOpen] = useState(false);
  const [rankOpen, setRankOpen] = useState(false);
  const { data } = useContacts();
  const contacts = data?.items ?? [];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">HR Contacts</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Opted-in HR decision-makers available for outreach.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => setRankOpen(true)}
            disabled={contacts.length === 0}
          >
            Rank contacts
          </Button>
          <Button onClick={() => setImportOpen(true)}>Import contact</Button>
        </div>
      </div>

      <ContactTable onImport={() => setImportOpen(true)} />

      <ImportContactDialog open={importOpen} onOpenChange={setImportOpen} />

      <RankContactsDialog
        contacts={contacts}
        open={rankOpen}
        onOpenChange={setRankOpen}
      />
    </div>
  );
}
