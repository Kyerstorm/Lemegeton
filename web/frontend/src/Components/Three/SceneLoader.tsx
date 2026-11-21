"use client";

import dynamic from "next/dynamic";
import { Component, useEffect, useState, type ReactNode } from "react";
import { SceneFallback } from "./SceneFallback";

const SceneCanvas = dynamic(
  () => import("./SceneCanvas").then(module => module.SceneCanvas),
  { ssr: false, loading: () => <SceneFallback /> },
);

class SceneErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <SceneFallback /> : this.props.children; }
}

function supportsWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

export function SceneLoader() {
  const [available, setAvailable] = useState(false);
  useEffect(() => setAvailable(supportsWebGL()), []);
  if (!available) return <SceneFallback />;
  return <SceneErrorBoundary><SceneCanvas /></SceneErrorBoundary>;
}
