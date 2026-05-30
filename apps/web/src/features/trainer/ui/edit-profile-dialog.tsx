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
import { useUpdateProfile } from "@/features/trainer/api/use-trainer-profile";
import { ApiError } from "@/lib/api";
import type { TrainerProfile } from "@/features/trainer/types";

const schema = z
  .object({
    niche: z.string().optional(),
    bio: z.string().optional(),
    topics: z.string().optional(),
    tone: z.string().optional(),
    usp: z.string().optional(),
    target_industries: z.string().optional(),
    languages: z.string().optional(),
    pricing_min_inr: z.coerce.number().int().min(0).optional().or(z.literal(NaN)),
    pricing_max_inr: z.coerce.number().int().min(0).optional().or(z.literal(NaN)),
  })
  .refine(
    (val) => {
      const min = val.pricing_min_inr;
      const max = val.pricing_max_inr;
      if (
        typeof min === "number" &&
        !isNaN(min) &&
        typeof max === "number" &&
        !isNaN(max)
      ) {
        return max >= min;
      }
      return true;
    },
    { message: "Max must be ≥ min", path: ["pricing_max_inr"] }
  );

type FormValues = z.infer<typeof schema>;

function toCSV(arr: string[]): string {
  return arr.join(", ");
}

function fromCSV(s: string | undefined): string[] {
  if (!s?.trim()) return [];
  return s
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

interface EditProfileDialogProps {
  profile: TrainerProfile;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditProfileDialog({
  profile,
  open,
  onOpenChange,
}: EditProfileDialogProps) {
  const { mutate, isPending, error } = useUpdateProfile();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      niche: profile.niche ?? "",
      bio: profile.bio ?? "",
      topics: toCSV(profile.topics),
      tone: profile.tone ?? "",
      usp: profile.usp ?? "",
      target_industries: toCSV(profile.target_industries),
      languages: toCSV(profile.languages),
      pricing_min_inr: profile.pricing_min_inr ?? undefined,
      pricing_max_inr: profile.pricing_max_inr ?? undefined,
    },
  });

  function onSubmit(values: FormValues) {
    const sanitizeNum = (v: unknown) =>
      typeof v === "number" && !isNaN(v) ? v : null;

    mutate(
      {
        niche: values.niche || null,
        bio: values.bio || null,
        topics: fromCSV(values.topics),
        tone: values.tone || null,
        usp: values.usp || null,
        target_industries: fromCSV(values.target_industries),
        languages: fromCSV(values.languages),
        pricing_min_inr: sanitizeNum(values.pricing_min_inr),
        pricing_max_inr: sanitizeNum(values.pricing_max_inr),
      },
      { onSuccess: () => onOpenChange(false) }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Profile</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 py-1">
          {/* Lock-required fields marked with * */}
          <div className="space-y-1.5">
            <Label htmlFor="niche">
              Niche <span className="text-destructive">*</span>
            </Label>
            <Input
              id="niche"
              placeholder="e.g. Leadership Development"
              {...register("niche")}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="bio">
              Bio <span className="text-destructive">*</span>
            </Label>
            <textarea
              id="bio"
              rows={4}
              placeholder="A short professional bio used to personalise outreach messages…"
              className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring resize-none"
              {...register("bio")}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="topics">
              Topics <span className="text-destructive">*</span>{" "}
              <span className="text-xs font-normal text-muted-foreground">
                (comma-separated)
              </span>
            </Label>
            <Input
              id="topics"
              placeholder="Leadership, Communication, Team Building"
              {...register("topics")}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="tone">Tone</Label>
            <Input
              id="tone"
              placeholder="e.g. Warm, professional, story-driven"
              {...register("tone")}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="usp">Unique Selling Point (USP)</Label>
            <Input
              id="usp"
              placeholder="e.g. The only trainer combining MBA frameworks with mindfulness"
              {...register("usp")}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="target_industries">
              Target industries{" "}
              <span className="text-xs font-normal text-muted-foreground">
                (comma-separated)
              </span>
            </Label>
            <Input
              id="target_industries"
              placeholder="IT, BFSI, Manufacturing, Healthcare"
              {...register("target_industries")}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="languages">
              Languages{" "}
              <span className="text-xs font-normal text-muted-foreground">
                (comma-separated)
              </span>
            </Label>
            <Input
              id="languages"
              placeholder="English, Hindi"
              {...register("languages")}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="pricing_min_inr">Pricing min (₹)</Label>
              <Input
                id="pricing_min_inr"
                type="number"
                min={0}
                placeholder="50000"
                {...register("pricing_min_inr")}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pricing_max_inr">Pricing max (₹)</Label>
              <Input
                id="pricing_max_inr"
                type="number"
                min={0}
                placeholder="200000"
                {...register("pricing_max_inr")}
              />
              {errors.pricing_max_inr && (
                <p className="text-xs text-destructive">
                  {errors.pricing_max_inr.message}
                </p>
              )}
            </div>
          </div>

          <p className="text-xs text-muted-foreground">
            <span className="text-destructive">*</span> Required to lock the profile
          </p>

          {error && (
            <p className="text-xs text-destructive">
              {error instanceof ApiError
                ? error.message
                : "Save failed — please try again."}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? "Saving…" : "Save changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
