import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface Session {
    accessToken?: string;
    workspaceId?: string;
    orgId?: string;
    /** Set to "RefreshAccessTokenError" when silent token refresh fails. */
    error?: string;
  }

  interface User {
    accessToken?: string;
    refreshToken?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken?: string;
    refreshToken?: string;
    workspaceId?: string;
    orgId?: string;
    /** Unix timestamp (seconds) when the access token expires, from the JWT `exp` claim. */
    accessTokenExpiry?: number;
    /** Set to "RefreshAccessTokenError" when silent token refresh fails. */
    error?: string;
  }
}
