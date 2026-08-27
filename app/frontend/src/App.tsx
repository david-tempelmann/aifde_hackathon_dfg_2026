import { NavLink, Outlet } from "react-router-dom";
import { LayoutGrid, Radar } from "lucide-react";
import goLogo from "./assets/go-project-logo.svg";

function NavItem({ to, icon, label }: { to: string; icon: React.ReactNode; label: string }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        `inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition ${
          isActive
            ? "bg-accent-50 text-accent-700"
            : "text-navy-400 hover:bg-brand-50 hover:text-navy"
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
      <header className="sticky top-0 z-10 border-b border-black/5 bg-canvas/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1536px] items-center gap-4 px-6 py-3">
          <div className="flex items-center gap-3">
            <img src={goLogo} alt="Global Orphan Project" className="h-8 w-auto" />
            <span className="hidden h-8 w-px bg-navy/15 sm:block" />
            <div className="leading-tight">
              <div className="text-sm font-bold tracking-tight text-navy">Outreach Signals</div>
              <div className="text-[11px] font-medium text-navy-400">
                Growing <span className="text-accent-600">CarePortal</span> partnerships through timely intel
              </div>
            </div>
          </div>
          <nav className="ml-6 flex items-center gap-1">
            <NavItem to="/" icon={<Radar className="h-4 w-4" />} label="Signals" />
            <NavItem to="/overview" icon={<LayoutGrid className="h-4 w-4" />} label="Overview" />
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-[1536px] px-6 py-6">
        <Outlet />
      </main>
    </div>
  );
}
