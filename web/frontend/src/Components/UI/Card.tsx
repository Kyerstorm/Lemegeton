import type { ReactNode } from "react";

export interface CardProps {
  eyebrow?: string;
  title: string;
  index?: string;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function Card({ eyebrow, title, index, action, className, children }: CardProps) {
  return (
    <article className={"panel " + (className || "")}>
      {eyebrow || index || action ? (
        <div className="panel-heading">
          <div>
            {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
            <h2>{title}</h2>
          </div>
          {action || (index ? <span className="panel-index">{index}</span> : null)}
        </div>
      ) : (
        <div className="panel-heading"><h2>{title}</h2></div>
      )}
      {children}
    </article>
  );
}
