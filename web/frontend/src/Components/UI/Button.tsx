import type { ButtonHTMLAttributes, ReactNode } from "react";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  tone?: "primary" | "secondary" | "quiet";
  children?: ReactNode;
}

export function Button({ tone = "secondary", className, children, ...props }: ButtonProps) {
  return (
    <button
      {...props}
      className={"button " + tone + (className ? " " + className : "")}
    >
      {children}
    </button>
  );
}
