export function Logo({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-2 font-serif text-2xl font-semibold tracking-tight text-ink ${className}`}
    >
      <svg
        width="26"
        height="26"
        viewBox="0 0 26 26"
        fill="none"
        aria-hidden="true"
      >
        <circle cx="13" cy="13" r="12" stroke="#c2683f" strokeWidth="1.5" />
        <path
          d="M13 4c3 3 4 6 4 9s-1 6-4 9c-3-3-4-6-4-9s1-6 4-9z"
          fill="#c2683f"
          opacity="0.9"
        />
        <circle cx="13" cy="13" r="2" fill="#faf6f0" />
      </svg>
      lumora
    </span>
  );
}
