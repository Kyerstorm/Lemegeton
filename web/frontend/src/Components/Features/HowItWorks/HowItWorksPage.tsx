"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";
import { Icon } from "../../Icons";
import { useReducedMotion } from "../../Hooks/useReducedMotion";
import { HowItWorksNavigation } from "./HowItWorksNavigation";
import {
  BrandLoop,
  BranchFlow,
  Converge,
  DataFlow,
  Flowlist,
  FluxCTA,
  HowItWorksSignature,
  LaunchHero,
  Nexus,
  Origin,
  PathFlow,
  Pipeline,
  Resolve,
  ScrollProgress,
  SpotlightGrid,
  Stream,
} from "../../UI";

function Reveal({ children, className = "", delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  const reducedMotion = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reducedMotion ? false : { opacity: 0, y: 18, filter: "blur(5px)" }}
      whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      viewport={{ once: true, amount: 0.14, margin: "0px 0px -35px 0px" }}
      transition={{ duration: reducedMotion ? 0 : 0.62, ease: [0.2, 0.8, 0.2, 1], delay: reducedMotion ? 0 : delay }}
    >
      {children}
    </motion.div>
  );
}

function SectionHeading({ index, eyebrow, title, copy }: { index: string; eyebrow: string; title: string; copy: string }) {
  return (
    <div className="hiw-section-heading">
      <span className="hiw-index">{index}</span>
      <div>
        <p className="hiw-eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
        <p className="hiw-section-copy">{copy}</p>
      </div>
    </div>
  );
}

export function HowItWorksPage() {
  return (
    <main className="hiw-page">
      <div className="hiw-progress"><ScrollProgress /></div>
      <HowItWorksNavigation />

      <section className="hiw-hero">
        <SpotlightGrid />
        <PathFlow />
        <LaunchHero
          title="More than a bot."
          emphasis="A connected system."
          description="Lemegeton brings media discovery, shared archives and community activities into Discord — with an optional dashboard for authorised server managers."
          primaryLabel="Explore the architecture"
          primaryHref="#architecture"
          secondaryLabel="View source"
          secondaryHref="/github"
        />
        <div className="hiw-hero-bottom"><span>LEMEGETON / SYSTEMS GUIDE</span><span>SCROLL TO EXPLORE <Icon name="chevron-down" size={12} /></span></div>
      </section>

      <section className="hiw-section hiw-activities" id="overview">
        <SectionHeading index="01" eyebrow="THE PRODUCT" title="Three connected ways to take part." copy="Lemegeton is built around participation. Discovery finds the media, archives preserve what a community shares, and activities give members a reason to return." />
        <div className="hiw-activity-grid">
          {[
            { index: "01", title: "Discover", text: "Look up supported media, compare records and explore connections across categories.", icon: "search" as const },
            { index: "02", title: "Share", text: "Contribute to community archives, organise collections and keep source attribution visible.", icon: "archive" as const },
            { index: "03", title: "Participate", text: "Join recurring activities, rankings, sessions, tournaments and group games.", icon: "activity" as const },
          ].map((item, index) => (
            <Reveal className="hiw-activity-card" key={item.title} delay={index * 0.08}>
              <span className="hiw-card-index">{item.index}</span>
              <span className="hiw-activity-icon"><Icon name={item.icon} size={20} /></span>
              <h3>{item.title}</h3>
              <p>{item.text}</p>
              <span className="hiw-card-rule" />
            </Reveal>
          ))}
        </div>
      </section>

      <section className="hiw-section hiw-architecture" id="architecture">
        <SectionHeading index="02" eyebrow="THE BOT RUNTIME" title="One runtime. Multiple servers." copy="Discord interactions enter one discord.js client. The command registry dispatches each request to a feature handler, while shared helpers, integrations and storage do the work behind it." />
        <Reveal>
          <div className="hiw-diagram-frame">
            <div className="hiw-diagram-topline"><span>FIG. 01 / REQUEST & DATA FLOW</span><span>REACTVIBE · DATA FLOW</span></div>
            <DataFlow />
          </div>
        </Reveal>
        <div className="hiw-two-column">
          <div>
            <p className="hiw-eyebrow">FROM INTERACTION TO RESPONSE</p>
            <Flowlist />
          </div>
          <div className="hiw-side-note">
            <span className="hiw-note-icon"><Icon name="shield-check" size={20} /></span>
            <p className="hiw-eyebrow">MULTI-GUILD BOUNDARIES</p>
            <h3>Server-owned data stays scoped.</h3>
            <p>Guild configuration, community records and private submissions are scoped to the invoking server. Shared catalogue metadata is kept distinct from guild-owned data.</p>
            <p className="hiw-note-foot">Authorization is checked at the point of a protected action — not inferred from a hidden button.</p>
          </div>
        </div>
      </section>

      <section className="hiw-section hiw-commands" id="commands">
        <SectionHeading index="03" eyebrow="COMMAND ARCHITECTURE" title="A small surface. Deep feature environments." copy="Related actions live together instead of multiplying top-level commands. Each feature command opens the tools relevant to its own job." />
        <Reveal>
          <div className="hiw-branch-frame">
            <div className="hiw-diagram-topline"><span>FIG. 02 / COMMAND DISPATCH</span><span>REACTVIBE · BRANCH FLOW</span></div>
            <BranchFlow />
          </div>
        </Reveal>
        <div className="hiw-standalone">
          <span>STANDALONE COMMANDS</span>
          <p><code>/help</code> command guide <i /> <code>/privacy</code> privacy entry point <i /> <code>/feedback</code> feedback intake <i /> <code>/language</code> required server setup</p>
        </div>
      </section>

      <section className="hiw-section hiw-dashboard" id="dashboard">
        <SectionHeading index="04" eyebrow="OPTIONAL WEB DASHBOARD" title="A control plane — not a second bot." copy="The dashboard is a separate browser interface for authorised server managers. Its backend is the security boundary, and it shares the bot’s authoritative storage rather than creating a parallel database." />
        <div className="hiw-dashboard-grid">
          <Reveal className="hiw-dashboard-copy">
            <div className="hiw-diagram-topline"><span>FIG. 03 / DASHBOARD REQUEST PATH</span><span>REACTVIBE · PIPELINE</span></div>
            <Pipeline />
          </Reveal>
          <Reveal className="hiw-dashboard-aside">
            <div className="hiw-dashboard-mark"><Icon name="shield-check" size={24} /></div>
            <p className="hiw-eyebrow">SEPARATE RESPONSIBILITIES</p>
            <h3>Next.js presents.<br />Rust authorizes.</h3>
            <p>The browser never decides whether a user may manage a guild. OAuth, session validation, CSRF and origin checks, and guild authorization stay on the Rust/Axum side.</p>
            <a className="hiw-text-link" href="/login">Open dashboard sign-in <Icon name="arrow-up-right" size={13} /></a>
          </Reveal>
        </div>
        <Reveal>
          <div className="hiw-origin-frame">
            <div className="hiw-diagram-topline"><span>FIG. 04 / SERVICE FAN-OUT</span><span>REACTVIBE · ORIGIN</span></div>
            <Origin />
            <p className="hiw-diagram-note">The runtime coordinates shared helpers, provider integrations and the two storage layers. Each request uses only the path it needs.</p>
          </div>
        </Reveal>
      </section>

      <section className="hiw-section hiw-integrations" id="integrations">
        <SectionHeading index="05" eyebrow="PROVIDERS & DATA" title="Many sources. Clear provenance." copy="Provider-specific request logic stays at the integration boundary. Results remain attributed to their source, and similar titles are not silently promoted into confirmed adaptations or franchise links." />
        <Reveal>
          <div className="hiw-provider-frame">
            <div className="hiw-diagram-topline"><span>FIG. 05 / MEDIA PROVIDER CONVERGENCE</span><span>REACTVIBE · CONVERGE</span></div>
            <Converge />
          </div>
        </Reveal>
        <div className="hiw-storage-grid">
          <Reveal className="hiw-storage-card">
            <span className="hiw-node-icon"><Icon name="database" size={19} /></span>
            <p className="hiw-eyebrow">STRUCTURED DATA</p>
            <h3>Shared libSQL</h3>
            <p>Guild configuration, command settings, profiles, archive/community records, sessions and related metadata.</p>
          </Reveal>
          <Reveal className="hiw-storage-card">
            <span className="hiw-node-icon"><Icon name="server" size={19} /></span>
            <p className="hiw-eyebrow">PRIVATE OBJECTS</p>
            <h3>RocksDB object store</h3>
            <p>Binary objects such as stored media and custom-role images. Ownership and authorization metadata stay in libSQL.</p>
          </Reveal>
        </div>
        <Reveal>
          <div className="hiw-stream-frame">
            <div className="hiw-diagram-topline"><span>FIG. 06 / CONNECTED STACK</span><span>REACTVIBE · STREAM</span></div>
            <Stream className="hiw-stream-provider" density={6} />
            <BrandLoop items={["TypeScript", "discord.js", "Next.js", "React", "Rust", "Axum", "libSQL", "RocksDB"]} />
          </div>
        </Reveal>
      </section>

      <section className="hiw-section hiw-atlas-section" id="atlas">
        <SectionHeading index="06" eyebrow="KNOWLEDGE ATLAS" title="Explore relationships, not just titles." copy="The Knowledge Atlas is part of /discover. It presents source-backed and community-reviewed connections while keeping relationship types and evidence distinguishable." />
        <Reveal>
          <div className="hiw-atlas-frame">
            <div className="hiw-diagram-topline"><span>FIG. 07 / RELATIONSHIP EXPLORATION</span><span>REACTVIBE · NEXUS</span></div>
            <Nexus />
            <p className="hiw-diagram-note">Illustrative network only. Live relationships depend on returned metadata, evidence and community-reviewed records.</p>
          </div>
        </Reveal>
      </section>

      <section className="hiw-section hiw-faq" id="faq">
        <SectionHeading index="08" eyebrow="CLARITY & TRUST" title="A few useful details." copy="What the system does, where authority lives and how its data boundaries work." />
        <Resolve />
      </section>

      <FluxCTA
        title="Understand the system."
        emphasis="Help make it better."
        description="Explore the code, review the documentation or report a reproducible issue through GitHub."
        primaryLabel="Explore GitHub"
        primaryHref="/github"
        secondaryLabel="Report an issue"
        secondaryHref="/issues"
      />
      <HowItWorksSignature />
    </main>
  );
}
