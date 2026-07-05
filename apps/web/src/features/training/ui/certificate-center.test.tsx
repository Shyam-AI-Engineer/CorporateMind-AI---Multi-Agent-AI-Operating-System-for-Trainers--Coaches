/**
 * Tests for CertificateCenter — Sprint 45.
 * Pattern: no jest-dom; use .not.toBeNull() / .textContent.toContain() / .toBeNull()
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ── Module mock setup ──────────────────────────────────────────────────────────

const mockListData = {
  data: { data: { items: [], next_cursor: null, has_more: false, total: 0 } },
  isLoading: false,
  isError: false,
};

const mockCreate = { mutateAsync: vi.fn(), isPending: false, error: null };
const mockIssue = { mutateAsync: vi.fn(), isPending: false, error: null };
const mockRevoke = { mutateAsync: vi.fn(), isPending: false, error: null };
const mockUpdate = { mutateAsync: vi.fn(), isPending: false, error: null };

vi.mock("@/features/training/api/use-training", () => ({
  useCertificateList: vi.fn(() => mockListData),
  useCreateCertificate: vi.fn(() => mockCreate),
  useIssueCertificate: vi.fn(() => mockIssue),
  useRevokeCertificate: vi.fn(() => mockRevoke),
  useUpdateCertificate: vi.fn(() => mockUpdate),
}));

import {
  useCertificateList,
  useCreateCertificate,
  useIssueCertificate,
  useRevokeCertificate,
  useUpdateCertificate,
} from "@/features/training/api/use-training";
import { CertificateCenter } from "@/features/training/ui/certificate-center";

// ── Helpers ────────────────────────────────────────────────────────────────────

const SESSION_ID = "sess-111";
const WORKSPACE_ID = "ws-222";

function makeCert(overrides: Record<string, unknown> = {}) {
  return {
    id: "cert-001",
    tenant_id: "t-001",
    workspace_id: WORKSPACE_ID,
    attendance_id: "att-001",
    session_id: SESSION_ID,
    certificate_number: null,
    participant_name: "Alice Smith",
    participant_email: "alice@example.com",
    certificate_title: null,
    issue_date: null,
    issued_by: null,
    status: "draft",
    download_count: 0,
    verification_code: "abc123xyz456",
    notes: null,
    created_at: "2026-07-05T10:00:00Z",
    updated_at: "2026-07-05T10:00:00Z",
    ...overrides,
  };
}

function renderCenter() {
  return render(
    <CertificateCenter sessionId={SESSION_ID} workspaceId={WORKSPACE_ID} />,
  );
}

function setListData(overrides: Partial<typeof mockListData> = {}) {
  vi.mocked(useCertificateList).mockReturnValue({
    ...mockListData,
    ...overrides,
  } as ReturnType<typeof useCertificateList>);
}

// ── Loading / error states ─────────────────────────────────────────────────────

describe("CertificateCenter — loading & error", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useCreateCertificate).mockReturnValue(mockCreate as ReturnType<typeof useCreateCertificate>);
    vi.mocked(useIssueCertificate).mockReturnValue(mockIssue as ReturnType<typeof useIssueCertificate>);
    vi.mocked(useRevokeCertificate).mockReturnValue(mockRevoke as ReturnType<typeof useRevokeCertificate>);
    vi.mocked(useUpdateCertificate).mockReturnValue(mockUpdate as ReturnType<typeof useUpdateCertificate>);
  });

  it("renders loading state", () => {
    setListData({ isLoading: true, isError: false, data: undefined });
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="certificate-loading"]')).not.toBeNull();
  });

  it("does not render center when loading", () => {
    setListData({ isLoading: true, isError: false, data: undefined });
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="certificate-center"]')).toBeNull();
  });

  it("renders error state", () => {
    setListData({ isLoading: false, isError: true, data: undefined });
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="certificate-error"]')).not.toBeNull();
  });

  it("does not render center on error", () => {
    setListData({ isLoading: false, isError: true, data: undefined });
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="certificate-center"]')).toBeNull();
  });
});

// ── Empty state ────────────────────────────────────────────────────────────────

describe("CertificateCenter — empty state", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useCertificateList).mockReturnValue(mockListData as ReturnType<typeof useCertificateList>);
    vi.mocked(useCreateCertificate).mockReturnValue(mockCreate as ReturnType<typeof useCreateCertificate>);
    vi.mocked(useIssueCertificate).mockReturnValue(mockIssue as ReturnType<typeof useIssueCertificate>);
    vi.mocked(useRevokeCertificate).mockReturnValue(mockRevoke as ReturnType<typeof useRevokeCertificate>);
    vi.mocked(useUpdateCertificate).mockReturnValue(mockUpdate as ReturnType<typeof useUpdateCertificate>);
  });

  it("renders certificate-center container", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="certificate-center"]')).not.toBeNull();
  });

  it("renders empty state when no items", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="certificate-empty"]')).not.toBeNull();
  });

  it("does not render table in empty state", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="certificate-table"]')).toBeNull();
  });

  it("renders btn-create-empty in empty state", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="btn-create-empty"]')).not.toBeNull();
  });

  it("kpi-total shows zero", () => {
    const { container } = renderCenter();
    const el = container.querySelector('[data-testid="kpi-total"]');
    expect(el).not.toBeNull();
    expect(el!.textContent).toContain("0");
  });

  it("kpi-issued shows zero", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="kpi-issued"]')!.textContent).toContain("0");
  });

  it("kpi-draft shows zero", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="kpi-draft"]')!.textContent).toContain("0");
  });

  it("kpi-revoked shows zero", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="kpi-revoked"]')!.textContent).toContain("0");
  });

  it("renders toolbar search input", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="input-search"]')).not.toBeNull();
  });

  it("renders status filter select", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="select-status-filter"]')).not.toBeNull();
  });

  it("renders btn-create-certificate toolbar button", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="btn-create-certificate"]')).not.toBeNull();
  });
});

// ── With certificates ──────────────────────────────────────────────────────────

describe("CertificateCenter — with certificates", () => {
  const draftCert = makeCert({ id: "cert-001", status: "draft" });
  const issuedCert = makeCert({
    id: "cert-002",
    status: "issued",
    participant_name: "Bob Jones",
    certificate_number: "CERT-2026-001",
  });
  const revokedCert = makeCert({ id: "cert-003", status: "revoked", participant_name: "Carol" });

  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useCertificateList).mockReturnValue({
      data: {
        data: {
          items: [draftCert, issuedCert, revokedCert],
          next_cursor: null,
          has_more: false,
          total: 3,
        },
      },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCertificateList>);
    vi.mocked(useCreateCertificate).mockReturnValue(mockCreate as ReturnType<typeof useCreateCertificate>);
    vi.mocked(useIssueCertificate).mockReturnValue(mockIssue as ReturnType<typeof useIssueCertificate>);
    vi.mocked(useRevokeCertificate).mockReturnValue(mockRevoke as ReturnType<typeof useRevokeCertificate>);
    vi.mocked(useUpdateCertificate).mockReturnValue(mockUpdate as ReturnType<typeof useUpdateCertificate>);
  });

  it("renders certificate-table", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="certificate-table"]')).not.toBeNull();
  });

  it("does not render empty state when items present", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="certificate-empty"]')).toBeNull();
  });

  it("renders row for draft cert", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="certificate-row-cert-001"]')).not.toBeNull();
  });

  it("renders row for issued cert", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="certificate-row-cert-002"]')).not.toBeNull();
  });

  it("renders row for revoked cert", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="certificate-row-cert-003"]')).not.toBeNull();
  });

  it("renders status badge for draft", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="status-badge-cert-001"]')).not.toBeNull();
  });

  it("renders status badge for issued", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="status-badge-cert-002"]')).not.toBeNull();
  });

  it("draft badge shows 'draft'", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="status-badge-cert-001"]')!.textContent).toContain("draft");
  });

  it("issued badge shows 'issued'", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="status-badge-cert-002"]')!.textContent).toContain("issued");
  });

  it("renders cert number for issued cert", () => {
    const { container } = renderCenter();
    const el = container.querySelector('[data-testid="cert-number-cert-002"]');
    expect(el).not.toBeNull();
    expect(el!.textContent).toContain("CERT-2026-001");
  });

  it("renders action button for draft cert", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="btn-action-cert-001"]')).not.toBeNull();
  });

  it("draft action button shows 'Issue'", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="btn-action-cert-001"]')!.textContent).toContain("Issue");
  });

  it("issued action button shows 'Revoke'", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="btn-action-cert-002"]')!.textContent).toContain("Revoke");
  });

  it("revoked action button shows 'View'", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="btn-action-cert-003"]')!.textContent).toContain("View");
  });

  it("kpi-total shows 3", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="kpi-total"]')!.textContent).toContain("3");
  });

  it("kpi-draft shows 1", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="kpi-draft"]')!.textContent).toContain("1");
  });

  it("kpi-issued shows 1", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="kpi-issued"]')!.textContent).toContain("1");
  });

  it("kpi-revoked shows 1", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="kpi-revoked"]')!.textContent).toContain("1");
  });

  it("certificate-count shows total", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="certificate-count"]')).not.toBeNull();
  });

  it("does not render load-more when has_more false", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="btn-load-more"]')).toBeNull();
  });

  it("renders load-more when has_more true", () => {
    vi.mocked(useCertificateList).mockReturnValue({
      data: {
        data: {
          items: [draftCert],
          next_cursor: "cursor-abc",
          has_more: true,
          total: 10,
        },
      },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCertificateList>);
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="btn-load-more"]')).not.toBeNull();
  });
});

// ── Create dialog ──────────────────────────────────────────────────────────────

describe("CertificateCenter — create dialog", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useCertificateList).mockReturnValue(mockListData as ReturnType<typeof useCertificateList>);
    vi.mocked(useCreateCertificate).mockReturnValue(mockCreate as ReturnType<typeof useCreateCertificate>);
    vi.mocked(useIssueCertificate).mockReturnValue(mockIssue as ReturnType<typeof useIssueCertificate>);
    vi.mocked(useRevokeCertificate).mockReturnValue(mockRevoke as ReturnType<typeof useRevokeCertificate>);
    vi.mocked(useUpdateCertificate).mockReturnValue(mockUpdate as ReturnType<typeof useUpdateCertificate>);
  });

  it("create dialog not open by default", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="create-dialog"]')).toBeNull();
  });

  it("clicking btn-create-certificate opens dialog", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-create-certificate"]')!);
    expect(container.querySelector('[data-testid="create-dialog"]')).not.toBeNull();
  });

  it("clicking btn-create-empty opens dialog", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-create-empty"]')!);
    expect(container.querySelector('[data-testid="create-dialog"]')).not.toBeNull();
  });

  it("create dialog has form", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-create-certificate"]')!);
    expect(container.querySelector('[data-testid="create-form"]')).not.toBeNull();
  });

  it("create dialog has input-cert-title", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-create-certificate"]')!);
    expect(container.querySelector('[data-testid="input-cert-title"]')).not.toBeNull();
  });

  it("create dialog has btn-cancel-create", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-create-certificate"]')!);
    expect(container.querySelector('[data-testid="btn-cancel-create"]')).not.toBeNull();
  });

  it("create dialog has btn-submit-create", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-create-certificate"]')!);
    expect(container.querySelector('[data-testid="btn-submit-create"]')).not.toBeNull();
  });

  it("cancel button closes dialog", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-create-certificate"]')!);
    await user.click(container.querySelector('[data-testid="btn-cancel-create"]')!);
    expect(container.querySelector('[data-testid="create-dialog"]')).toBeNull();
  });

  it("shows create error when mutation errors", async () => {
    const user = userEvent.setup();
    vi.mocked(useCreateCertificate).mockReturnValue({
      ...mockCreate,
      error: new Error("Already exists"),
    } as ReturnType<typeof useCreateCertificate>);
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-create-certificate"]')!);
    expect(container.querySelector('[data-testid="create-error"]')).not.toBeNull();
  });
});

// ── Issue dialog ───────────────────────────────────────────────────────────────

describe("CertificateCenter — issue dialog", () => {
  const draftCert = makeCert({ id: "cert-d1", status: "draft" });

  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useCertificateList).mockReturnValue({
      data: { data: { items: [draftCert], next_cursor: null, has_more: false, total: 1 } },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCertificateList>);
    vi.mocked(useCreateCertificate).mockReturnValue(mockCreate as ReturnType<typeof useCreateCertificate>);
    vi.mocked(useIssueCertificate).mockReturnValue(mockIssue as ReturnType<typeof useIssueCertificate>);
    vi.mocked(useRevokeCertificate).mockReturnValue(mockRevoke as ReturnType<typeof useRevokeCertificate>);
    vi.mocked(useUpdateCertificate).mockReturnValue(mockUpdate as ReturnType<typeof useUpdateCertificate>);
  });

  it("issue dialog not open by default", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="issue-dialog"]')).toBeNull();
  });

  it("clicking Issue action opens issue dialog", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-action-cert-d1"]')!);
    expect(container.querySelector('[data-testid="issue-dialog"]')).not.toBeNull();
  });

  it("issue dialog has input-issue-date", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-action-cert-d1"]')!);
    expect(container.querySelector('[data-testid="input-issue-date"]')).not.toBeNull();
  });

  it("issue dialog has input-issued-by", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-action-cert-d1"]')!);
    expect(container.querySelector('[data-testid="input-issued-by"]')).not.toBeNull();
  });

  it("issue dialog has input-cert-number", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-action-cert-d1"]')!);
    expect(container.querySelector('[data-testid="input-cert-number"]')).not.toBeNull();
  });

  it("issue dialog has btn-cancel-issue", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-action-cert-d1"]')!);
    expect(container.querySelector('[data-testid="btn-cancel-issue"]')).not.toBeNull();
  });

  it("issue dialog has btn-confirm-issue", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-action-cert-d1"]')!);
    expect(container.querySelector('[data-testid="btn-confirm-issue"]')).not.toBeNull();
  });

  it("cancel button closes issue dialog", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-action-cert-d1"]')!);
    await user.click(container.querySelector('[data-testid="btn-cancel-issue"]')!);
    expect(container.querySelector('[data-testid="issue-dialog"]')).toBeNull();
  });

  it("issue dialog shows error when mutation errors", async () => {
    const user = userEvent.setup();
    vi.mocked(useIssueCertificate).mockReturnValue({
      ...mockIssue,
      error: new Error("Cannot issue"),
    } as ReturnType<typeof useIssueCertificate>);
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-action-cert-d1"]')!);
    expect(container.querySelector('[data-testid="issue-error"]')).not.toBeNull();
  });
});

// ── Revoke dialog ──────────────────────────────────────────────────────────────

describe("CertificateCenter — revoke dialog", () => {
  const issuedCert = makeCert({ id: "cert-i1", status: "issued" });

  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useCertificateList).mockReturnValue({
      data: { data: { items: [issuedCert], next_cursor: null, has_more: false, total: 1 } },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCertificateList>);
    vi.mocked(useCreateCertificate).mockReturnValue(mockCreate as ReturnType<typeof useCreateCertificate>);
    vi.mocked(useIssueCertificate).mockReturnValue(mockIssue as ReturnType<typeof useIssueCertificate>);
    vi.mocked(useRevokeCertificate).mockReturnValue(mockRevoke as ReturnType<typeof useRevokeCertificate>);
    vi.mocked(useUpdateCertificate).mockReturnValue(mockUpdate as ReturnType<typeof useUpdateCertificate>);
  });

  it("revoke dialog not open by default", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="revoke-dialog"]')).toBeNull();
  });

  it("clicking Revoke action opens revoke dialog", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-action-cert-i1"]')!);
    expect(container.querySelector('[data-testid="revoke-dialog"]')).not.toBeNull();
  });

  it("revoke dialog has input-revoke-notes", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-action-cert-i1"]')!);
    expect(container.querySelector('[data-testid="input-revoke-notes"]')).not.toBeNull();
  });

  it("revoke dialog has btn-cancel-revoke", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-action-cert-i1"]')!);
    expect(container.querySelector('[data-testid="btn-cancel-revoke"]')).not.toBeNull();
  });

  it("revoke dialog has btn-confirm-revoke", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-action-cert-i1"]')!);
    expect(container.querySelector('[data-testid="btn-confirm-revoke"]')).not.toBeNull();
  });

  it("cancel button closes revoke dialog", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-action-cert-i1"]')!);
    await user.click(container.querySelector('[data-testid="btn-cancel-revoke"]')!);
    expect(container.querySelector('[data-testid="revoke-dialog"]')).toBeNull();
  });

  it("revoke dialog shows error when mutation errors", async () => {
    const user = userEvent.setup();
    vi.mocked(useRevokeCertificate).mockReturnValue({
      ...mockRevoke,
      error: new Error("Already revoked"),
    } as ReturnType<typeof useRevokeCertificate>);
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-action-cert-i1"]')!);
    expect(container.querySelector('[data-testid="revoke-error"]')).not.toBeNull();
  });
});

// ── Certificate drawer ─────────────────────────────────────────────────────────

describe("CertificateCenter — certificate drawer", () => {
  const cert = makeCert({
    id: "cert-d2",
    status: "draft",
    participant_name: "Dave Lee",
    certificate_title: "Completion",
    certificate_number: "CERT-999",
    verification_code: "verify-abc",
    notes: "Good work",
    download_count: 5,
    issued_by: null,
  });

  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useCertificateList).mockReturnValue({
      data: { data: { items: [cert], next_cursor: null, has_more: false, total: 1 } },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCertificateList>);
    vi.mocked(useCreateCertificate).mockReturnValue(mockCreate as ReturnType<typeof useCreateCertificate>);
    vi.mocked(useIssueCertificate).mockReturnValue(mockIssue as ReturnType<typeof useIssueCertificate>);
    vi.mocked(useRevokeCertificate).mockReturnValue(mockRevoke as ReturnType<typeof useRevokeCertificate>);
    vi.mocked(useUpdateCertificate).mockReturnValue(mockUpdate as ReturnType<typeof useUpdateCertificate>);
  });

  it("drawer not visible by default", () => {
    const { container } = renderCenter();
    expect(container.querySelector('[data-testid="certificate-drawer"]')).toBeNull();
  });

  it("clicking participant name opens drawer", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    expect(container.querySelector('[data-testid="certificate-drawer"]')).not.toBeNull();
  });

  it("drawer shows participant name", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    expect(container.querySelector('[data-testid="drawer-participant-name"]')!.textContent).toContain("Dave Lee");
  });

  it("drawer shows status badge", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    expect(container.querySelector('[data-testid="drawer-status-badge"]')).not.toBeNull();
  });

  it("drawer shows cert title", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    expect(container.querySelector('[data-testid="drawer-cert-title"]')!.textContent).toContain("Completion");
  });

  it("drawer shows cert number", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    expect(container.querySelector('[data-testid="drawer-cert-number"]')!.textContent).toContain("CERT-999");
  });

  it("drawer shows verification code", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    expect(container.querySelector('[data-testid="drawer-verification-code"]')!.textContent).toContain("verify-abc");
  });

  it("drawer shows download count", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    expect(container.querySelector('[data-testid="drawer-download-count"]')!.textContent).toContain("5");
  });

  it("drawer shows notes", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    expect(container.querySelector('[data-testid="drawer-notes"]')!.textContent).toContain("Good work");
  });

  it("btn-close-drawer is present", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    expect(container.querySelector('[data-testid="btn-close-drawer"]')).not.toBeNull();
  });

  it("btn-close-drawer closes drawer", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    await user.click(container.querySelector('[data-testid="btn-close-drawer"]')!);
    expect(container.querySelector('[data-testid="certificate-drawer"]')).toBeNull();
  });

  it("edit form not visible by default in drawer", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    expect(container.querySelector('[data-testid="drawer-edit-form"]')).toBeNull();
  });

  it("clicking edit button shows edit form", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    await user.click(container.querySelector('[data-testid="btn-edit-certificate"]')!);
    expect(container.querySelector('[data-testid="drawer-edit-form"]')).not.toBeNull();
  });

  it("edit form has edit-cert-title input", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    await user.click(container.querySelector('[data-testid="btn-edit-certificate"]')!);
    expect(container.querySelector('[data-testid="edit-cert-title"]')).not.toBeNull();
  });

  it("edit form has edit-cert-number input", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    await user.click(container.querySelector('[data-testid="btn-edit-certificate"]')!);
    expect(container.querySelector('[data-testid="edit-cert-number"]')).not.toBeNull();
  });

  it("edit form has edit-issued-by input", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    await user.click(container.querySelector('[data-testid="btn-edit-certificate"]')!);
    expect(container.querySelector('[data-testid="edit-issued-by"]')).not.toBeNull();
  });

  it("edit form has edit-notes textarea", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    await user.click(container.querySelector('[data-testid="btn-edit-certificate"]')!);
    expect(container.querySelector('[data-testid="edit-notes"]')).not.toBeNull();
  });

  it("edit form has btn-save-edit", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    await user.click(container.querySelector('[data-testid="btn-edit-certificate"]')!);
    expect(container.querySelector('[data-testid="btn-save-edit"]')).not.toBeNull();
  });

  it("edit form has btn-cancel-edit", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    await user.click(container.querySelector('[data-testid="btn-edit-certificate"]')!);
    expect(container.querySelector('[data-testid="btn-cancel-edit"]')).not.toBeNull();
  });

  it("btn-cancel-edit dismisses edit form", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    await user.click(container.querySelector('[data-testid="btn-edit-certificate"]')!);
    await user.click(container.querySelector('[data-testid="btn-cancel-edit"]')!);
    expect(container.querySelector('[data-testid="drawer-edit-form"]')).toBeNull();
  });

  it("drawer shows drawer-error when update mutation errors", async () => {
    const user = userEvent.setup();
    vi.mocked(useUpdateCertificate).mockReturnValue({
      ...mockUpdate,
      error: new Error("Update failed"),
    } as ReturnType<typeof useUpdateCertificate>);
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="certificate-row-cert-d2"] button')!);
    await user.click(container.querySelector('[data-testid="btn-edit-certificate"]')!);
    expect(container.querySelector('[data-testid="drawer-error"]')).not.toBeNull();
  });
});

// ── Revoked cert — view (no edit) ──────────────────────────────────────────────

describe("CertificateCenter — revoked cert action opens drawer", () => {
  const revokedCert = makeCert({ id: "cert-r1", status: "revoked" });

  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useCertificateList).mockReturnValue({
      data: { data: { items: [revokedCert], next_cursor: null, has_more: false, total: 1 } },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCertificateList>);
    vi.mocked(useCreateCertificate).mockReturnValue(mockCreate as ReturnType<typeof useCreateCertificate>);
    vi.mocked(useIssueCertificate).mockReturnValue(mockIssue as ReturnType<typeof useIssueCertificate>);
    vi.mocked(useRevokeCertificate).mockReturnValue(mockRevoke as ReturnType<typeof useRevokeCertificate>);
    vi.mocked(useUpdateCertificate).mockReturnValue(mockUpdate as ReturnType<typeof useUpdateCertificate>);
  });

  it("clicking View on revoked opens drawer not dialog", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-action-cert-r1"]')!);
    expect(container.querySelector('[data-testid="certificate-drawer"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="revoke-dialog"]')).toBeNull();
  });

  it("revoked cert drawer has no edit button", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.click(container.querySelector('[data-testid="btn-action-cert-r1"]')!);
    expect(container.querySelector('[data-testid="btn-edit-certificate"]')).toBeNull();
  });
});

// ── Status filter ──────────────────────────────────────────────────────────────

describe("CertificateCenter — status filter", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useCertificateList).mockReturnValue(mockListData as ReturnType<typeof useCertificateList>);
    vi.mocked(useCreateCertificate).mockReturnValue(mockCreate as ReturnType<typeof useCreateCertificate>);
    vi.mocked(useIssueCertificate).mockReturnValue(mockIssue as ReturnType<typeof useIssueCertificate>);
    vi.mocked(useRevokeCertificate).mockReturnValue(mockRevoke as ReturnType<typeof useRevokeCertificate>);
    vi.mocked(useUpdateCertificate).mockReturnValue(mockUpdate as ReturnType<typeof useUpdateCertificate>);
  });

  it("select-status-filter has all-statuses option", () => {
    const { container } = renderCenter();
    const sel = container.querySelector('[data-testid="select-status-filter"]')!;
    expect(sel.textContent).toContain("All statuses");
  });

  it("select-status-filter contains draft option", () => {
    const { container } = renderCenter();
    const sel = container.querySelector('[data-testid="select-status-filter"]')!;
    expect(sel.textContent).toContain("draft");
  });

  it("select-status-filter contains issued option", () => {
    const { container } = renderCenter();
    const sel = container.querySelector('[data-testid="select-status-filter"]')!;
    expect(sel.textContent).toContain("issued");
  });

  it("select-status-filter contains revoked option", () => {
    const { container } = renderCenter();
    const sel = container.querySelector('[data-testid="select-status-filter"]')!;
    expect(sel.textContent).toContain("revoked");
  });

  it("changing status filter calls useCertificateList with new status", async () => {
    const user = userEvent.setup();
    const { container } = renderCenter();
    await user.selectOptions(
      container.querySelector('[data-testid="select-status-filter"]') as HTMLSelectElement,
      "issued",
    );
    const lastCall = vi.mocked(useCertificateList).mock.lastCall?.[0];
    expect(lastCall?.status).toBe("issued");
  });
});
