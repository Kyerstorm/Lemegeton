"use client";

import { motion } from "motion/react";
import { Icon, type IconName } from "../Icons";
import { useReducedMotion } from "../Hooks/useReducedMotion";

export interface ConvergeSource {
  id: string;
  title: string;
  detail: string;
  icon: IconName;
}
export interface ConvergeProps {
  sources?: ConvergeSource[];
  centerTitle?: string;
  centerDetail?: string;
  outputTitle?: string;
  outputDetail?: string;
}

const sourceDefaults: ConvergeSource[] = [
  { id: "anime", title: "Anime & manga", detail: "AniList · Kitsu · MangaDex", icon: "search" },
  { id: "books", title: "Books & novels", detail: "Google Books · Open Library", icon: "archive" },
  { id: "webnovels", title: "Webnovels", detail: "Supported public catalogues", icon: "home" },
  { id: "film", title: "Film & television", detail: "TMDB", icon: "activity" },
  { id: "games", title: "Video games", detail: "IGDB · Steam", icon: "server" },
  { id: "music", title: "Music", detail: "MusicBrainz · Last.fm · setlist.fm", icon: "integrations" },
];

export function Converge({
  sources = sourceDefaults,
  centerTitle = "Provider-specific helpers",
  centerDetail = "Normalised records with source provenance",
  outputTitle = "Source-aware results",
  outputDetail = "Relationships are not guessed",
}: ConvergeProps) {
  const reducedMotion = useReducedMotion();
  return (
    <div className="hiw-converge">
      <div className="hiw-converge-sources">
        {sources.map((source, index) => <motion.article key={source.id} className="hiw-converge-source"
          initial={reducedMotion ? false : { opacity: 0, x: -12 }} whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, amount: .2 }} transition={{ duration: reducedMotion ? 0 : .55, delay: reducedMotion ? 0 : index * .05 }}>
          <span className="hiw-node-icon"><Icon name={source.icon} size={16} /></span><span><strong>{source.title}</strong><small>{source.detail}</small></span>
        </motion.article>)}
      </div>
      <div className="hiw-converge-wires" aria-hidden="true">
        <svg viewBox="0 0 1000 420" preserveAspectRatio="none">
          {sources.map((source, index) => {
            const y = ((index + .5) / sources.length) * 420;
            const d = "M 0 " + y + " C 200 " + y + ", 300 210, 470 210";
            return <g key={source.id}>
              <motion.path d={d} fill="none" stroke="#777" strokeWidth="1.2" strokeDasharray="5 8"
                animate={reducedMotion ? undefined : { strokeDashoffset: [0, -70], opacity: [.2, .65, .2] }}
                transition={reducedMotion ? { duration: 0 } : { duration: 7 + index, repeat: Infinity, ease: "linear" }} />
              {!reducedMotion ? <circle r="3" fill="#eee"><animateMotion dur={(4 + index * .4) + "s"} repeatCount="indefinite" path={d} /></circle> : null}
            </g>;
          })}
          <path d="M 560 210 C 700 210, 760 210, 1000 210" fill="none" stroke="#777" strokeDasharray="4 8" strokeWidth="1.2" />
        </svg>
      </div>
      <div className="hiw-converge-core">
        <span className="hiw-node-icon"><Icon name="integrations" size={18} /></span><strong>{centerTitle}</strong><small>{centerDetail}</small>
      </div>
      <div className="hiw-converge-output"><span className="hiw-provider-dot" /><strong>{outputTitle}</strong><small>{outputDetail}</small></div>
      <p className="hiw-diagram-note">Coverage depends on category, provider availability and deployment credentials. Missing metadata stays missing.</p>
    </div>
  );
}
