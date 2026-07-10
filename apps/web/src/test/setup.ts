import { vi } from "vitest";
import "@testing-library/jest-dom";

// Mock next/navigation globally so components importing useRouter don't crash.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));
