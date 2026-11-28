import { readFile } from "node:fs/promises";
import path from "node:path";
import type { ReactNode } from "react";
import { Icon } from "../../Icons/Icon";

type PolicyFilename =
  | "TERMS_OF_SERVICE.md"
  | "PRIVACY_POLICY.md"
  | "COMMUNITY_GUIDELINES.md"
  | "COPYRIGHT_AND_CONTENT_COMPLAINTS.md"
  | "DMCA.md";

const POLICY_ROUTES: Record<string, string> = {
  "TERMS_OF_SERVICE.md": "/terms-of-service",
  "PRIVACY_POLICY.md": "/privacy-policy",
  "COMMUNITY_GUIDELINES.md": "/community-guidelines",
  "COPYRIGHT_AND_CONTENT_COMPLAINTS.md": "/copyright-complaints",
  "DMCA.md": "/dmca",
};

function resolvePolicyLink(href: string): string {
  const filename = href.split(/[?#]/, 1)[0]?.split("/").pop() || "";
  return POLICY_ROUTES[filename] || href;
}

function inlineContent(value: string, keyPrefix: string): ReactNode[] {
  const output: ReactNode[] = [];
  const token = /\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)/g;
  let cursor = 0;
  let match: RegExpExecArray | null;
  let index = 0;

  while ((match = token.exec(value)) !== null) {
    if (match.index > cursor) output.push(value.slice(cursor, match.index));
    const tokenValue = match[0];
    if (tokenValue.startsWith("**")) {
      output.push(<strong key={keyPrefix + "-strong-" + index}>{tokenValue.slice(2, -2)}</strong>);
    } else if (tokenValue.startsWith("`")) {
      output.push(<code key={keyPrefix + "-code-" + index}>{tokenValue.slice(1, -1)}</code>);
    } else {
      const closing = tokenValue.indexOf("](");
      const label = tokenValue.slice(1, closing);
      const href = resolvePolicyLink(tokenValue.slice(closing + 2, -1));
      const external = /^https?:\/\//i.test(href);
      output.push(
        <a
          key={keyPrefix + "-link-" + index}
          href={href}
          {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
        >
          {label}
        </a>,
      );
    }
    cursor = match.index + tokenValue.length;
    index += 1;
  }

  if (cursor < value.length) output.push(value.slice(cursor));
  return output;
}

function renderMarkdown(markdown: string): ReactNode[] {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const nodes: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index]?.trim() || "";
    if (!line) {
      index += 1;
      continue;
    }
    if (/^---+$/.test(line)) {
      nodes.push(<hr key={"rule-" + index} />);
      index += 1;
      continue;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) {
      const level = heading[1]!.length;
      const children = inlineContent(heading[2]!, "heading-" + index);
      if (level === 1) nodes.push(<h1 key={"heading-" + index}>{children}</h1>);
      else if (level === 2) nodes.push(<h2 key={"heading-" + index}>{children}</h2>);
      else if (level === 3) nodes.push(<h3 key={"heading-" + index}>{children}</h3>);
      else nodes.push(<h4 key={"heading-" + index}>{children}</h4>);
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index] || "")) {
        items.push((lines[index] || "").trim().replace(/^[-*]\s+/, ""));
        index += 1;
      }
      nodes.push(
        <ul key={"list-" + index}>
          {items.map((item, itemIndex) => <li key={"item-" + itemIndex}>{inlineContent(item, "list-" + index + "-" + itemIndex)}</li>)}
        </ul>,
      );
      continue;
    }

    if (/^\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index] || "")) {
        items.push((lines[index] || "").trim().replace(/^\d+[.)]\s+/, ""));
        index += 1;
      }
      nodes.push(
        <ol key={"ordered-" + index}>
          {items.map((item, itemIndex) => <li key={"item-" + itemIndex}>{inlineContent(item, "ordered-" + index + "-" + itemIndex)}</li>)}
        </ol>,
      );
      continue;
    }

    const paragraph: string[] = [];
    while (index < lines.length && (lines[index] || "").trim()
      && !/^\s*(#{1,4}\s+|[-*]\s+|\d+[.)]\s+|---+$)/.test(lines[index] || "")) {
      paragraph.push((lines[index] || "").trim());
      index += 1;
    }
    nodes.push(<p key={"paragraph-" + index}>{inlineContent(paragraph.join(" "), "paragraph-" + index)}</p>);
  }

  return nodes;
}

export async function PolicyPage({ filename }: { filename: PolicyFilename }) {
  const documentPath = path.resolve(process.cwd(), "../../docs/legal", filename);
  const markdown = await readFile(documentPath, "utf8");

  return (
    <main className="legal-page">
      <header className="legal-header">
        <a className="legal-brand" href="/login" aria-label="Lemegeton sign in">
          <span className="legal-brand-mark">L</span>
          <span><strong>LEMEGETON</strong><small>POLICY CENTRE</small></span>
        </a>
        <a className="legal-back" href="/login">Back to sign in <span aria-hidden="true"><Icon name="external-link" size={12} /></span></a>
      </header>
      <article className="legal-document">
        <div className="legal-kicker"><span /> LEMEGETON / LEGAL DOCUMENTS</div>
        <div className="legal-content">{renderMarkdown(markdown)}</div>
        <nav className="legal-document-nav" aria-label="Legal documents">
          <a href="/terms-of-service">Terms of Service</a>
          <a href="/privacy-policy">Privacy Policy</a>
          <a href="/community-guidelines">Community Guidelines</a>
          <a href="/copyright-complaints">Copyright Complaints</a>
          <a href="/dmca">DMCA & Copyright</a>
        </nav>
      </article>
      <footer className="legal-footer"><span>LEMEGETON / CONTROL PLANE</span><span>FIRST-PARTY POLICY DOCUMENTS</span></footer>
    </main>
  );
}
