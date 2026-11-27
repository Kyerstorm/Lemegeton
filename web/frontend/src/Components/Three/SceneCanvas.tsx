"use client";

import { useEffect, useRef } from "react";
import { Canvas } from "@react-three/fiber";
import type { Group } from "three";
import { useReducedMotion } from "../Hooks/useReducedMotion";
import { MonochromeScene } from "./MonochromeScene";
import { disposeScene } from "./DisposeScene";
import { SCENE_CONFIG } from "./SceneConfig";
import { WebGLFallback } from "./WebGLFallback";

export function SceneCanvas() {
  const scene = useRef<Group>(null);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    const mountedScene = scene.current;
    return () => disposeScene(mountedScene);
  }, []);

  return (
    <Canvas
      frameloop={reducedMotion ? "demand" : "always"}
      dpr={[SCENE_CONFIG.dpr[0], SCENE_CONFIG.dpr[1]]}
      camera={{ position: [...SCENE_CONFIG.camera.position], fov: SCENE_CONFIG.camera.fov }}
      gl={{ alpha: true, antialias: true, powerPreference: "low-power" }}
      fallback={<WebGLFallback />}
    >
      <ambientLight intensity={0.8} />
      <pointLight position={[3, 3, 4]} intensity={18} color="#ffffff" />
      <group ref={scene} dispose={null}>
        <MonochromeScene />
      </group>
    </Canvas>
  );
}
