import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  ApprovalStatusBadge,
  DeliveryStatusBadge,
  ProposalStatusBadge,
} from "./proposal-status-badge";

describe("ProposalStatusBadge", () => {
  it("renders 'Draft' for status draft", () => {
    render(<ProposalStatusBadge status="draft" />);
    expect(screen.getByText("Draft")).not.toBeNull();
  });

  it("renders 'Sent' for status sent", () => {
    render(<ProposalStatusBadge status="sent" />);
    expect(screen.getByText("Sent")).not.toBeNull();
  });

  it("falls back to the raw status string for unknown values", () => {
    render(<ProposalStatusBadge status="unknown_state" />);
    expect(screen.getByText("unknown_state")).not.toBeNull();
  });
});

describe("ApprovalStatusBadge", () => {
  it("renders 'Pending Review' for pending_approval", () => {
    render(<ApprovalStatusBadge status="pending_approval" />);
    expect(screen.getByText("Pending Review")).not.toBeNull();
  });

  it("renders 'Approved' for approved", () => {
    render(<ApprovalStatusBadge status="approved" />);
    expect(screen.getByText("Approved")).not.toBeNull();
  });

  it("renders 'Rejected' for rejected", () => {
    render(<ApprovalStatusBadge status="rejected" />);
    expect(screen.getByText("Rejected")).not.toBeNull();
  });

  it("falls back to the raw string for unknown approval status", () => {
    render(<ApprovalStatusBadge status="custom_status" />);
    expect(screen.getByText("custom_status")).not.toBeNull();
  });
});

describe("DeliveryStatusBadge", () => {
  it("renders nothing when status is null", () => {
    const { container } = render(<DeliveryStatusBadge status={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when status is undefined", () => {
    const { container } = render(<DeliveryStatusBadge status={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders 'Queued' for queued", () => {
    render(<DeliveryStatusBadge status="queued" />);
    expect(screen.getByText("Queued")).not.toBeNull();
  });

  it("renders 'Sent' for sent", () => {
    render(<DeliveryStatusBadge status="sent" />);
    expect(screen.getByText("Sent")).not.toBeNull();
  });

  it("renders 'Blocked' for blocked", () => {
    render(<DeliveryStatusBadge status="blocked" />);
    expect(screen.getByText("Blocked")).not.toBeNull();
  });

  it("renders 'Failed' for failed", () => {
    render(<DeliveryStatusBadge status="failed" />);
    expect(screen.getByText("Failed")).not.toBeNull();
  });
});
