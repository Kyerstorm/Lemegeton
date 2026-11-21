"use client";

import { useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import type { Group } from "three";

function Geometry() {
  const group = useRef<Group>(null);
  useFrame((state, delta) => {
    if (!group.current) return;
    group.current.rotation.y += delta * 0.12;
    group.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.2) * 0.045;
  });
  return <group ref={group}>
    <mesh>
      <icosahedronGeometry args={[1.05, 1]} />
      <meshStandardMaterial color="#bdbdbd" wireframe roughness={0.82} metalness={0.15} />
    </mesh>
    <mesh rotation={[Math.PI / 2.8, 0, 0]}>
      <torusGeometry args={[1.42, 0.012, 8, 112]} />
      <meshBasicMaterial color="#f4f4f4" transparent opacity={0.72} />
    </mesh>
    <mesh rotation={[0.3, 0.4, Math.PI / 2]}>
      <torusGeometry args={[1.64, 0.006, 6, 112]} />
      <meshBasicMaterial color="#777" transparent opacity={0.52} />
    </mesh>
  </group>;
}

export function SceneCanvas() {
  return <Canvas dpr={[1, 1.4]} camera={{ position: [0, 0, 5.3], fov: 38 }} gl={{ alpha: true, antialias: true, powerPreference: "low-power" }}>
    <ambientLight intensity={0.8} />
    <pointLight position={[3, 3, 4]} intensity={18} color="#fff" />
    <Geometry />
  </Canvas>;
}
