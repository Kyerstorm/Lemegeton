export const SCENE_CONFIG = {
  desktopMinWidth: 801,
  camera: { position: [0, 0, 5.3] as [number, number, number], fov: 38 },
  dpr: [1, 1.4] as [number, number],
  geometry: { radius: 1.05, detail: 1, orbitRadius: 1.42, outerOrbitRadius: 1.64 },
  rotation: { speed: 0.12, tilt: 0.045, tiltFrequency: 0.2 },
} as const;
