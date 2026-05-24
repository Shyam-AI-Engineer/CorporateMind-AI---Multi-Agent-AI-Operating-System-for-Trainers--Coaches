---
name: review-tenant-isolation
description: Verify tenant_id propagation and isolation on a module or query path — including a runnable regression test
---

# Review Tenant Isolation Skill

## Goal
Confirm that a module/feature CANNOT leak data across tenants. This is a P0 invariant in CorporateMind AI; missing tenant isolation is a release blocker.

## Steps
1. **Ask for:** the module name OR the PR / branch under review.
2. **Static checks (read-only walk):**

### Schema
- [ ] Every new table has `tenant_id UUID NOT NULL`.
- [ ] Composite index `(tenant_id, ...)` on the primary lookup key.
- [ ] RLS policy created (`USING (tenant_id = current_setting('app.tenant_id')::uuid)`).
- [ ] RLS enabled on the table (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`).

### Repository
- [ ] All queries inherit from the base repository OR explicitly include the tenant filter.
- [ ] No raw SQL that bypasses the base repo.
- [ ] No method accepts `tenant_id` as a parameter — comes from `TenantContext` only.
- [ ] Bulk operations (UPDATE / DELETE many) include the tenant filter.

### Service / API
- [ ] Endpoints inject `TenantContext` via `Depends`.
- [ ] No code path constructs queries from user-supplied IDs without scope verification.
- [ ] Pagination cursors are tenant-bound (can't be reused across tenants).

### Caching / Vector / Storage
- [ ] Redis keys include the tenant prefix (`t:{org_id}:{workspace_id}:...`).
- [ ] Qdrant search includes a `tenant_id` payload predicate.
- [ ] Object-storage paths include the tenant prefix.
- [ ] Celery tasks carry `tenant_id` in headers.

### Audit
- [ ] Cross-tenant admin operations use `@cross_tenant_admin_only` and audit-log every call.

3. **Generate the regression test** (mandatory if a new table or query path was added):

```python
# apps/api/tests/isolation/test_<module>_tenancy.py

@pytest.mark.asyncio
async def test_<entity>_isolation_between_tenants(db, http):
    # Arrange: two tenants
    tenant_a = await create_tenant(name="A")
    tenant_b = await create_tenant(name="B")

    # Act: write into A
    async with tenant_ctx(tenant_a):
        item_id = await create_<entity>(...)

    # Assert: B cannot see it through ANY read path
    async with tenant_ctx(tenant_b):
        # Direct repo
        assert await <entity>_repo.get_by_id(item_id) is None
        # List endpoint
        resp = await http.get("/api/v1/<resource>")
        assert all(r["id"] != str(item_id) for r in resp.json()["items"])
        # Search / Qdrant (if applicable)
        results = await search_<entity>(query="...")
        assert all(r.id != item_id for r in results)
        # Direct fetch by ID
        resp = await http.get(f"/api/v1/<resource>/{item_id}")
        assert resp.status_code in (403, 404)
```

4. **Run the test:**
   - `pytest apps/api/tests/isolation/test_<module>_tenancy.py -v`
   - Failure ⇒ tenant isolation bug. Do not merge.

## Quality rules
- This skill is READ-ONLY for the source. It produces a NEW test file.
- The generated test must run against testcontainers Postgres (real RLS, not mocked).
- Cover EVERY read path the module exposes — listing, fetching by ID, searching, exporting.
- If the module has a write path that takes a target ID (e.g., update by ID), test cross-tenant write attempts too.

## Forbidden
- Skipping this when the change "doesn't really involve tenant data" — assume it does.
- Trusting RLS alone — application-level filter MUST be present.

## References
- `.claude/rules/multi-tenancy.md`
- `.claude/rules/testing.md`
- `.claude/rules/security.md`
