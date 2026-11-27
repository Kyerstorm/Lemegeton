"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { BrandMark } from "../../Brand/BrandMark";
import { Icon } from "../../Icons";
import { useReducedMotion } from "../../Hooks/useReducedMotion";

const links = [
  { label: "How it works", href: "/how-it-works", current: true },
  { label: "System status", href: "/status" },
  { label: "GitHub", href: "/github", external: true },
];

export function HowItWorksNavigation() {
  const [open, setOpen] = useState(false);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  return (
    <header className="hiw-nav">
      <a className="hiw-brand" href="/login" aria-label="Lemegeton dashboard sign-in">
        <BrandMark size={32} />
        <span><strong>LEMEGETON</strong><small>COMMUNITY SYSTEMS</small></span>
      </a>
      <nav className="hiw-nav-links" aria-label="Main navigation">
        {links.map((link) => (
          <a key={link.href} className={link.current ? "is-current" : ""} href={link.href}
            target={link.external ? "_blank" : undefined} rel={link.external ? "noreferrer" : undefined}>
            {link.label}{link.external ? <Icon name="arrow-up-right" size={12} /> : null}
          </a>
        ))}
      </nav>
      <a className="hiw-nav-cta" href="/login">Dashboard <Icon name="arrow-up-right" size={13} /></a>
      <button className="hiw-mobile-menu-button" type="button" aria-label={open ? "Close navigation" : "Open navigation"}
        aria-expanded={open} aria-controls="hiw-mobile-menu" onClick={() => setOpen((value) => !value)}>
        <Icon name={open ? "close" : "menu"} size={20} />
      </button>
      <AnimatePresence>
        {open ? (
          <motion.nav id="hiw-mobile-menu" className="hiw-mobile-menu" aria-label="Mobile navigation"
            initial={reducedMotion ? false : { opacity: 0, clipPath: "inset(0 0 100% 0)" }}
            animate={{ opacity: 1, clipPath: "inset(0 0 0% 0)" }}
            exit={reducedMotion ? undefined : { opacity: 0, clipPath: "inset(0 0 100% 0)" }}
            transition={{ duration: reducedMotion ? 0 : 0.42, ease: [0.2, 0.8, 0.2, 1] }}>
            <div className="hiw-mobile-menu-top"><span>LEMEGETON / NAVIGATION</span><button type="button" onClick={() => setOpen(false)} aria-label="Close navigation"><Icon name="close" size={19} /></button></div>
            {links.map((link, index) => (
              <motion.a key={link.href} href={link.href} target={link.external ? "_blank" : undefined}
                rel={link.external ? "noreferrer" : undefined} onClick={() => setOpen(false)}
                initial={reducedMotion ? false : { opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: reducedMotion ? 0 : index * 0.07, duration: reducedMotion ? 0 : 0.42 }}>
                <span>{link.label}</span><Icon name="arrow-up-right" size={18} />
              </motion.a>
            ))}
            <a className="hiw-mobile-menu-dashboard" href="/login" onClick={() => setOpen(false)}>Open dashboard <Icon name="arrow-up-right" size={15} /></a>
          </motion.nav>
        ) : null}
      </AnimatePresence>
    </header>
  );
}
