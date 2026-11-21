import type { ReactNode } from "react";

export interface SectionHeadingProps {
  eyebrow: string;
  title: ReactNode;
  subtitle: string;
  actions?: ReactNode;
}

export function SectionHeading({ eyebrow, title, subtitle, actions }: SectionHeadingProps) {
  return (
    <div className="page-heading">
      <div className="page-heading-copy">
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="lede">{subtitle}</p>
      </div>
      {actions ? <div className="heading-actions">{actions}</div> : null}
    </div>
  );
}
