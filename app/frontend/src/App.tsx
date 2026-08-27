import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { ArrowUp, LayoutGrid, Radar } from "lucide-react";
import { fetchStats } from "./api";
import goLogo from "./assets/go-project-logo.svg";

function HeaderStats() {
  const [stats, setStats] = useState<{ total: number; since_yesterday: number | null } | null>(null);

  useEffect(() => {
    fetchStats().then(setStats).catch(() => setStats(null));
  }, []);

  if (!stats) return null;
  const up = stats.since_yesterday;

  return (
    <div className="ml-auto flex items-center gap-4">
      <div className="text-right leading-tight">
        <div className="text-lg font-extrabold text-white">{stats.total.toLocaleString()}</div>
        <div className="text-[11px] font-medium uppercase tracking-wide text-white/70">Signals</div>
      </div>
      {up != null && up > 0 && (
        <div className="inline-flex items-center gap-1 rounded-full bg-emerald-400/20 px-2.5 py-1 text-xs font-semibold text-emerald-200 ring-1 ring-emerald-300/30">
          <ArrowUp className="h-3.5 w-3.5" />
          {up} since yesterday
        </div>
      )}
    </div>
  );
}

function NavItem({ to, icon, label }: { to: string; icon: React.ReactNode; label: string }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        `inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition ${
          isActive
            ? "bg-white/15 text-white"
            : "text-white/70 hover:bg-white/10 hover:text-white"
        }`
      }
    >
      {icon}
      {label}
    </NavLink>
  );
}

export default function App() {
  return (
    <div className="min-h-full">
      {/* Thin CarePortal-orange rule at the very top as a brand cue. */}
      <div className="h-1 w-full bg-accent-500" />
      <header className="sticky top-0 z-10 border-b border-white/10 bg-gradient-to-r from-navy to-brand-600 text-white shadow-sm">
        <div className="mx-auto flex max-w-[1536px] items-center gap-4 px-6 py-3">
          <div className="flex items-center gap-3">
            <span className="flex items-center rounded-md bg-white px-2 py-1 shadow-sm">
              <img src={goLogo} alt="Global Orphan Project" className="h-6 w-auto" />
            </span>
            <span className="hidden h-8 w-px bg-white/25 sm:block" />
            <div className="leading-tight">
              <div className="text-sm font-bold tracking-tight text-white">Outreach Signals</div>
              <div className="text-[11px] font-medium text-white/70">
                Growing <span className="font-semibold text-accent-500">CarePortal</span> partnerships through timely intel
              </div>
            </div>
          </div>
          <nav className="ml-6 flex items-center gap-1">
            <NavItem to="/" icon={<Radar className="h-4 w-4" />} label="Signals" />
            <NavItem to="/overview" icon={<LayoutGrid className="h-4 w-4" />} label="Overview" />
          </nav>
          <HeaderStats />
        </div>
      </header>
      <main className="mx-auto max-w-[1536px] px-6 py-6">
        <Outlet />
      </main>
    </div>
  );
}
