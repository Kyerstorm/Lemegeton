"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { useReducedMotion } from "../Hooks/useReducedMotion";

const R = 50;

type Eye = { w: number; h: number; r: number };

const STYLES: Record<string, Eye> = {
  Slant: { w: 9, h: 15, r: 4.5 },
  Dots: { w: 11, h: 11, r: 5.5 },
  Squares: { w: 12, h: 12, r: 3.5 },
};

const GAP = 0.19;

const TILT = 64;

const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));

const LINES = [
  "Hey, I see you.",
  "Oh, hello there!",
  "Hi there!",
  "Well, look who it is.",
  "Fancy seeing you here.",
  "Hello, human.",
  "You're back!",
  "Hey, stranger.",
  "Good to see you.",
  "Psst. Over here.",
  "Boop.",
  "That tickles.",
  "Again? Okay.",
  "You found me.",
  "Was that necessary?",
  "Hehe. Stop that.",
  "Boop detected.",
  "I felt that.",
  "A little to the left.",
  "Well, that's new.",
  "You have my attention.",
  "Is this your hobby?",
  "I wasn't expecting that.",
  "Okay, one more time.",
  "You're persistent.",
  "Caught you.",
  "I see what you're doing.",
  "Interesting choice.",
  "Touché.",
  "Noted. Boop.",
  "Stop poking me.",
  "I'm watching you.",
  "Careful there.",
  "Don't make this weird.",
  "I have my eyes on you.",
  "That's enough. Probably.",
  "One more and...",
  "You wouldn't dare.",
  "I'm onto you.",
  "Consider yourself noticed.",
  "What are you looking for?",
  "Looking for something?",
  "Did you need something?",
  "Curiosity detected.",
  "What's the plan?",
  "Just exploring?",
  "You seem curious.",
  "Something on your mind?",
  "Where were we?",
  "What's next?",
  "Yes, I'm interactive.",
  "You know I can feel that, right?",
  "There's no achievement for this.",
  "Still here, by the way.",
  "You're testing me, aren't you?",
  "I know you're clicking.",
  "This is getting interesting.",
  "I wasn't programmed for this.",
  "Are we having fun yet?",
  "You could be doing literally anything.",
  "A wild click appeared!",
  "Interaction successful. Probably.",
  "This button has feelings.",
  "Don't tell the others.",
  "My circuits are tingling.",
  "Beep boop.",
  "Tiny interruption.",
  "Stay curious.",
  "What a day.",
  "That's quite enough excitement.",
  "I'm just vibing.",
  "Everything is under control.",
  "Trust the process.",
  "Nothing suspicious here.",
  "Carry on.",
  "You saw nothing.",
  "A moment, please.",
  "Well, anyway...",
  "Back to business.",
];

const TINTS = [
  "#3b5bff", 
  "#179c52", 
  "#e0307f", 
  "#9b5de5", 
  "#00a6a6", 
  "#ff8c42", 
  "#e5b800", 
  "#e05252", 
  "#64748b", 
  "#00a3ff", 
  "#c04cff", 
  "#20b486", 
];
const KEY_MS = 38;
const HOLD_MS = 1500;

const SHAPES: Record<string, string> = {
  Ball: "M50 0 A50 50 0 1 1 49.99 0 Z",

  Circle: "M50 7 A43 43 0 1 1 49.99 7 Z",
  Cube: "M30 6 H70 A24 24 0 0 1 94 30 V70 A24 24 0 0 1 70 94 H30 A24 24 0 0 1 6 70 V30 A24 24 0 0 1 30 6 Z",
  Pill: "M34 17 H66 A33 33 0 0 1 66 83 H34 A33 33 0 0 1 34 17 Z",

  Hexagon: "M59.53 8.50 L81.18 21.00 Q90.70 26.50 90.70 37.50 L90.70 62.50 Q90.70 73.50 81.18 79.00 L59.53 91.50 Q50.00 97.00 40.47 91.50 L18.82 79.00 Q9.30 73.50 9.30 62.50 L9.30 37.50 Q9.30 26.50 18.82 21.00 L40.47 8.50 Q50.00 3.00 59.53 8.50 Z",
  "Hex flat": "M91.50 59.53 L79.00 81.18 Q73.50 90.70 62.50 90.70 L37.50 90.70 Q26.50 90.70 21.00 81.18 L8.50 59.53 Q3.00 50.00 8.50 40.47 L21.00 18.82 Q26.50 9.30 37.50 9.30 L62.50 9.30 Q73.50 9.30 79.00 18.82 L91.50 40.47 Q97.00 50.00 91.50 59.53 Z",
};

const RAYS = 120;
const radii = new Map<string, number[]>();

function measure(shape: string): number[] {
  const hit = radii.get(shape);
  if (hit) return hit;
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 100 100");
  svg.style.cssText = "position:absolute;width:0;height:0;overflow:hidden";
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", SHAPES[shape] ?? SHAPES.Ball);
  svg.appendChild(path);
  document.body.appendChild(svg);
  const pt = svg.createSVGPoint();
  const out: number[] = [];
  for (let i = 0; i < RAYS; i++) {
    const a = (i / RAYS) * Math.PI * 2 - Math.PI / 2;
    let lo = 0, hi = 60;
    for (let k = 0; k < 16; k++) {
      const mid = (lo + hi) / 2;
      pt.x = 50 + Math.cos(a) * mid;
      pt.y = 50 + Math.sin(a) * mid;
      if (path.isPointInFill(pt)) lo = mid; else hi = mid;
    }
    out.push(lo);
  }
  svg.remove();
  radii.set(shape, out);
  return out;
}

function outline(r: number[]): string {
  let d = "";
  r.forEach((v, i) => {
    const a = (i / r.length) * Math.PI * 2 - Math.PI / 2;
    d += `${i ? "L" : "M"}${(50 + Math.cos(a) * v).toFixed(2)} ${(50 + Math.sin(a) * v).toFixed(2)}`;
  });
  return d + "Z";
}

export type WatcherProps = {
  follow?: number;
  bounce?: number;
  size?: number;
  shape?: string;
  eyes?: string;
  eyeScale?: number;
  eyeWidth?: number;
  eyeRound?: number;
  eyeHeight?: number;
  idle?: boolean;
  within?: string;
};

export function Watcher({

  follow = 60,

  bounce = 30,
  size = 100,
  shape = "Cube",
  eyes: look = "Slant",

  eyeScale = 1,

  eyeWidth = 1,

  eyeRound = 1,

  eyeHeight = 1,

  idle = false,

  within,
}: WatcherProps = {}) {
  const still = useReducedMotion();
  const box = useRef<HTMLDivElement>(null);
  const [typed, setTyped] = useState("");
  const [talking, setTalking] = useState(false);
  const [tint, setTint] = useState(TINTS[0]);
  const turn = useRef(0);
  const lastLine = useRef(-1);
  useEffect(() => () => { turn.current++; }, []);
  const poke = async () => {
    if (idle) return;
    const mine = ++turn.current;
    const pool = LINES.map((_, i) => i).filter((i) => i !== lastLine.current);
    const i = pool[Math.floor(Math.random() * pool.length)];
    lastLine.current = i;
    const line = LINES[i];
    const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
    setTint(TINTS[Math.floor(Math.random() * TINTS.length)]);
    setTyped("");
    setTalking(true);
    if (still) {
      setTyped(line);
    } else {
      for (let k = 1; k <= line.length; k++) {
        await wait(KEY_MS + Math.random() * 30);
        if (mine !== turn.current) return;
        setTyped(line.slice(0, k));
      }
    }
    await wait(HOLD_MS);
    if (mine !== turn.current) return;
    setTalking(false);
  };
  const eyes = useRef<(SVGGElement | null)[]>([]);
  const knobs = useRef({ follow, bounce, eyeScale });
  knobs.current = { follow, bounce, eyeScale };
  const base = STYLES[look] ?? STYLES.Slant;
  const eye = {
    w: base.w * eyeScale * eyeWidth,
    h: base.h * eyeScale * eyeHeight,
    r: base.r * eyeScale * eyeWidth * eyeRound,
  };
  const eyeNow = useRef(eye);
  eyeNow.current = eye;

  useEffect(() => {
    const el = box.current;
    if (!el) return;

    const t = { x: 0, y: 0, vx: 0, vy: 0, tx: 0, ty: 0 };
    let raf = 0;
    let prev = 0;
    let blink = Number.NEGATIVE_INFINITY;
    let nextBlink = performance.now() + (idle ? 2000 : 2200);
    let blinkTimer = 0;
    let glanceTimer = 0;
    let glanceEndTimer = 0;
    let seen = true;

    const draw = (now: number) => {
      const since = now - blink;
      const blinking = !still && since >= 0 && since < 160;
      const lid = blinking ? 1 - 0.9 * Math.sin((since / 160) * Math.PI) : 1;

      const as = (v: number) => Math.asin(clamp(v, -0.92, 0.92));
      const yaw = as(t.x);
      const pitch = -as(t.y);
      const cy = Math.cos(yaw), sy = Math.sin(yaw);
      const cp = Math.cos(pitch), sp = Math.sin(pitch);
      const tilt = TILT * t.x * t.y;
      const g0 = GAP * Math.max(1, knobs.current.eyeScale * 0.8);

      [-g0, g0].forEach((x0, i) => {
        const g = eyes.current[i];
        if (!g) return;

        const z0 = Math.sqrt(1 - x0 * x0);
        const x1 = x0 * cy + z0 * sy;
        const z1 = -x0 * sy + z0 * cy;
        const y2 = -z1 * sp;
        const z2 = z1 * cp;
        const near = clamp(z2, 0, 1);
        const k = 0.45 + 0.55 * near;
        const sx = k * (0.7 + 0.3 * near);
        const e0 = eyeNow.current;
        const w = e0.w * sx;
        const h = Math.max(0.6, e0.h * k * lid);
        const rect = g.firstElementChild as SVGRectElement | null;

        if (rect) {
          rect.setAttribute("x", (-w / 2).toFixed(2));
          rect.setAttribute("y", (-h / 2).toFixed(2));
          rect.setAttribute("width", w.toFixed(2));
          rect.setAttribute("height", h.toFixed(2));
          rect.setAttribute("rx", Math.min(e0.r, w / 2, h / 2).toFixed(2));
        }

        g.setAttribute(
          "transform",
          `translate(${(50 + x1 * R).toFixed(2)} ${(50 + y2 * R).toFixed(2)}) rotate(${tilt.toFixed(2)})`,
        );
        g.style.opacity = z2 < 0.05 ? "0" : "1";
      });

      return blinking;
    };

    const tick = (now: number) => {
      raf = 0;
      if (!seen || document.hidden) {
        prev = 0;
        return;
      }

      const dt = prev ? Math.min(2.5, (now - prev) / 16.67) : 1;
      prev = now;

      if (still) {
        t.x = t.tx;
        t.y = t.ty;
        t.vx = 0;
        t.vy = 0;
      } else {
        const k = 0.06;
        const d = 0.34 - (clamp(knobs.current.bounce, 0, 100) / 100) * 0.22;
        t.vx += ((t.tx - t.x) * k - t.vx * d) * dt;
        t.vy += ((t.ty - t.y) * k - t.vy * d) * dt;
        t.x += t.vx * dt;
        t.y += t.vy * dt;
      }

      const moving = !still && (
        Math.abs(t.tx - t.x) > 0.02
        || Math.abs(t.ty - t.y) > 0.02
        || Math.abs(t.vx) > 0.02
        || Math.abs(t.vy) > 0.02
      );

      if (!moving && !still) {
        t.x = t.tx;
        t.y = t.ty;
        t.vx = 0;
        t.vy = 0;
      }

      const blinking = draw(now);
      if (moving || blinking) raf = requestAnimationFrame(tick);
      else prev = 0;
    };

    const wake = () => {
      if (!raf && seen && !document.hidden) raf = requestAnimationFrame(tick);
    };
    const aimAt = (x: number, y: number) => {
      t.tx = x;
      t.ty = y;
      wake();
    };
    const rest = () => aimAt(0, 0);

    const frame = el.closest<HTMLElement>(
      within ?? ".app-shell, .page, .bench-card, .dtl-block, .board, .sf-thumb, .panel, .card",
    ) ?? el;

    const aim = (e: PointerEvent) => {
      const f = frame.getBoundingClientRect();
      if (
        e.clientX < f.left || e.clientX > f.right
        || e.clientY < f.top || e.clientY > f.bottom
      ) {
        rest();
        return;
      }

      const r = el.getBoundingClientRect();
      const dx = e.clientX - (r.left + r.width / 2);
      const dy = e.clientY - (r.top + r.height / 2);
      const d = Math.hypot(dx, dy) || 1;
      const reach = Math.max(60, Math.min(f.width, f.height) * 0.28);
      const far = Math.min(
        0.85,
        Math.tanh(d / reach) * (clamp(knobs.current.follow, 0, 100) / 100) * 1.5,
      );
      aimAt((dx / d) * far, (dy / d) * far);
    };

    const scheduleBlink = () => {
      if (still) return;
      blinkTimer = window.setTimeout(() => {
        blink = performance.now();
        nextBlink = blink + (idle ? 2000 : 2600 + Math.random() * 3200);
        wake();
        scheduleBlink();
      }, Math.max(0, nextBlink - performance.now()));
    };

    const io = new IntersectionObserver(([entry]) => {
      seen = entry.isIntersecting;
      if (!seen && raf) {
        cancelAnimationFrame(raf);
        raf = 0;
        prev = 0;
      } else {
        wake();
      }
    });
    io.observe(el);
    document.addEventListener("visibilitychange", wake);

    if (!still) scheduleBlink();

    if (idle && !still) {
      const look = () => {
        const a = Math.random() * Math.PI * 2;
        const far = 0.45 + Math.random() * 0.25;
        aimAt(Math.cos(a) * far, Math.sin(a) * far);
        glanceEndTimer = window.setTimeout(() => {
          rest();
          glanceTimer = window.setTimeout(look, 4100);
        }, 900);
      };
      glanceTimer = window.setTimeout(look, 5000);
    } else if (!idle) {
      window.addEventListener("pointermove", aim, { passive: true });
      document.documentElement.addEventListener("pointerleave", rest);
    }

    wake();

    return () => {
      if (raf) cancelAnimationFrame(raf);
      io.disconnect();
      document.removeEventListener("visibilitychange", wake);
      window.removeEventListener("pointermove", aim);
      document.documentElement.removeEventListener("pointerleave", rest);
      window.clearTimeout(blinkTimer);
      window.clearTimeout(glanceTimer);
      window.clearTimeout(glanceEndTimer);
    };
  }, [still, idle, within]);

  const s = clamp(size, 16, 180);
  const body = SHAPES[shape] ?? SHAPES.Ball;
  const clip = `eyt-clip-${useId().replace(/:/g, "")}`;

  const bodyEl = useRef<SVGPathElement>(null);
  const clipEl = useRef<SVGPathElement>(null);
  const shown = useRef<number[] | null>(null);
  const from = useRef(shape);
  useLayoutEffect(() => {
    if (from.current === shape && !still) return;
    const start = shown.current ?? measure(from.current);
    const end = measure(shape);
    from.current = shape;
    if (still) {
      shown.current = end;
      const d = outline(end);
      bodyEl.current?.setAttribute("d", d);
      clipEl.current?.setAttribute("d", d);
      return;
    }
    const t0 = performance.now();
    const ms = 520;
    let raf = 0;
    const step = (now: number) => {
      const u = Math.min(1, (now - t0) / ms);

      const c = 1.3;
      const e = 1 + (c + 1) * Math.pow(u - 1, 3) + c * Math.pow(u - 1, 2);
      const r = start.map((a, i) => a + (end[i] - a) * e);
      shown.current = r;
      const d = outline(r);
      bodyEl.current?.setAttribute("d", d);
      clipEl.current?.setAttribute("d", d);
      if (u < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [shape, still]);
  return (
    <div
      className="eyt"
      ref={box}
      style={{ "--eyt-size": `${s}px` } as React.CSSProperties}
    >
      <svg
        className="eyt-ball"
        viewBox="0 0 100 100"
        data-poke={idle ? undefined : true}
        role={idle ? "img" : "button"}
        tabIndex={idle ? undefined : 0}
        aria-label={idle ? "A small animated mark" : "Interactive eyes. Press to make them respond."}
        onClick={() => { void poke(); }}
        onKeyDown={(event) => {
          if (!idle && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            void poke();
          }
        }}
      >
        <defs>
          <clipPath id={clip}>
            <path ref={clipEl} d={shown.current ? outline(shown.current) : body} />
          </clipPath>
        </defs>
        <path ref={bodyEl} className="eyt-body" d={shown.current ? outline(shown.current) : body} />
        <g clipPath={`url(#${clip})`}>
        {[0, 1].map((i) => (
          <g key={i} ref={(n) => { eyes.current[i] = n; }}>
            <rect
              className="eyt-eye"
              x={-eye.w / 2}
              y={-eye.h / 2}
              width={eye.w}
              height={eye.h}
              rx={eye.r}
            />
          </g>
        ))}
        </g>
      </svg>
      {idle ? null : (
        <span
          className="eyt-say"
          data-on={talking || undefined}
          aria-live="polite"
          style={{ "--tint": tint } as React.CSSProperties}
        >
          <span>{typed}</span>
          <span className="eyt-caret" />
        </span>
      )}
    </div>
  );
}
