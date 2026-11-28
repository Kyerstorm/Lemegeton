import { isIP } from "node:net";

const NON_PUBLIC_IPV4_RANGES: ReadonlyArray<readonly [number, number]> = [
  [0x00000000, 8], [0x0a000000, 8], [0x64400000, 10], [0x7f000000, 8],
  [0xa9fe0000, 16], [0xac100000, 12], [0xc0000000, 24], [0xc0000200, 24],
  [0xc01fc400, 24], [0xc034c100, 24], [0xc0586300, 24], [0xc0a80000, 16],
  [0xc0af3000, 24], [0xc6120000, 15], [0xc6336400, 24],
  [0xcb007100, 24], [0xe0000000, 4], [0xf0000000, 4],
];

function parseIpv4Number(value: string): number | null {
  const octets = value.split(".").map(Number);
  if (octets.length !== 4 || octets.some(octet => !Number.isInteger(octet) || octet < 0 || octet > 255)) return null;
  return (((octets[0]! << 24) | (octets[1]! << 16) | (octets[2]! << 8) | octets[3]!) >>> 0);
}

function isNonPublicIpv4(value: string): boolean {
  const address = parseIpv4Number(value);
  if (address === null) return true;
  return NON_PUBLIC_IPV4_RANGES.some(([network, prefix]) =>
    (address >>> (32 - prefix)) === (network >>> (32 - prefix)),
  );
}

function parseIpv6Groups(value: string): number[] | null {
  let normalized = value.toLowerCase();
  if (!normalized.includes(":") || normalized.includes("%")) return null;
  const dottedTail = normalized.match(/(?:^|:)(\d{1,3}(?:\.\d{1,3}){3})$/);
  if (dottedTail) {
    const ipv4 = parseIpv4Number(dottedTail[1]!);
    if (ipv4 === null) return null;
    const first = (ipv4 >>> 16).toString(16);
    const second = (ipv4 & 0xffff).toString(16);
    normalized = normalized.slice(0, normalized.length - dottedTail[1]!.length) + first + ":" + second;
  }
  const separator = normalized.indexOf("::");
  if (separator !== -1 && normalized.indexOf("::", separator + 2) !== -1) return null;
  const leftText = separator === -1 ? normalized : normalized.slice(0, separator);
  const rightText = separator === -1 ? "" : normalized.slice(separator + 2);
  const parseSide = (side: string): number[] | null => {
    if (!side) return [];
    const groups = side.split(":");
    if (groups.some(group => !/^[0-9a-f]{1,4}$/.test(group))) return null;
    return groups.map(group => Number.parseInt(group, 16));
  };
  const left = parseSide(leftText);
  const right = parseSide(rightText);
  if (!left || !right) return null;
  const missing = 8 - left.length - right.length;
  if (separator === -1 ? missing !== 0 : missing < 1) return null;
  return [...left, ...Array<number>(missing).fill(0), ...right];
}

export function isPublicUnicastAddress(address: string): boolean {
  const value = address.toLowerCase().replace(/^\[/, "").replace(/\]$/, "");
  const version = isIP(value);
  if (version === 4) return !isNonPublicIpv4(value);
  if (version !== 6) return false;

  const groups = parseIpv6Groups(value);
  if (!groups) return false;

  if (groups.slice(0, 5).every(group => group === 0) && groups[5] === 0xffff) {
    const ipv4 = (((groups[6]! << 16) | groups[7]!) >>> 0);
    return !isNonPublicIpv4([
      (ipv4 >>> 24) & 255,
      (ipv4 >>> 16) & 255,
      (ipv4 >>> 8) & 255,
      ipv4 & 255,
    ].join("."));
  }
  if (groups.slice(0, 6).every(group => group === 0)) return false;

  const first = groups[0]!;
  const second = groups[1]!;
  if ((first & 0xe000) !== 0x2000) return false;
  if (first === 0x2001 && (second & 0xfe00) === 0) return false;
  if (first === 0x2001 && second === 0x0db8) return false;
  if (first === 0x2002) return false;
  if (first === 0x3fff && (second & 0xf000) === 0) return false;
  if (first === 0x0064 && second === 0xff9b) return false;
  return true;
}
