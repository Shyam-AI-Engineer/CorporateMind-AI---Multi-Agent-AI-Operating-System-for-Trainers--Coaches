"use client";

import { useEffect } from "react";
import { useSession, signOut } from "next-auth/react";

/**
 * Detects refresh token failure and forces a clean logout rather than
 * leaving the user in a broken authenticated-but-unauthorized state.
 * Renders nothing — used purely for its side effect.
 */
export function SessionGuard() {
  const { data: session } = useSession();

  useEffect(() => {
    if (session?.error === "RefreshAccessTokenError") {
      void signOut({ callbackUrl: "/login" });
    }
  }, [session?.error]);

  return null;
}
