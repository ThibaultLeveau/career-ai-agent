export function BrandMark({ size = 32, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-hidden="true">
      <path d="M16 3v26M3 16h26M6.8 6.8l18.4 18.4M6.8 25.2 25.2 6.8" stroke="currentColor" strokeWidth="3.8" />
    </svg>
  );
}
