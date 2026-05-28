"use client";

import { useState, useMemo } from "react";
import { CheckCircle2, XCircle, X } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { useGenerateOutreach, useSendMessage } from "@/features/outreach/api/use-outreach";
import { useContacts } from "@/features/hr/api/use-contacts";
import type { HRContact } from "@/features/hr/types";
import type { OutboundMessage, OutreachChannel, SendMessageResponse } from "@/features/outreach/types";
import { OUTREACH_CHANNELS, CHANNEL_LABELS, CHANNEL_EMOJI, LIVE_OUTREACH_CHANNELS } from "@/features/outreach/types";

type Step = "compose" | "preview" | "result";

// ── Contact search/select ────────────────────────────────────────────────────

interface ContactSearchProps {
  contacts: HRContact[];
  selected: HRContact | null;
  onSelect: (c: HRContact) => void;
  onClear: () => void;
}

function ContactSearch({ contacts, selected, onSelect, onClear }: ContactSearchProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    const list = q.length === 0
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
            <Badge variant="destructive" className="ml-2 text-[10px]">Non-contactable</Badge>
          )}
        </div>
        <button
          type="button"
          onClick={() => { onClear(); setQuery(""); }}
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
        placeholder="Search by name or email…"
        value={query}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 160)}
        autoComplete="off"
      />
      {open && filtered.length > 0 && (
        <ul className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md text-sm overflow-hidden max-h-52 overflow-y-auto">
          {filtered.map((c) => (
            <li
              key={c.id}
              onMouseDown={() => { onSelect(c); setOpen(false); setQuery(""); }}
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

// ── Channel picker ───────────────────────────────────────────────────────────

interface ChannelPickerProps {
  value: OutreachChannel;
  onChange: (ch: OutreachChannel) => void;
}

function ChannelPicker({ value, onChange }: ChannelPickerProps) {
  return (
    <div className="flex gap-2">
      {OUTREACH_CHANNELS.map((ch) => {
        const live = LIVE_OUTREACH_CHANNELS.has(ch);
        return (
          <button
            key={ch}
            type="button"
            disabled={!live}
            onClick={() => live && onChange(ch)}
            title={live ? undefined : `${CHANNEL_LABELS[ch]} — coming soon`}
            className={`relative flex-1 rounded-md border px-3 py-2 text-xs font-medium transition-colors ${
              !live
                ? "cursor-not-allowed opacity-40 text-muted-foreground"
                : value === ch
                ? "border-primary bg-primary/5 text-primary"
                : "text-muted-foreground hover:bg-muted"
            }`}
          >
            {CHANNEL_EMOJI[ch]} {CHANNEL_LABELS[ch]}
            {!live && (
              <span className="ml-1 rounded bg-muted px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wider">
                soon
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ── Main dialog ───────────────────────────────────────────────────────────────

interface ComposeOutreachDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ComposeOutreachDialog({ open, onOpenChange }: ComposeOutreachDialogProps) {
  const [step, setStep] = useState<Step>("compose");
  const [selectedContact, setSelectedContact] = useState<HRContact | null>(null);
  const [channel, setChannel] = useState<OutreachChannel>("email");
  const [draft, setDraft] = useState<OutboundMessage | null>(null);
  const [sendResult, setSendResult] = useState<SendMessageResponse | null>(null);

  const { data: contactsData, isLoading: contactsLoading } = useContacts();
  const contacts = contactsData?.items ?? [];

  const {
    mutate: generate,
    isPending: generating,
    error: generateError,
    reset: resetGenerate,
  } = useGenerateOutreach();

  const {
    mutate: send,
    isPending: sending,
    reset: resetSend,
  } = useSendMessage();

  function handleGenerate() {
    if (!selectedContact) return;
    generate(
      { contact_id: selectedContact.id, channel },
      {
        onSuccess: (msg) => {
          setDraft(msg);
          setStep("preview");
        },
      }
    );
  }

  function handleSend() {
    if (!draft) return;
    send(draft.id, {
      onSuccess: (result) => {
        setSendResult(result);
        setStep("result");
      },
    });
  }

  function handleClose(isOpen: boolean) {
    if (!isOpen) {
      setStep("compose");
      setSelectedContact(null);
      setChannel("email");
      setDraft(null);
      setSendResult(null);
      resetGenerate();
      resetSend();
    }
    onOpenChange(isOpen);
  }

  function handleComposeAnother() {
    setStep("compose");
    setSelectedContact(null);
    setDraft(null);
    setSendResult(null);
    resetGenerate();
    resetSend();
  }

  const titles: Record<Step, string> = {
    compose: "Compose Outreach",
    preview: "Preview Message",
    result: sendResult?.status === "queued" ? "Message Queued" : "Send Blocked",
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{titles[step]}</DialogTitle>
        </DialogHeader>

        {/* ── Step: Compose ── */}
        {step === "compose" && (
          <div className="space-y-4 py-1">
            <p className="text-xs text-muted-foreground">
              Select a contact and channel — the AI will generate personalised copy from
              your trainer profile and the contact&apos;s role and industry.
            </p>

            <div className="space-y-1.5">
              <Label>Contact</Label>
              {contactsLoading ? (
                <div className="h-9 rounded-md border bg-muted/40 animate-pulse" />
              ) : (
                <ContactSearch
                  contacts={contacts}
                  selected={selectedContact}
                  onSelect={setSelectedContact}
                  onClear={() => setSelectedContact(null)}
                />
              )}
              {selectedContact && !selectedContact.is_contactable && (
                <p className="text-xs text-destructive">
                  This contact is flagged non-contactable — compliance will block the send.
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label>Channel</Label>
              <ChannelPicker value={channel} onChange={setChannel} />
            </div>

            {generateError && (
              <p className="text-xs text-destructive">
                Generation failed — please try again.
              </p>
            )}

            <DialogFooter>
              <Button variant="outline" onClick={() => handleClose(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleGenerate}
                disabled={!selectedContact || generating}
              >
                {generating ? "Generating…" : "Generate AI Copy"}
              </Button>
            </DialogFooter>
          </div>
        )}

        {/* ── Step: Preview ── */}
        {step === "preview" && draft && (
          <div className="space-y-4 py-1">
            <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
              <span className="font-medium text-foreground">{selectedContact?.full_name}</span>
              <span>·</span>
              <Badge variant="secondary">
                {CHANNEL_EMOJI[channel]} {CHANNEL_LABELS[channel]}
              </Badge>
              {draft.prompt_version && (
                <>
                  <span>·</span>
                  <span className="font-mono">{draft.prompt_version}</span>
                </>
              )}
            </div>

            {draft.subject && (
              <div className="space-y-1">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Subject
                </p>
                <p className="text-sm font-medium">{draft.subject}</p>
              </div>
            )}

            <div className="space-y-1">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Body
              </p>
              <div className="rounded-md border bg-muted/30 p-3 max-h-52 overflow-y-auto">
                <p className="text-sm whitespace-pre-wrap leading-relaxed">{draft.body}</p>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setStep("compose")}>
                ← Start Over
              </Button>
              <Button onClick={handleSend} disabled={sending}>
                {sending ? "Sending…" : "Send Message"}
              </Button>
            </DialogFooter>
          </div>
        )}

        {/* ── Step: Result ── */}
        {step === "result" && sendResult && (
          <div className="space-y-4 py-2">
            {sendResult.status === "queued" ? (
              <div className="flex items-start gap-3 rounded-md border border-green-200 bg-green-50 p-4">
                <CheckCircle2 className="h-5 w-5 text-green-600 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-green-800">
                    Message queued for delivery
                  </p>
                  <p className="text-xs text-green-700 mt-0.5">
                    Will be sent to <strong>{selectedContact?.full_name}</strong> via{" "}
                    {CHANNEL_LABELS[channel]}.
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-4">
                <XCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-destructive">
                    Send blocked by compliance
                  </p>
                  {sendResult.compliance_reason && (
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {sendResult.compliance_reason}
                    </p>
                  )}
                </div>
              </div>
            )}

            <DialogFooter>
              <Button variant="outline" onClick={handleComposeAnother}>
                Compose Another
              </Button>
              <Button onClick={() => handleClose(false)}>Done</Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
