"use client";

import type { Proposal } from "@/features/proposals/types";

interface ProposalContentViewProps {
  proposal: Proposal;
}

function renderValue(val: unknown): React.ReactNode {
  if (typeof val === "string" || typeof val === "number") {
    return <span>{String(val)}</span>;
  }
  if (Array.isArray(val)) {
    if (val.every((item) => typeof item === "string")) {
      return (
        <ul className="list-disc pl-4 space-y-1">
          {val.map((item, i) => <li key={i}>{item}</li>)}
        </ul>
      );
    }
    return (
      <div className="space-y-2">
        {val.map((item, i) => (
          <div key={i} className="rounded border p-2 text-xs">
            {Object.entries(item as Record<string, unknown>).map(([k, v]) => (
              <div key={k}>
                <span className="font-medium capitalize">{k.replace(/_/g, " ")}: </span>
                <span>{String(v)}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  }
  if (typeof val === "object" && val !== null) {
    return (
      <div className="space-y-1">
        {Object.entries(val as Record<string, unknown>).map(([k, v]) => (
          <div key={k}>
            <span className="font-medium capitalize">{k.replace(/_/g, " ")}: </span>
            <span>{String(v)}</span>
          </div>
        ))}
      </div>
    );
  }
  return <span>{JSON.stringify(val)}</span>;
}

export function ProposalContentView({ proposal }: ProposalContentViewProps) {
  const { content, cloudinary_url } = proposal;
  const title = typeof content.title === "string" ? content.title : null;
  const body = typeof content.body === "string" ? content.body : null;

  const extras = Object.entries(content).filter(
    ([k]) => k !== "title" && k !== "body"
  );

  return (
    <div className="space-y-4">
      {title && (
        <h2 className="text-lg font-semibold leading-snug">{title}</h2>
      )}

      {body && (
        <div className="whitespace-pre-wrap rounded-lg border bg-muted/30 p-4 text-sm leading-relaxed">
          {body}
        </div>
      )}

      {extras.length > 0 && (
        <dl className="grid grid-cols-1 gap-2 rounded-lg border p-4 text-sm sm:grid-cols-2">
          {extras.map(([key, val]) => (
            <div key={key}>
              <dt className="text-xs font-medium text-muted-foreground capitalize">
                {key.replace(/_/g, " ")}
              </dt>
              <dd className="mt-0.5">{renderValue(val)}</dd>
            </div>
          ))}
        </dl>
      )}

      {!body && extras.length === 0 && (
        <p className="text-sm text-muted-foreground italic">
          No proposal content available.
        </p>
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
