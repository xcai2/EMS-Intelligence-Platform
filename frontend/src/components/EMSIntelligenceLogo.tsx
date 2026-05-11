interface EMSIntelligenceLogoProps {
  size?: number;
  className?: string;
}

export function EMSIntelligenceLogo({ size = 32, className = "" }: EMSIntelligenceLogoProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 72 72"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="EMS Intelligence logo"
      role="img"
    >
      {/* Chamber: beveled square with two opposite corners cut */}
      <path d="M 14 0 L 72 0 L 72 58 L 58 72 L 0 72 L 0 14 Z" fill="#A78BFA" />

      {/* Letter E: three horizontal bars + left spine, middle bar shorter for design rhythm */}
      <rect x="14" y="18" width="22" height="6" fill="#0B0F1A" />
      <rect x="14" y="33" width="16" height="6" fill="#0B0F1A" />
      <rect x="14" y="48" width="22" height="6" fill="#0B0F1A" />
      <rect x="14" y="18" width="6" height="36" fill="#0B0F1A" />

      {/* Letter I: stem only, dot replaced by the sparkle above */}
      <rect x="49" y="32" width="6" height="22" fill="#0B0F1A" />

      {/* Main sparkle: four-point concave star, replaces the I-dot */}
      <path
        d="M 52 14 L 54.5 20 L 60 22 L 54.5 24 L 52 30 L 49.5 24 L 44 22 L 49.5 20 Z"
        fill="#F59E0B"
      />

      {/* Twinkle: smaller accent star in the top-right corner */}
      <path
        d="M 63 9 L 63.6 10.5 L 65 11 L 63.6 11.5 L 63 13 L 62.4 11.5 L 61 11 L 62.4 10.5 Z"
        fill="#F59E0B"
        opacity="0.65"
      />
    </svg>
  );
}
