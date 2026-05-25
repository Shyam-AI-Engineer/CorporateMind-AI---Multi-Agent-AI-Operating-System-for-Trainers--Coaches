import { redirect } from "next/navigation";

export default function RootPage() {
  // Redirect to dashboard (auth guard in middleware)
  redirect("/dashboard");
}
