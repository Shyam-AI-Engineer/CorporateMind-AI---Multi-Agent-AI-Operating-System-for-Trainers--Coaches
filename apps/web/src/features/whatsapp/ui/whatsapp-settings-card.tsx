"use client";

import { MessageCircle, CheckCircle2, AlertCircle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

interface WhatsAppTemplate {
  id: string;
  name: string;
  language: string;
  approval_status: string;
}

interface TemplateListOut {
  items: WhatsAppTemplate[];
  total: number;
}

function useWhatsAppStatus() {
  return useQuery<TemplateListOut>({
    queryKey: ["whatsapp", "templates"],
    queryFn: () => apiFetch<TemplateListOut>("/api/v1/whatsapp/templates"),
    retry: false,
    staleTime: 60_000,
  });
}

export function WhatsAppSettingsCard() {
  const { data, isLoading, isError } = useWhatsAppStatus();

  const isConnected = !isError;
  const templateCount = data?.total ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <MessageCircle className="h-5 w-5 text-green-600" />
        <h2 className="text-base font-semibold">WhatsApp Business</h2>
        {!isLoading && (
          <span className="ml-auto flex items-center gap-1 text-xs">
            {isConnected ? (
              <>
                <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                <span className="text-green-700">Configured</span>
              </>
            ) : (
              <>
                <AlertCircle className="h-3.5 w-3.5 text-amber-600" />
                <span className="text-amber-700">Not configured</span>
              </>
            )}
          </span>
        )}
      </div>

      <p className="text-sm text-muted-foreground">
        Send outreach messages via WhatsApp Business Cloud API. Requires a Meta
        WhatsApp Business Account (WABA) with at least one approved template.
      </p>

      {isConnected && !isLoading && (
        <div className="rounded-md border bg-muted/40 px-4 py-3 text-sm">
          <span className="font-medium">{templateCount}</span>
          <span className="text-muted-foreground ml-1">
            approved {templateCount === 1 ? "template" : "templates"} available
          </span>
        </div>
      )}

      <div className="rounded-md border bg-card p-4 text-sm">
        <p className="font-medium">Setup requirements</p>
        <ol className="mt-2 space-y-1 text-muted-foreground list-none">
          <li>1. Set <code className="text-xs bg-muted px-1 rounded">WHATSAPP_BUSINESS_ACCOUNT_ID</code>, <code className="text-xs bg-muted px-1 rounded">WHATSAPP_PHONE_NUMBER_ID</code>, and <code className="text-xs bg-muted px-1 rounded">WHATSAPP_ACCESS_TOKEN</code> in your environment.</li>
          <li>2. Submit and get at least one message template approved via Meta Business Manager.</li>
          <li>3. Add <code className="text-xs bg-muted px-1 rounded">phone_e164</code> and WhatsApp opt-in date to each contact you want to reach on WhatsApp.</li>
          <li>4. Create a campaign and select <strong>WhatsApp</strong> as the channel.</li>
        </ol>
      </div>
    </div>
  );
}
