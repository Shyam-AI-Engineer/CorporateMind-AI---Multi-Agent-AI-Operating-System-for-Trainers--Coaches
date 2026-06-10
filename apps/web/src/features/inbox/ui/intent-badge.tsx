/**
 * IntentBadge — render a reply intent as a coloured pill.
 *
 * Reuses the existing Badge primitive from @/components/ui/badge — no new
 * badge framework.  The variant mapping lives in features/inbox/types.ts so
 * the seven canonical intents stay defined in exactly one place.
 *
 * NULL intent renders as a muted "Unclassified" outline badge so the table
 * never has gaps.
 */

import { Badge } from "@/components/ui/badge";
import {
  INTENT_CONFIG,
  type ReplyIntent,
} from "@/features/inbox/types";

interface IntentBadgeProps {
  intent: ReplyIntent | null;
  confidence?: number | null;
  /** Show confidence value alongside the intent label (default false). */
  showConfidence?: boolean;
}

export function IntentBadge({
  intent,
  confidence,
  showConfidence = false,
}: IntentBadgeProps) {
  if (!intent) {
    return (
      <Badge variant="outline" aria-label="Unclassified reply">
        Unclassified
      </Badge>
    );
  }

  const config = INTENT_CONFIG[intent];
  const conf =
    showConfidence && confidence != null
      ? ` · ${Math.round(confidence * 100)}%`
      : "";

  return (
    <Badge
      variant={config.variant}
      aria-label={`Reply intent: ${config.label}${conf}`}
    >
      {config.label}
      {conf}
    </Badge>
  );
}
