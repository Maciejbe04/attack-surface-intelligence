type LogoProps = {
  compact?: boolean;
  className?: string;
};

/**
 * Four-wedge geometric X (cross negative space), HexStrike-like mark.
 * Colors: #FFCC00 on dark UI chrome.
 */
export function LogoMark({ className = "" }: { className?: string }) {
  return (
    <svg
      className={className}
      width="30"
      height="30"
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      {/* Top wedge */}
      <polygon points="18,2 32,22 46,2 38,2 32,12 26,2" fill="#FFCC00" />
      {/* Right wedge */}
      <polygon points="62,18 42,32 62,46 62,38 52,32 62,26" fill="#FFCC00" />
      {/* Bottom wedge */}
      <polygon points="18,62 32,42 46,62 38,62 32,52 26,62" fill="#FFCC00" />
      {/* Left wedge */}
      <polygon points="2,18 22,32 2,46 2,38 12,32 2,26" fill="#FFCC00" />
    </svg>
  );
}

export function Logo({ compact = false, className = "" }: LogoProps) {
  return (
    <span className={`brand-logo ${compact ? "brand-logo--compact" : ""} ${className}`.trim()}>
      <LogoMark className="brand-logo__mark" />
      {!compact && (
        <span className="brand-logo__word" aria-label="SurfaceX">
          <span className="brand-logo__surface">Surface</span>
          <span className="brand-logo__x">X</span>
        </span>
      )}
    </span>
  );
}
