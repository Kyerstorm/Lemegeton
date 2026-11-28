import { LogoTraceLoader } from "../UI/LogoTraceLoader";

export interface BrandMarkProps {
  size?: number;
}

export function BrandMark({ size = 29 }: BrandMarkProps) {
  return (
    <span className="brand-mark">
      <LogoTraceLoader
        size={size}
        strokeWidth={Math.max(1, size * 0.48)}
        loading={false}
        isComplete
        ariaLabel="Lemegeton logo"
      />
    </span>
  );
}
