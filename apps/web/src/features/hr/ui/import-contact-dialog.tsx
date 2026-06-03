"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
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
import { useImportContacts } from "@/features/hr/api/use-contacts";
import { ApiError } from "@/lib/api";
import { SOURCE_TYPES, SOURCE_TYPE_LABELS } from "@/features/hr/types";

const schema = z.object({
  raw_data: z.string().min(10, "At least 10 characters").max(5000),
  source: z.string().min(1, "Required"),
  source_type: z.enum(SOURCE_TYPES as [string, ...string[]]),
  // Opt-in fields are optional — omitting them marks the contact as non-contactable.
  opted_in_at: z.string().optional(),
  opt_in_evidence: z.string().min(5, "At least 5 characters").optional().or(z.literal("")),
  company_name: z.string().min(1, "Required"),
  company_industry: z.string().optional(),
  company_city: z.string().optional(),
  company_country: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

interface ImportContactDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ImportContactDialog({ open, onOpenChange }: ImportContactDialogProps) {
  const { mutate, isPending, isSuccess, error, reset: resetMutation } = useImportContacts();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { source_type: "company_website" },
  });

  function onSubmit(values: FormValues) {
    mutate(
      {
        contacts: [
          {
            raw_data: values.raw_data,
            source: values.source,
            source_type: values.source_type as typeof SOURCE_TYPES[number],
            opted_in_at: values.opted_in_at ? new Date(values.opted_in_at).toISOString() : null,
            opt_in_evidence: values.opt_in_evidence || null,
            company_name: values.company_name,
            company_industry: values.company_industry || null,
            company_city: values.company_city || null,
            company_country: values.company_country || null,
          },
        ],
      },
      {
        onSuccess: () => {
          reset();
          onOpenChange(false);
        },
      }
    );
  }

  function handleClose(open: boolean) {
    if (!open) {
      reset();
      resetMutation();
    }
    onOpenChange(open);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Import HR Contact</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 py-1">
          {/* Raw data */}
          <div className="space-y-1.5">
            <Label htmlFor="raw_data">Contact bio / raw data</Label>
            <textarea
              id="raw_data"
              rows={4}
              placeholder="Paste bio, vCard, LinkedIn snippet, or any text about this contact…"
              className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring resize-none"
              {...register("raw_data")}
            />
            {errors.raw_data && (
              <p className="text-xs text-destructive">{errors.raw_data.message}</p>
            )}
          </div>

          {/* Source */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="source">Source URL / system</Label>
              <Input id="source" placeholder="https://example.com/team" {...register("source")} />
              {errors.source && (
                <p className="text-xs text-destructive">{errors.source.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="source_type">Source type</Label>
              <select
                id="source_type"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
                {...register("source_type")}
              >
                {SOURCE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {SOURCE_TYPE_LABELS[t]}
                  </option>
                ))}
              </select>
              {errors.source_type && (
                <p className="text-xs text-destructive">{errors.source_type.message}</p>
              )}
            </div>
          </div>

          {/* Opt-in — optional; omitting marks the contact as non-contactable */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="opted_in_at">Opted in at <span className="text-muted-foreground font-normal">(optional)</span></Label>
              <Input id="opted_in_at" type="datetime-local" {...register("opted_in_at")} />
              {errors.opted_in_at && (
                <p className="text-xs text-destructive">{errors.opted_in_at.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="opt_in_evidence">Opt-in evidence <span className="text-muted-foreground font-normal">(optional)</span></Label>
              <Input
                id="opt_in_evidence"
                placeholder="URL, screenshot ID, or consent ref"
                {...register("opt_in_evidence")}
              />
              {errors.opt_in_evidence && (
                <p className="text-xs text-destructive">{errors.opt_in_evidence.message}</p>
              )}
            </div>
          </div>

          {/* Company */}
          <p className="text-xs font-medium text-muted-foreground pt-1">Company details</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="company_name">Name</Label>
              <Input id="company_name" placeholder="Acme Corp" {...register("company_name")} />
              {errors.company_name && (
                <p className="text-xs text-destructive">{errors.company_name.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="company_industry">Industry</Label>
              <Input id="company_industry" placeholder="Technology" {...register("company_industry")} />
              {errors.company_industry && (
                <p className="text-xs text-destructive">{errors.company_industry.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="company_city">City</Label>
              <Input id="company_city" placeholder="Mumbai" {...register("company_city")} />
              {errors.company_city && (
                <p className="text-xs text-destructive">{errors.company_city.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="company_country">Country</Label>
              <Input id="company_country" placeholder="India" {...register("company_country")} />
              {errors.company_country && (
                <p className="text-xs text-destructive">{errors.company_country.message}</p>
              )}
            </div>
          </div>

          {error && (
            <p className="text-xs text-destructive">
              {error instanceof ApiError ? error.message : "Import failed — please try again."}
            </p>
          )}
          {isSuccess && (
            <p className="text-xs text-green-600">Contact imported successfully.</p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? "Importing…" : "Import contact"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
