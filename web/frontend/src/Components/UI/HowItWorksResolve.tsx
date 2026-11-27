"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Icon } from "../Icons";
import { GlowEffect } from "./GlowEffect";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface ResolveItem {
  question: string;
  answer: string;
}
export interface ResolveProps {
  items?: ResolveItem[];
  initialOpenIndex?: number;
  heading?: string;
  description?: string;
}

const defaultItems: ResolveItem[] = [
  { question: "Do I need the web dashboard to use Lemegeton?", answer: "No. Discord is the primary member interface. The dashboard is optional and gives authorised server managers a browser-based control plane for supported configuration and operational views." },
  { question: "Can one Discord server see another server’s data?", answer: "Guild-owned settings, archives and community records are scoped to their server. Shared provider catalogue metadata is separate from private guild configuration and submissions. Authorization is checked again when a protected action is performed." },
  { question: "What happens when the dashboard changes a setting?", answer: "The browser is not trusted to authorize a change. Rust/Axum validates the session, request origin and guild permissions. Actions that must be performed by the running bot use its private bridge." },
  { question: "Where does Lemegeton store information?", answer: "The bot and dashboard use the same libSQL database for structured records and metadata. Private binary objects, such as stored media and custom-role images, use the RocksDB object store." },
  { question: "Are all listed providers enabled on every deployment?", answer: "No. Provider availability depends on the category, the source and the operator’s configuration. Optional integrations can require credentials. Results keep their source and provenance." },
  { question: "Where should I report a bug?", answer: "Open a GitHub issue and include the affected command or page, what you expected, what happened, and the relevant non-sensitive diagnostic reference. Never include tokens, passwords or private server data." },
];

export function Resolve({
  items = defaultItems,
  initialOpenIndex = 0,
  heading = "Frequently asked questions",
  description = "How Lemegeton works, where authority lives and how its data boundaries work.",
}: ResolveProps) {
  const [active, setActive] = useState<number | null>(initialOpenIndex);
  const reducedMotion = useReducedMotion();

  return (
    <div className="hiw-resolve">
      <div className="hiw-resolve-aside">
        <div className="hiw-resolve-mark">
          <GlowEffect className="hiw-glow-layer" colors={["#fff", "#555", "#fff"]} mode="pulse" blur="medium" duration={6} />
          <span><Icon name="shield-check" size={22} /></span>
        </div>
        <h3>{heading}</h3>
        <p>{description}</p>
        <a className="hiw-text-link" href="/issues" target="_blank" rel="noreferrer">Report an issue <Icon name="arrow-up-right" size={13} /></a>
      </div>
      <div className="hiw-resolve-list">
        {items.map((item, index) => {
          const open = active === index;
          return <article className={"hiw-resolve-item " + (open ? "is-open" : "")} key={item.question}>
            <button type="button" aria-expanded={open} aria-controls={"hiw-resolve-answer-" + index} onClick={() => setActive(open ? null : index)}>
              <span>{item.question}</span><Icon name={open ? "close" : "chevron-down"} size={16} />
            </button>
            <AnimatePresence initial={false}>
              {open ? <motion.div id={"hiw-resolve-answer-" + index} className="hiw-resolve-answer"
                initial={reducedMotion ? false : { height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: reducedMotion ? 0 : .28, ease: "easeOut" }}>
                <p>{item.answer}</p>
              </motion.div> : null}
            </AnimatePresence>
          </article>;
        })}
      </div>
    </div>
  );
}
