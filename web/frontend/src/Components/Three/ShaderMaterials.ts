import { ShaderMaterial } from "three";

export const MONOCHROME_VERTEX_SHADER = `
  varying vec3 vNormal;
  varying vec3 vPosition;
  void main() {
    vNormal = normalize(normalMatrix * normal);
    vec4 position = modelViewMatrix * vec4(position, 1.0);
    vPosition = position.xyz;
    gl_Position = projectionMatrix * position;
  }
`;

export const MONOCHROME_FRAGMENT_SHADER = `
  varying vec3 vNormal;
  varying vec3 vPosition;
  void main() {
    float light = max(dot(normalize(vNormal), normalize(vec3(0.45, 0.7, 1.0))), 0.0);
    float edge = pow(1.0 - abs(dot(normalize(vNormal), normalize(-vPosition))), 2.0);
    float shade = 0.28 + light * 0.38 + edge * 0.12;
    gl_FragColor = vec4(vec3(shade), 1.0);
  }
`;

export function createMonochromeMaterial(): ShaderMaterial {
  return new ShaderMaterial({
    vertexShader: MONOCHROME_VERTEX_SHADER,
    fragmentShader: MONOCHROME_FRAGMENT_SHADER,
    transparent: false,
  });
}
