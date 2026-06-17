"use client";

import { useState } from "react";
import { Copy, RefreshCw, Check, AlertCircle, Webhook } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useBookingWebhook,
  useRegenerateBookingSecret,
} from "@/features/workspace/api/use-workspace-settings";

export function IntegrationsPanel() {
  const { data, isLoading, isError } = useBookingWebhook();
  const regenerate = useRegenerateBookingSecret();

  const [copiedField, setCopiedField] = useState<"url" | "secret" | null>(null);
  const [confirmRegenerate, setConfirmRegenerate] = useState(false);

  async function copy(text: string, field: "url" | "secret") {
    await navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  }

  async function handleRegenerate() {
    if (!confirmRegenerate) {
      setConfirmRegenerate(true);
      return;
    }
    setConfirmRegenerate(false);
    await regenerate.mutateAsync();
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex items-center gap-2 text-sm text-destructive">
        <AlertCircle className="h-4 w-4 shrink-0" />
        Failed to load webhook settings.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Webhook className="h-5 w-5 text-primary" />
        <h2 className="text-base font-semibold">Booking Webhook</h2>
      </div>

      <p className="text-sm text-muted-foreground">
        Paste your webhook URL and secret into your booking tool (Calendly, Cal.com,
        Tidycal, etc.) to automatically sync meetings with your CRM pipeline.
      </p>

      {/* Webhook URL */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-muted-foreground">
          Webhook URL
        </label>
        <div className="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2">
          <code className="min-w-0 flex-1 truncate text-xs">{data.webhook_url}</code>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7 shrink-0"
            onClick={() => void copy(data.webhook_url, "url")}
            aria-label="Copy webhook URL"
          >
            {copiedField === "url" ? (
              <Check className="h-3.5 w-3.5 text-green-600" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </Button>
        </div>
      </div>

      {/* Secret */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-muted-foreground">
          HMAC Secret
        </label>
        {data.has_secret && data.secret ? (
          <div className="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2">
            <code className="min-w-0 flex-1 truncate text-xs font-mono">
              {data.secret}
            </code>
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7 shrink-0"
              onClick={() => void copy(data.secret!, "secret")}
              aria-label="Copy secret"
            >
              {copiedField === "secret" ? (
                <Check className="h-3.5 w-3.5 text-green-600" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No secret generated yet. Click &ldquo;Generate secret&rdquo; below to create one.
          </p>
        )}
      </div>

      {/* Regenerate */}
      <div className="flex items-center gap-3">
        <Button
          size="sm"
          variant={confirmRegenerate ? "destructive" : "outline"}
          onClick={() => void handleRegenerate()}
          disabled={regenerate.isPending}
        >
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          {regenerate.isPending
            ? "Generating…"
            : confirmRegenerate
              ? "Confirm — invalidates current secret"
              : data.has_secret
                ? "Regenerate secret"
                : "Generate secret"}
        </Button>
        {confirmRegenerate && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setConfirmRegenerate(false)}
          >
            Cancel
          </Button>
        )}
        {regenerate.isError && (
          <p className="text-xs text-destructive">Failed — please try again.</p>
        )}
      </div>

      {/* Setup instructions */}
      <div className="rounded-md border bg-card p-4 text-sm">
        <p className="font-medium">How to connect your booking tool</p>
        <ol className="mt-2 space-y-1 text-muted-foreground">
          <li>1. Copy the Webhook URL and secret above.</li>
          <li>2. In your booking tool, find &ldquo;Webhook&rdquo; or &ldquo;Integrations&rdquo; settings.</li>
          <li>3. Add a new webhook pointing to the URL.</li>
          <li>4. Paste the secret into the &ldquo;HMAC secret&rdquo; / &ldquo;Signing key&rdquo; field.</li>
          <li>5. Set the payload to include invitee email and scheduled time.</li>
        </ol>
      </div>
    </div>
  );
}
