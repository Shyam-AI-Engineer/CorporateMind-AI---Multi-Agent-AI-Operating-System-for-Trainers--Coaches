import type { Metadata } from "next";
import { CustomerCenter } from "@/features/customers/ui/customer-center";

export const metadata: Metadata = {
  title: "Customers — CorporateMind AI",
};

export default function CustomersRoute() {
  const workspaceId = "default";
  return <CustomerCenter workspaceId={workspaceId} />;
}
