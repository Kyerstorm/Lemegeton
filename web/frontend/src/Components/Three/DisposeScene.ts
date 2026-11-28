import { Mesh, type Object3D } from "three";

export function disposeScene(root: Object3D | null): void {
  root?.traverse(object => {
    if (!(object instanceof Mesh)) return;
    object.geometry.dispose();
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    for (const material of materials) material.dispose();
  });
}
