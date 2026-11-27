"use client";

import { BrandMark } from "../Brand/BrandMark";
import { Icon } from "../Icons";

export interface SignatureProps {
  year?: number;
  description?: string;
}

export function Signature({
  year = new Date().getFullYear(),
  description = "A multi-guild Discord bot for media discovery, shared archives and community participation.",
}: SignatureProps) {
  const projectLinks = [
    { label: "How it works", href: "/how-it-works" },
    { label: "GitHub", href: "/github", external: true },
    { label: "Report an issue", href: "/issues", external: true },
    { label: "System status", href: "/status" },
    { label: "Dashboard", href: "/login" },
  ];
  const policyLinks = [
    { label: "Privacy policy", href: "/privacy-policy" },
    { label: "Terms of service", href: "/terms-of-service" },
    { label: "Community guidelines", href: "/community-guidelines" },
    { label: "Copyright complaints", href: "/copyright-complaints" },
  ];
  return (
    <footer className="hiw-signature">
      <div className="hiw-signature-main">
        <div className="hiw-signature-brand">
          <a className="hiw-brand" href="/login"><BrandMark size={34} /><span><strong>LEMEGETON</strong><small>DISCOVER · CONNECT · CREATE</small></span></a>
          <p>{description}</p>
          <span className="hiw-signature-note">A community tool. An open repository.</span>
        </div>
        <div className="hiw-signature-column"><strong>PROJECT</strong>
          {projectLinks.map((link) => <a key={link.href} href={link.href} target={link.external ? "_blank" : undefined} rel={link.external ? "noreferrer" : undefined}>{link.label}{link.external ? <Icon name="arrow-up-right" size={11} /> : null}</a>)}
        </div>
        <div className="hiw-signature-column"><strong>POLICIES</strong>
          {policyLinks.map((link) => <a key={link.href} href={link.href}>{link.label}</a>)}
        </div>
      </div>
      <div className="hiw-signature-bottom"><span>© {year} LEMEGETON / COMMUNITY SYSTEMS</span><span>BUILT WITH OPEN-SOURCE TECHNOLOGY</span><a href="#overview">BACK TO TOP ↑</a></div>
    </footer>
  );
}
