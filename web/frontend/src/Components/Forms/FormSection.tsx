import type { ReactNode } from "react";

export function FormSection({ title, description, children, className }: {
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={["form-section", className].filter(Boolean).join(" ")}>
      <div className="form-section-heading">
        <h3>{title}</h3>
        {description ? <p>{description}</p> : null}
      </div>
      {children}
    </section>
  );
}
