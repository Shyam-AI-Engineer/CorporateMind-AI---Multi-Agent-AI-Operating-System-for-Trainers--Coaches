"use client";

import React, { useRef, useState } from "react";
import type { EntityType } from "@/features/bulk_operations/types";
import { ENTITY_TYPE_LABELS, SUPPORTED_ENTITY_TYPES } from "@/features/bulk_operations/types";

interface CsvUploadDialogProps {
  onValidate: (entityType: EntityType, rows: Record<string, unknown>[]) => void;
  onImport: (entityType: EntityType, rows: Record<string, unknown>[]) => void;
  isValidating?: boolean;
  isImporting?: boolean;
}

function parseCsvText(text: string): Record<string, unknown>[] {
  const lines = text.trim().split("\n");
  if (lines.length < 2) return [];
  const headers = lines[0].split(",").map((h) => h.trim().replace(/^"|"$/g, ""));
  return lines.slice(1).map((line) => {
    const values = line.split(",").map((v) => v.trim().replace(/^"|"$/g, ""));
    return Object.fromEntries(headers.map((h, i) => [h, values[i] ?? ""]));
  });
}

export function CsvUploadDialog({
  onValidate,
  onImport,
  isValidating = false,
  isImporting = false,
}: CsvUploadDialogProps) {
  const [entityType, setEntityType] = useState<EntityType>("customers");
  const [parsedRows, setParsedRows] = useState<Record<string, unknown>[]>([]);
  const [fileName, setFileName] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setParseError(null);
    const reader = new FileReader();
    reader.onload = (evt) => {
      const text = evt.target?.result as string;
      try {
        const rows = parseCsvText(text);
        if (rows.length === 0) {
          setParseError("CSV appears empty or has no data rows.");
          setParsedRows([]);
        } else {
          setParsedRows(rows);
        }
      } catch {
        setParseError("Failed to parse CSV. Ensure it is valid UTF-8.");
        setParsedRows([]);
      }
    };
    reader.readAsText(file);
  }

  const hasRows = parsedRows.length > 0;

  return (
    <div data-testid="csv-upload-dialog" className="space-y-4">
      {/* Entity type selector */}
      <div>
        <label
          htmlFor="entity-type-select"
          className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
        >
          Entity Type
        </label>
        <select
          id="entity-type-select"
          data-testid="entity-type-select"
          value={entityType}
          onChange={(e) => setEntityType(e.target.value as EntityType)}
          className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-sm text-gray-900 dark:text-gray-100"
        >
          {SUPPORTED_ENTITY_TYPES.map((et) => (
            <option key={et} value={et}>
              {ENTITY_TYPE_LABELS[et]}
            </option>
          ))}
        </select>
      </div>

      {/* File picker */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          CSV File
        </label>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,text/csv"
          data-testid="csv-file-input"
          onChange={handleFileChange}
          className="block w-full text-sm text-gray-700 dark:text-gray-300 file:mr-3 file:rounded-md file:border-0 file:bg-gray-100 dark:file:bg-gray-700 file:px-3 file:py-1.5 file:text-sm file:font-medium"
        />
        {fileName && (
          <p data-testid="file-name" className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {fileName}
          </p>
        )}
        {parseError && (
          <p data-testid="parse-error" className="mt-1 text-xs text-red-600 dark:text-red-400">
            {parseError}
          </p>
        )}
      </div>

      {/* Row count */}
      {hasRows && (
        <p data-testid="row-count" className="text-xs text-gray-600 dark:text-gray-400">
          {parsedRows.length} row{parsedRows.length !== 1 ? "s" : ""} parsed
        </p>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2">
        <button
          data-testid="validate-btn"
          disabled={!hasRows || isValidating}
          onClick={() => onValidate(entityType, parsedRows)}
          className="rounded-md bg-gray-100 dark:bg-gray-700 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 disabled:opacity-40"
        >
          {isValidating ? "Validating…" : "Validate"}
        </button>
        <button
          data-testid="import-btn"
          disabled={!hasRows || isImporting}
          onClick={() => onImport(entityType, parsedRows)}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
        >
          {isImporting ? "Importing…" : "Import"}
        </button>
      </div>
    </div>
  );
}
