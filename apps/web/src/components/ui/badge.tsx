import { cn } from "@/lib/utils";

export type BadgeVariant = "default" | "secondary" | "success" | "warning" | "destructive" | "outline";

const variantClasses: Record<BadgeVariant, string> = {
  default: "bg-primary text-primary-foreground",
  secondary: "bg-secondary text-secondary-foreground",
  success: "bg-green-100 text-green-800",
  warning: "bg-amber-100 text-amber-800",
  destructive: "bg-destructive/10 text-destructive",
  outline: "border border-border bg-transparent text-foreground",
};

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        variantClasses[variant],
        className
      )}
      {...props}
    />
  );
}
