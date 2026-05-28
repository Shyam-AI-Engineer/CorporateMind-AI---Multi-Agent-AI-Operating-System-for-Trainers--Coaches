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
import type { TrainerProfile } from "@/features/trainer/types";

const schema = z.object({
  niche: z.string().optional(),
  tone: z.string().optional(),
  usp: z.string().optional(),
  pricing_min_inr: z.coerce.number().int().min(0).optional().or(z.literal(NaN)),
  pricing_max_inr: z.coerce.number().int().min(0).optional().or(z.literal(NaN)),
}).refine(
  (val) => {
    const min = val.pricing_min_inr;
    const max = val.pricing_max_inr;
    if (
      typeof min === "number" && !isNaN(min) &&
      typeof max === "number" && !isNaN(max)
    ) {
      return max >= min;
    }
    return true;
  },
  { message: "Max must be greater than or equal to min", path: ["pricing_max_inr"] }
);

type FormValues = z.infer<typeof schema>;

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
      tone: profile.tone ?? "",
      usp: profile.usp ?? "",
      pricing_min_inr: profile.pricing_min_inr ?? undefined,
      pricing_max_inr: profile.pricing_max_inr ?? undefined,
    },
  });

  function onSubmit(values: FormValues) {
    const sanitize = (v: unknown) =>
      typeof v === "number" && !isNaN(v) ? v : null;

    mutate(
      {
        niche: values.niche || null,
        tone: values.tone || null,
        usp: values.usp || null,
        pricing_min_inr: sanitize(values.pricing_min_inr),
        pricing_max_inr: sanitize(values.pricing_max_inr),
      },
      { onSuccess: () => onOpenChange(false) }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit Profile</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 py-1">
          <div className="space-y-1.5">
            <Label htmlFor="niche">Niche</Label>
            <Input
              id="niche"
              placeholder="e.g. Leadership Development"
              {...register("niche")}
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

          {error && (
            <p className="text-xs text-destructive">
              Save failed. The profile may be locked.
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
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
