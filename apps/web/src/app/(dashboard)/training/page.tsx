import type { Metadata } from "next";
import { TrainingCenter } from "@/features/training/ui/training-center";

export const metadata: Metadata = {
  title: "Training Engagements — CorporateMind AI",
};

export default function TrainingRoute() {
  const workspaceId = "default";
  return <TrainingCenter workspaceId={workspaceId} />;
}
