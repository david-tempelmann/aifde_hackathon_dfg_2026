// App mark for "Outreach": a central hub reaching out and connecting to partner
// nodes (growing CarePortal partnerships), in the CarePortal palette. Reusable.
export default function Logo({ size = 34, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      role="img"
      aria-label="Outreach Signals"
      className={className}
    >
      <defs>
        <linearGradient id="osLogoGrad" x1="4" y1="2" x2="36" y2="38" gradientUnits="userSpaceOnUse">
          <stop stopColor="#0a8ac9" />
          <stop offset="1" stopColor="#05496b" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="11" fill="url(#osLogoGrad)" />
      {/* connections from the hub out to partner nodes */}
      <g stroke="#ffffff" strokeWidth="2" strokeLinecap="round" opacity="0.92">
        <line x1="20" y1="20" x2="11" y2="12" />
        <line x1="20" y1="20" x2="29" y2="13" />
        <line x1="20" y1="20" x2="21" y2="31" />
      </g>
      {/* partner nodes */}
      <g fill="#ffffff">
        <circle cx="11" cy="12" r="2.6" />
        <circle cx="29" cy="13" r="2.6" />
        <circle cx="21" cy="31" r="2.6" />
      </g>
      {/* the hub */}
      <circle cx="20" cy="20" r="4.2" fill="#ff6129" />
    </svg>
  );
}
