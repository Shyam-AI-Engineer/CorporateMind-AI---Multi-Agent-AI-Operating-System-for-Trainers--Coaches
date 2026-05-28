"use client";

import { useState } from "react";
import { Send, MessageSquarePlus, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ComposeOutreachDialog } from "@/features/outreach/ui/compose-outreach-dialog";

export default function OutreachPage() {
  const [composing, setComposing] = useState(false);

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Outreach</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            AI-personalised single-contact messages — pick a contact, choose a channel, send.
          </p>
        </div>
        <Button onClick={() => setComposing(true)} className="gap-2">
          <MessageSquarePlus className="h-4 w-4" />
          Compose
        </Button>
      </div>

      {/* How it works */}
      <div className="grid grid-cols-3 gap-4">
        {[
          {
            step: "1",
            title: "Select contact & channel",
            description: "Pick any HR contact from your database and choose email, WhatsApp, or Telegram.",
          },
          {
            step: "2",
            title: "AI generates the copy",
            description:
              "The AI uses your trainer profile — niche, topics, tone, USP — plus the contact's role and industry.",
          },
          {
            step: "3",
            title: "Review and send",
            description:
              "Preview the subject and body, then queue for delivery. Compliance checks run automatically before send.",
          },
        ].map(({ step, title, description }) => (
          <div key={step} className="rounded-lg border p-4 space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="h-5 w-5 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center">
                {step}
              </span>
              <p className="text-sm font-medium">{title}</p>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
          </div>
        ))}
      </div>

      {/* Empty CTA */}
      <div className="rounded-lg border border-dashed p-10 flex flex-col items-center justify-center text-center gap-4">
        <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
          <Send className="h-5 w-5 text-muted-foreground" />
        </div>
        <div className="space-y-1">
          <p className="text-sm font-medium">No messages composed yet</p>
          <p className="text-xs text-muted-foreground max-w-xs">
            Use the Campaigns module for bulk sends. Outreach is for individual, high-touch messages.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setComposing(true)} className="gap-2">
          <Sparkles className="h-3.5 w-3.5" />
          Compose your first message
        </Button>
      </div>

      <ComposeOutreachDialog open={composing} onOpenChange={setComposing} />
    </div>
  );
}
