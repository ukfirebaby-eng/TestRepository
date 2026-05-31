export type Vec3 = { x: number; y: number; z: number };

export type FocusTarget = {
  camera: Vec3;
  lookAt: Vec3;
};

export function seededPosition(index: number, total: number, riskScore: number): Vec3 {
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  const y = 1 - (index / Math.max(total - 1, 1)) * 2;
  const radius = Math.sqrt(1 - y * y);
  const theta = goldenAngle * index;
  const spread = 7 + Math.min(riskScore, 16) * 0.16;
  return {
    x: Math.cos(theta) * radius * spread,
    y: y * spread * 0.74,
    z: Math.sin(theta) * radius * spread,
  };
}

export function getFocusTarget(position: Vec3, distance = 7): FocusTarget {
  return {
    lookAt: position,
    camera: {
      x: position.x * 0.72,
      y: position.y + distance * 0.34,
      z: position.z + distance,
    },
  };
}

export function getLinkFocusTarget(source: Vec3, target: Vec3): FocusTarget {
  const midpoint = {
    x: (source.x + target.x) / 2,
    y: (source.y + target.y) / 2,
    z: (source.z + target.z) / 2,
  };
  return getFocusTarget(midpoint, 8.5);
}
