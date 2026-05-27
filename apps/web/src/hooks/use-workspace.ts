"use client";

import { useSession } from "next-auth/react";

export function useWorkspace() {
  const { data: session } = useSession();
  return {
    workspaceId: session?.workspaceId ?? null,
    orgId: session?.orgId ?? null,
  };
}
