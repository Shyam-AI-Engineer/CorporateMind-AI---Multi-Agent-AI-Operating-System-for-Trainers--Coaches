import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import { decodeJwtPayload } from "@/lib/jwt";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface BackendTokenResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

async function callRefresh(refreshToken: string): Promise<BackendTokenResponse> {
  const res = await fetch(`${API_URL}/api/v1/identity/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) throw new Error(`Token refresh failed: ${res.status}`);
  return res.json() as Promise<BackendTokenResponse>;
}

export const authOptions: NextAuthOptions = {
  providers: [
    CredentialsProvider({
      name: "Credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials.password) return null;

        const res = await fetch(`${API_URL}/api/v1/identity/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: credentials.email,
            password: credentials.password,
          }),
        });

        if (!res.ok) return null;

        const data = (await res.json()) as BackendTokenResponse & { user_id?: string };
        return {
          id: data.user_id ?? "unknown",
          email: credentials.email,
          accessToken: data.access_token,
          refreshToken: data.refresh_token,
        };
      },
    }),
  ],

  callbacks: {
    async jwt({ token, user }) {
      // ── Initial sign-in: hydrate token from authorize() result ──────────────
      if (user) {
        token.accessToken = user.accessToken;
        token.refreshToken = user.refreshToken;
        token.error = undefined;
        if (user.accessToken) {
          const payload = decodeJwtPayload(user.accessToken);
          token.workspaceId = payload.workspace_id as string | undefined;
          token.orgId = payload.org_id as string | undefined;
          // Use the JWT's own `exp` claim — avoids clock skew from computing
          // Date.now() + expires_in after a variable network round-trip.
          token.accessTokenExpiry = payload.exp as number | undefined;
        }
        return token;
      }

      // ── Fast path: access token still valid (60 s grace buffer) ─────────────
      const nowSec = Math.floor(Date.now() / 1000);
      if (token.accessTokenExpiry && nowSec < token.accessTokenExpiry - 60) {
        return token;
      }

      // ── No refresh token stored — cannot recover ─────────────────────────────
      if (!token.refreshToken) {
        return { ...token, error: "RefreshAccessTokenError" as const };
      }

      // ── Attempt silent refresh ────────────────────────────────────────────────
      // The backend rotates the refresh token (JTI blocklist), so the returned
      // refresh_token must replace the stored one to avoid double-use errors.
      try {
        const refreshed = await callRefresh(token.refreshToken);
        const payload = decodeJwtPayload(refreshed.access_token);
        return {
          ...token,
          accessToken: refreshed.access_token,
          refreshToken: refreshed.refresh_token, // rotated — must overwrite
          accessTokenExpiry: payload.exp as number | undefined,
          workspaceId: payload.workspace_id as string | undefined,
          orgId: payload.org_id as string | undefined,
          error: undefined,
        };
      } catch {
        // Preserve existing (stale) tokens so the client can attempt recovery;
        // SessionGuard will detect the error and sign the user out cleanly.
        return { ...token, error: "RefreshAccessTokenError" as const };
      }
    },

    async session({ session, token }) {
      session.accessToken = token.accessToken;
      session.workspaceId = token.workspaceId;
      session.orgId = token.orgId;
      session.error = token.error;
      return session;
    },
  },

  pages: {
    signIn: "/login",
    error: "/login",
  },

  session: {
    strategy: "jwt",
    // 7 days — the jwt callback silently rotates the 15-min access token via
    // /identity/refresh before it expires, so sessions survive extended usage
    // without forcing re-login. Actual session termination happens when the
    // refresh token is revoked (logout or server-side blocklist).
    maxAge: 7 * 24 * 60 * 60,
  },
};
