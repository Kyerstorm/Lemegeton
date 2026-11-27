"use client";

import dynamic from "next/dynamic";
import { Component, useEffect, useState, type ReactNode } from "react";
import { WebGLFallback } from "./WebGLFallback";

const SceneCanvas = dynamic(
  () => import("./SceneCanvas").then(module => module.SceneCanvas),
  { ssr: false, loading: () => <WebGLFallback /> },
);

class SceneErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <WebGLFallback /> : this.props.children; }
}

function supportsWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

type SceneMode = "hidden" | "static" | "webgl";

export function SceneLoader() {
  const [mode, setMode] = useState<SceneMode>("hidden");
  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => {
      if (!window.matchMedia("(min-width: 801px)").matches) {
        setMode("hidden");
      } else if (motion.matches || !supportsWebGL()) {
        setMode("static");
      } else {
        setMode("webgl");
      }
    };
    update();
    window.addEventListener("resize", update);
    motion.addEventListener("change", update);
    return () => {
      window.removeEventListener("resize", update);
      motion.removeEventListener("change", update);
    };
  }, []);
  if (mode === "hidden") return null;
  if (mode === "static") return <WebGLFallback />;
  return <SceneErrorBoundary><SceneCanvas /></SceneErrorBoundary>;
}
