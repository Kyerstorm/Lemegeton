import type { ButtonHTMLAttributes, ReactNode } from "react";
import { GlowEffect } from "./GlowEffect";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  tone?: "primary" | "secondary" | "quiet";
  children?: ReactNode;
}

export function Button({ tone = "secondary", className, children, type = "button", ...props }: ButtonProps) {
  return (
    <button
      {...props}
      type={type}
      className={"button " + tone + (className ? " " + className : "")}
    >
      {tone === "primary" ? <GlowEffect className="button-glow" colors={["#fff", "#777", "#fff"]} mode="rotate" blur="medium" duration={10} scale={1.04} /> : null}
      <span className="button-content">{children}</span>
    </button>
  );
}
