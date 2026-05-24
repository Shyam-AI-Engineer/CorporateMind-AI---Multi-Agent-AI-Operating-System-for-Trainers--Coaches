# Frontend Next.js Rules

Apply when editing files under `apps/web/`.

## Framework
- Next.js 14 App Router. RSC by default; `"use client"` only when needed (forms, hooks, event handlers).
- Strict TypeScript — no `any`. Types generated from backend OpenAPI live in `packages/shared-types`.
- Tailwind + shadcn/ui + Radix primitives. Don't introduce another UI kit.

## Structure
- Feature-sliced: `apps/web/features/<name>/{api,hooks,ui,types.ts}`.
- Small reusable components; one component per file.
- Separate UI from data fetching — TanStack Query hooks in `features/*/api/`.

## Async UI
- Every async surface MUST have loading, empty, and error states.
- Prefer Suspense boundaries for RSC; query-state for client components.
- SSE hook (`useEventSource`) for agent-run / campaign-progress streams; reconnect with backoff.

## Forms
- React Hook Form + Zod. Re-use Zod schemas generated from backend OpenAPI when possible.
- Disable submit while pending; surface server errors against the right field.

## Routing & auth
- Auth-guarded routes go under `app/(dashboard)/`. Public marketing under `app/(marketing)/`.
- NextAuth handles credentials + Google; exchanges for backend JWT stored in httpOnly cookie.
- Tenant guard middleware reads `tenant_id` from JWT and redirects on mismatch.

## API client
- One central `lib/api.ts` wraps fetch with auth header injection + error normalization.
- Never inline `fetch()` in components.

## Charts & analytics
- Recharts for dashboards. No Chart.js / Highcharts.

## Performance
- Default to RSC; client components only where interactivity is required.
- Avoid deeply nested trees when composition is cleaner.
- Image: Next `<Image>` only — no raw `<img>` for content images.
