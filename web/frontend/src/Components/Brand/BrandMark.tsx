export interface BrandMarkProps { size?: number; }
export function BrandMark({size=29}:BrandMarkProps) {
 return <span className="brand-mark"><img src="/brand/lemegeton.svg" alt="" width={size} height={size}/></span>;
}
