import {
  Activity,
  Bell,
  Briefcase,
  FlaskConical,
  History,
  LayoutDashboard,
  Layers,
  LineChart,
  Newspaper,
  NotebookPen,
  Receipt,
  Settings,
  Star,
  Target,
  TestTubeDiagonal,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

export const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Research",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/market", label: "Market", icon: Activity },
      { href: "/opportunities", label: "Opportunities", icon: Target },
      { href: "/stocks", label: "Stocks", icon: LineChart },
      { href: "/news", label: "News", icon: Newspaper },
      { href: "/fno", label: "F&O", icon: Layers },
    ],
  },
  {
    label: "Portfolio",
    items: [
      { href: "/portfolio", label: "Portfolio", icon: Briefcase },
      { href: "/paper", label: "Paper trading", icon: FlaskConical },
      { href: "/trades", label: "Trade journal", icon: NotebookPen },
      { href: "/watchlist", label: "Watchlists", icon: Star },
      { href: "/alerts", label: "Alerts", icon: Bell },
      { href: "/tax", label: "Tax Center", icon: Receipt },
    ],
  },
  {
    label: "Analytics",
    items: [
      { href: "/recommendations", label: "Track record", icon: History },
      { href: "/performance", label: "Performance", icon: TrendingUp },
      { href: "/backtesting", label: "Backtesting", icon: TestTubeDiagonal },
    ],
  },
  {
    label: "System",
    items: [{ href: "/settings", label: "Settings", icon: Settings }],
  },
];

export const MOBILE_PRIMARY = ["/dashboard", "/opportunities", "/portfolio", "/stocks"];

export const ALL_NAV: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);

export function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
