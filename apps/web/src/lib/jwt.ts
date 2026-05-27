/**
 * Decode a JWT payload without verifying the signature.
 * Used server-side (Node.js Buffer) to extract claims like workspace_id.
 */
export function decodeJwtPayload(token: string): Record<string, unknown> {
  try {
    const base64 = token.split(".")[1];
    if (!base64) return {};
    const json = Buffer.from(base64, "base64url").toString("utf-8");
    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return {};
  }
}
