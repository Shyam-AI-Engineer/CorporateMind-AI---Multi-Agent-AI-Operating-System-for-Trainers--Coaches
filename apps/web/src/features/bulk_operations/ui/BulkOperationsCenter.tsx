"use client";

import React, { useState } from "react";
import type { BulkOperationOut, CsvValidationOut, EntityType } from "@/features/bulk_operations/types";
import {
  useBulkOperationList,
  useValidateCsv,
  useImportCsv,
} from "@/features/bulk_operations/api/use-bulk-operations";
import { CsvUploadDialog } from "@/features/bulk_operations/ui/CsvUploadDialog";
import { ValidationResultsTable } from "@/features/bulk_operations/ui/ValidationResultsTable";
import { ImportSummaryCard } from "@/features/bulk_operations/ui/ImportSummaryCard";
import { BulkOperationHistory } from "@/features/bulk_operations/ui/BulkOperationHistory";

interface BulkOperationsCenterProps {
  workspaceId: string;
  requestedBy: string;
}

export function BulkOperationsCenter({ workspaceId, requestedBy }: BulkOperationsCenterProps) {
  const [validation, setValidation] = useState<CsvValidationOut | null>(null);
  const [lastOperation, setLastOperation] = useState<BulkOperationOut | null>(null);

  const historyQuery = useBulkOperationList(workspaceId);
  const validateMutation = useValidateCsv();
  const importMutation = useImportCsv();

  const isLoading = historyQuery.isLoading;
  const hasError = historyQuery.isError;

  async function handleValidate(entityType: EntityType, rows: Record<string, unknown>[]) {
    const result = await validateMutation.mutateAsync({
      workspace_id: workspaceId,
      entity_type: entityType,
      rows,
    });
    setValidation(result);
    setLastOperation(null);
  }

  async function handleImport(entityType: EntityType, rows: Record<string, unknown>[]) {
    const result = await importMutation.mutateAsync({
      workspace_id: workspaceId,
      entity_type: entityType,
      rows,
      requested_by: requestedBy,
    });
    setLastOperation(result);
    setValidation(null);
  }

  if (isLoading) {
    return (
      <div data-testid="bulk-loading" className="flex items-center justify-center py-16">
        <p className="text-sm text-gray-500 dark:text-gray-400">Loading bulk operations…</p>
      </div>
    );
  }

  if (hasError) {
    return (
      <div
        data-testid="bulk-error"
        className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950 p-4"
      >
        <p className="text-sm text-red-700 dark:text-red-300">
          Failed to load bulk operations history. Please try again.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="bulk-operations-center" className="space-y-8">
      {/* Section: Upload CSV */}
      <section aria-labelledby="upload-heading">
        <h2
          id="upload-heading"
          className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-4"
        >
          Upload CSV
        </h2>
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
          <CsvUploadDialog
            onValidate={handleValidate}
            onImport={handleImport}
            isValidating={validateMutation.isPending}
            isImporting={importMutation.isPending}
          />
          {validateMutation.isError && (
            <p data-testid="validate-error" className="mt-2 text-xs text-red-600 dark:text-red-400">
              {validateMutation.error.message}
            </p>
          )}
          {importMutation.isError && (
            <p data-testid="import-error" className="mt-2 text-xs text-red-600 dark:text-red-400">
              {importMutation.error.message}
            </p>
          )}
        </div>
      </section>

      {/* Section: Validation Results */}
      {validation && (
        <section aria-labelledby="validation-heading">
          <h2
            id="validation-heading"
            className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-4"
          >
            Validation Results
          </h2>
          <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
            <ValidationResultsTable validation={validation} />
          </div>
        </section>
      )}

      {/* Section: Operation Summary */}
      {lastOperation && (
        <section aria-labelledby="summary-heading">
          <h2
            id="summary-heading"
            className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-4"
          >
            Operation Summary
          </h2>
          <ImportSummaryCard operation={lastOperation} />
        </section>
      )}

      {/* Section: History */}
      <section aria-labelledby="history-heading">
        <h2
          id="history-heading"
          className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-4"
        >
          History
        </h2>
        <BulkOperationHistory
          operations={historyQuery.data?.operations ?? []}
          total={historyQuery.data?.total ?? 0}
        />
      </section>
    </div>
  );
}
