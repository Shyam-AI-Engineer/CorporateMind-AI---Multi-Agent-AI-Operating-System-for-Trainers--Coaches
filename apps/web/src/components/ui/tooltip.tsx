"use client";

import React, { createContext, useContext, useRef, useState } from "react";
import { cn } from "@/lib/utils";

// ── Context ────────────────────────────────────────────────────────────────────

interface TooltipCtx {
  open: boolean;
  setOpen: (v: boolean) => void;
  triggerRef: React.RefObject<HTMLElement | null>;
}

const Ctx = createContext<TooltipCtx | null>(null);

function useTooltip() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("Tooltip components must be used inside <Tooltip>");
  return ctx;
}

// ── TooltipProvider (no-op wrapper — satisfies import sites) ──────────────────

export function TooltipProvider({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

// ── Tooltip ───────────────────────────────────────────────────────────────────

export function Tooltip({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLElement | null>(null);
  return <Ctx.Provider value={{ open, setOpen, triggerRef }}>{children}</Ctx.Provider>;
}

// ── TooltipTrigger ────────────────────────────────────────────────────────────

interface TriggerProps {
  children: React.ReactElement;
  asChild?: boolean;
}

export function TooltipTrigger({ children, asChild = false }: TriggerProps) {
  const { setOpen, triggerRef } = useTooltip();

  const handlers = {
    onMouseEnter: () => setOpen(true),
    onMouseLeave: () => setOpen(false),
    onFocus: () => setOpen(true),
    onBlur: () => setOpen(false),
  };

  if (asChild && React.isValidElement(children)) {
    return React.cloneElement(children as React.ReactElement<Record<string, unknown>>, {
      ...handlers,
      ref: triggerRef,
    });
  }

  return (
    <span ref={triggerRef as React.RefObject<HTMLSpanElement>} {...handlers} style={{ display: "inline-flex" }}>
      {children}
    </span>
  );
}

// ── TooltipContent ────────────────────────────────────────────────────────────

interface ContentProps {
  children?: React.ReactNode;
  className?: string;
  side?: "top" | "right" | "bottom" | "left";
  sideOffset?: number;
}

export function TooltipContent({
  children,
  className,
}: ContentProps) {
  const { open } = useTooltip();

  if (!open) return null;

  return (
    <div
      role="tooltip"
      className={cn(
        "absolute z-50 rounded-md bg-popover px-3 py-1.5 text-xs text-popover-foreground shadow-md",
        "border border-border",
        className
      )}
    >
      {children}
    </div>
  );
}
