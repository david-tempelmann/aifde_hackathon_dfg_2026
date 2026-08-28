import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Home, Radar, Telescope } from "lucide-react";
import { fetchStats } from "./api";
import goLogo from "./assets/go-project-logo.svg";
import outreachLogo from "./assets/outreach-logo.png";

function HeaderStats() {
  const [total, setTotal] = useState<number | null>(null);

  useEffect(() => {
    fetchStats().then((s) => setTotal(s.total)).catch(() => setTotal(null));
  }, []);

  if (total == null) return null;

  return (
    <div className="ml-auto flex items-center gap-2">
      {/* Pulsing green dot to signal the feed is live/up to date. */}
      <span className="relative flex h-2.5 w-2.5" aria-hidden>
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
      </span>
      <div className="leading-tight">
        <span className="text-lg font-extrabold text-navy">{total.toLocaleString()}</span>
        <span className="ml-1 text-xs font-medium text-navy-400">signals</span>
      </div>
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
            ? "bg-accent-50 text-accent-700 shadow-sm ring-1 ring-accent-100"
            : "text-navy-500 hover:bg-white/60 hover:text-navy"
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
      {/* Colourful shapes fixed behind the header so the frosted glass has
          something to diffuse (the effect is invisible over a plain page). */}
      <div aria-hidden className="pointer-events-none fixed inset-x-0 top-0 z-0 h-16 overflow-hidden">
        <div className="absolute -top-10 left-[4%] h-32 w-80 rounded-full bg-brand-500/60 blur-2xl" />
        <div className="absolute -top-12 left-[40%] h-32 w-80 rounded-full bg-accent-500/50 blur-2xl" />
        <div className="absolute -top-10 right-[6%] h-32 w-72 rounded-full bg-gold-400/50 blur-2xl" />
      </div>
      <header className="sticky top-0 z-10 border-b border-black/5 bg-white/60 shadow-sm backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1536px] items-center gap-4 px-6 py-3">
          <div className="flex items-center gap-3">
            <img src={goLogo} alt="Global Orphan Project" className="h-8 w-auto" />
            <span className="hidden h-8 w-px bg-navy/15 sm:block" />
            <img src={outreachLogo} alt="Outreach Signals" className="h-9 w-9 rounded-[10px] object-cover shadow-sm" />
            <div className="leading-tight">
              <div className="text-sm font-bold tracking-tight text-navy">Outreach Signals</div>
              <div className="text-[11px] font-medium text-navy-400">
                Growing <span className="font-semibold text-accent-600">CarePortal</span> partnerships through timely intel
              </div>
            </div>
          </div>
          <nav className="ml-6 flex items-center gap-1">
            <NavItem to="/" icon={<Home className="h-4 w-4" />} label="Home" />
            <NavItem to="/signals" icon={<Radar className="h-4 w-4" />} label="Signals" />
            <NavItem to="/deep-dive" icon={<Telescope className="h-4 w-4" />} label="Deep Dive" />
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
