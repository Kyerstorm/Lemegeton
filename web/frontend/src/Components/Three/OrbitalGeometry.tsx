import { SCENE_CONFIG } from "./SceneConfig";

export function OrbitalGeometry() {
  return (
    <>
      <mesh rotation={[Math.PI / 2.8, 0, 0]}>
        <torusGeometry args={[SCENE_CONFIG.geometry.orbitRadius, 0.012, 8, 112]} />
        <meshBasicMaterial color="#f4f4f4" transparent opacity={0.72} />
      </mesh>
      <mesh rotation={[0.3, 0.4, Math.PI / 2]}>
        <torusGeometry args={[SCENE_CONFIG.geometry.outerOrbitRadius, 0.006, 6, 112]} />
        <meshBasicMaterial color="#777777" transparent opacity={0.52} />
      </mesh>
    </>
  );
}
