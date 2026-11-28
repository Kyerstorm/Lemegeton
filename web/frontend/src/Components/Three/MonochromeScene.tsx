"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import type { Group } from "three";
import { createMonochromeMaterial } from "./ShaderMaterials";
import { SCENE_CONFIG } from "./SceneConfig";
import { OrbitalGeometry } from "./OrbitalGeometry";

export function MonochromeScene() {
  const group = useRef<Group>(null);
  const material = useMemo(() => createMonochromeMaterial(), []);

  useFrame((state, delta) => {
    if (!group.current) return;
    group.current.rotation.y += delta * SCENE_CONFIG.rotation.speed;
    group.current.rotation.x = Math.sin(state.clock.elapsedTime * SCENE_CONFIG.rotation.tiltFrequency) * SCENE_CONFIG.rotation.tilt;
  });

  return (
    <group ref={group}>
      <mesh>
        <icosahedronGeometry args={[SCENE_CONFIG.geometry.radius, SCENE_CONFIG.geometry.detail]} />
        <primitive object={material} attach="material" />
      </mesh>
      <OrbitalGeometry />
    </group>
  );
}
