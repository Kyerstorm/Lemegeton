"use client";

import { useCallback, useEffect, useRef } from "react";
import { useReducedMotion } from "../Hooks/useReducedMotion";

const W = 480;
const H = 400;
const CX = W / 2;
const CY = H / 2;

const N = 720;

export const SHAPES = ["Circle", "Square", "Flower"] as const;
type Shape = (typeof SHAPES)[number];
export type ParticleShape = Shape;

const homeCache = new Map<Shape, [number, number][]>();

type Dot = { hx: number; hy: number; x: number; y: number; vx: number; vy: number };

const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));

function outline(s: Shape): Path2D {
  const p = new Path2D();
  if (s === "Circle") p.arc(CX, CY, 150, 0, Math.PI * 2);
  else if (s === "Square") p.roundRect(CX - 140, CY - 140, 280, 280, 36);
  else {

    for (let i = 0; i < 5; i++) {
      const a = -Math.PI / 2 + (i * Math.PI * 2) / 5;
      const x = CX + Math.cos(a) * 104;
      const y = CY + 8 + Math.sin(a) * 104;
      p.moveTo(x + 60, y);
      p.arc(x, y, 60, 0, Math.PI * 2);
    }
    p.moveTo(CX + 58, CY + 8);
    p.arc(CX, CY + 8, 58, 0, Math.PI * 2);
  }
  return p;
}

function homes(s: Shape): [number, number][] {
  const cached = homeCache.get(s);
  if (cached) return cached;

  const c = document.createElement("canvas");
  c.width = W;
  c.height = H;
  const g = c.getContext("2d")!;
  const path = outline(s);
  let area = 0;
  for (let y = 1; y < H; y += 2) for (let x = 1; x < W; x += 2) if (g.isPointInPath(path, x, y)) area += 4;
  const sp = Math.sqrt((area / N) * (2 / Math.sqrt(3)));
  const rowH = (sp * Math.sqrt(3)) / 2;
  const pts: [number, number][] = [];
  for (let y = rowH / 2, row = 0; y < H; y += rowH, row++) {
    for (let x = sp / 2 + (row % 2) * (sp / 2); x < W; x += sp) {
      if (g.isPointInPath(path, x, y)) pts.push([x, y]);
    }
  }

  const out: [number, number][] = [];
  for (let i = 0; i < N; i++) out.push(pts[Math.floor((i * pts.length) / N)]);
  homeCache.set(s, out);
  return out;
}

const angle = (x: number, y: number) => Math.atan2(y - CY, x - CX);

export type ParticlesProps = {
  shape?: string;
  reach?: number;
  force?: number;
  grain?: string;
};

export function Particles({

  shape = "Circle",

  reach = 80,

  force = 60,

  grain = "Fine",
}: ParticlesProps = {}) {
  const still = useReducedMotion();
  const cv = useRef<HTMLCanvasElement | null>(null);
  const dots = useRef<Dot[]>([]);
  const at = useRef<Shape>("Circle");
  const hand = useRef<{ x: number; y: number } | null>(null);
  const raf = useRef(0);
  const knobs = useRef({ reach, force, grain });
  knobs.current = { reach, force, grain };

  const become = useCallback((s: Shape) => {
    at.current = s;
    const next = homes(s);
    const ds = dots.current;
    if (!ds.length) {
      dots.current = next.map(([x, y]) => ({ hx: x, hy: y, x, y, vx: 0, vy: 0 }));
      return;
    }

    const a = ds.map((d, i) => [angle(d.x, d.y), i] as const).sort((p, q) => p[0] - q[0]);
    const b = next.map((h, i) => [angle(h[0], h[1]), i] as const).sort((p, q) => p[0] - q[0]);
    a.forEach(([, di], k) => {
      const h = next[b[k][1]];
      ds[di].hx = h[0];
      ds[di].hy = h[1];
      if (still) { ds[di].x = h[0]; ds[di].y = h[1]; }
    });
  }, [still]);

  const draw = useCallback(() => {
    const c = cv.current;
    if (!c) return;
    const x = c.getContext("2d")!;
    const k = c.width / W;
    x.setTransform(k, 0, 0, k, 0, 0);
    x.clearRect(0, 0, W, H);
    x.fillStyle = getComputedStyle(c).color;
    const r = knobs.current.grain === "Coarse" ? 2.7 : 1.9;
    x.beginPath();
    for (const d of dots.current) {
      const sp = Math.hypot(d.vx, d.vy);
      if (sp < 0.3) {
        x.moveTo(d.x + r, d.y);
        x.arc(d.x, d.y, r, 0, Math.PI * 2);
      } else {

        const s = Math.min(2.6, 1 + sp * 0.12);
        const rot = Math.atan2(d.vy, d.vx);
        x.moveTo(d.x + Math.cos(rot) * r * s, d.y + Math.sin(rot) * r * s);
        x.ellipse(d.x, d.y, r * s, r / Math.sqrt(s), rot, 0, Math.PI * 2);
      }
    }
    x.fill();
  }, []);

  const run = useCallback(() => {
    if (still) {
      draw();
      return;
    }
    if (raf.current) return;

    let prev = 0;
    const tick = (t: number) => {
      const dt = prev ? clamp((t - prev) / 16.67, 0, 2.5) : 1;
      prev = t;
      const h = hand.current;
      const R = clamp(knobs.current.reach, 30, 160);
      const S = (clamp(knobs.current.force, 0, 100) / 100) * 11;
      let busy = false;

      for (const d of dots.current) {
        if (h && S > 0) {
          const dx = d.x - h.x;
          const dy = d.y - h.y;
          const dd = Math.hypot(dx, dy);
          if (dd < R && dd > 0.01) {
            const f = Math.pow(1 - dd / R, 2) * S;
            d.vx += (dx / dd) * f * dt;
            d.vy += (dy / dd) * f * dt;
            busy = true;
          }
        }

        d.vx = (d.vx + (d.hx - d.x) * 0.05 * dt) * Math.pow(0.84, dt);
        d.vy = (d.vy + (d.hy - d.y) * 0.05 * dt) * Math.pow(0.84, dt);
        d.x += d.vx * dt;
        d.y += d.vy * dt;

        if (
          Math.abs(d.hx - d.x) < 0.05
          && Math.abs(d.hy - d.y) < 0.05
          && Math.abs(d.vx) < 0.02
          && Math.abs(d.vy) < 0.02
        ) {
          d.x = d.hx;
          d.y = d.hy;
          d.vx = 0;
          d.vy = 0;
        } else {
          busy = true;
        }
      }

      draw();
      raf.current = busy ? requestAnimationFrame(tick) : 0;
    };

    raf.current = requestAnimationFrame(tick);
  }, [still, draw]);

  useEffect(() => {
    const c = cv.current;
    if (!c) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    c.width = Math.round(W * dpr);
    c.height = Math.round(H * dpr);
  }, []);
  useEffect(() => {
    const s = (SHAPES as readonly string[]).includes(shape) ? (shape as Shape) : "Circle";
    become(s);
    draw();
    run();
  }, [shape, become, draw, run]);
  useEffect(() => { draw(); }, [grain, draw]);
  useEffect(() => {
    if (!still) return;
    hand.current = null;
    for (const dot of dots.current) {
      dot.x = dot.hx;
      dot.y = dot.hy;
      dot.vx = 0;
      dot.vy = 0;
    }
    if (raf.current) cancelAnimationFrame(raf.current);
    raf.current = 0;
    draw();
  }, [still, draw]);
  useEffect(() => () => { cancelAnimationFrame(raf.current); raf.current = 0; }, []);
  useEffect(() => {
    const mo = new MutationObserver(draw);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, [draw]);

  const where = (e: React.PointerEvent) => {
    const r = e.currentTarget.getBoundingClientRect();
    const k = r.width / W;
    return { x: (e.clientX - r.left) / k, y: (e.clientY - r.top) / k };
  };

  return (
    <div className="ptc">
      <canvas
        ref={cv}
        className="ptc-canvas"
        style={{ width: "100%", height: "auto", aspectRatio: `${W} / ${H}` }}
        role="button"
        tabIndex={0}
        aria-label="Interactive particle field. Move the pointer to repel dots; press Enter or Space to change the shape."
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            become(SHAPES[(SHAPES.indexOf(at.current) + 1) % SHAPES.length]);
            draw();
            run();
          }
        }}
        onPointerMove={(e) => {
          if (still) return;
          hand.current = where(e);
          run();
        }}
        onPointerLeave={() => { hand.current = null; run(); }}
        onPointerCancel={() => { hand.current = null; run(); }}
        onPointerDown={(e) => {

          const p = where(e);
          if (!still) {
            const S = 0.4 + (clamp(knobs.current.force, 0, 100) / 100) * 1.2;
            for (const d of dots.current) {
              const dx = d.x - p.x;
              const dy = d.y - p.y;
              const dd = Math.hypot(dx, dy);
              if (dd > 200 || dd < 0.01) continue;
              const f = (1 - dd / 200) * 30 * S;
              d.vx += (dx / dd) * f;
              d.vy += (dy / dd) * f;
            }
          }
          become(SHAPES[(SHAPES.indexOf(at.current) + 1) % SHAPES.length]);
          draw();
          run();
        }}
      />
    </div>
  );
}
