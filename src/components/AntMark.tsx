export function AntMark({ className = "w-10 h-10" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      className={className}
      aria-hidden="true"
    >
      <ellipse
        cx="32"
        cy="42"
        rx="10"
        ry="15"
        transform="rotate(28 32 42)"
        fill="currentColor"
      />
      <ellipse cx="32" cy="25" rx="7" ry="8" fill="currentColor" />
      <circle cx="36" cy="12" r="6" />
      <path d="m32 7-4-5m12 5 5-4M24 29l-12-4-7 6m19 6-14 5-3 9m18-7-8 10v6m23-32 12 1 7-6M42 36l11 8 6-1M40 46l7 10-2 5" />
    </svg>
  );
}
