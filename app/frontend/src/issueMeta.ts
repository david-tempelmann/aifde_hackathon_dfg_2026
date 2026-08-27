import {
  Home,
  Users,
  ShieldAlert,
  Brain,
  HandCoins,
  Utensils,
  GraduationCap,
  Siren,
  Tag,
  type LucideIcon,
} from "lucide-react";

// Map an issue label to a representative icon (keyword match, with a fallback),
// so the feed is scannable and less text-heavy.
export function issueIcon(label: string | null | undefined): LucideIcon {
  const l = (label ?? "").toLowerCase();
  if (l.includes("housing") || l.includes("homeless") || l.includes("eviction") || l.includes("shelter")) return Home;
  if (l.includes("foster") || l.includes("family") || l.includes("kinship") || l.includes("reunif")) return Users;
  if (l.includes("welfare") || l.includes("protection") || l.includes("cps") || l.includes("abuse") || l.includes("neglect")) return ShieldAlert;
  if (l.includes("mental") || l.includes("youth") || l.includes("crisis")) return Brain;
  if (l.includes("poverty") || l.includes("economic") || l.includes("benefit") || l.includes("tax") || l.includes("cash")) return HandCoins;
  if (l.includes("food") || l.includes("material") || l.includes("hunger") || l.includes("nutrition")) return Utensils;
  if (l.includes("education") || l.includes("school") || l.includes("student")) return GraduationCap;
  if (l.includes("emergency") || l.includes("disaster") || l.includes("displace")) return Siren;
  return Tag;
}
