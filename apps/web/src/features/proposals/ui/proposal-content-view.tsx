"use client";

import type { Proposal } from "@/features/proposals/types";

interface ProposalContentViewProps {
  proposal: Proposal;
}

export function ProposalContentView({ proposal }: ProposalContentViewProps) {
  const { content, cloudinary_url } = proposal;
  const title = typeof content.title === "string" ? content.title : null;
  const body = typeof content.body === "string" ? content.body : null;

  // Collect any extra fields the LLM may have added beyond title/body
  const extras = Object.entries(content).filter(
    ([k]) => k !== "title" && k !== "body"
  );

  return (
    <div className="space-y-4">
      {title && (
        <h2 className="text-lg font-semibold leading-snug">{title}</h2>
      )}

      {body ? (
        <div className="whitespace-pre-wrap rounded-lg border bg-muted/30 p-4 text-sm leading-relaxed">
          {body}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground italic">
          No body content available.
        </p>
      )}

      {extras.length > 0 && (
        <dl className="grid grid-cols-1 gap-2 rounded-lg border p-4 text-sm sm:grid-cols-2">
          {extras.map(([key, val]) => (
            <div key={key}>
              <dt className="text-xs font-medium text-muted-foreground capitalize">
                {key.replace(/_/g, " ")}
              </dt>
              <dd className="mt-0.5">
                {typeof val === "string" || typeof val === "number"
                  ? String(val)
                  : JSON.stringify(val)}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {cloudinary_url && (
        <a
          href={cloudinary_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-sm text-primary underline-offset-2 hover:underline"
        >
          View PDF document ↗
        </a>
      )}
    </div>
  );
}
