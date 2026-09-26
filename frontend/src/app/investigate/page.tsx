import { redirect } from "next/navigation";

export default function LegacyInvestigatePage() {
  redirect("/cases/new");
}
