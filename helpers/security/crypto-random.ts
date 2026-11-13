import {createHash,randomBytes} from "node:crypto";

const DOMAIN=Buffer.from("Lemegeton.Random.v1\0","utf8");

/** Return an unbiased integer in [0, upperBound), using fresh OS entropy and SHA-512. */
export function secureRandBelow(upperBound:number):number{
 if(!Number.isSafeInteger(upperBound)||upperBound<=0)throw new RangeError("upperBound must be a positive safe integer.");
 if(upperBound===1)return 0;
 const bound=BigInt(upperBound);
 const bitLength=(bound-1n).toString(2).length;
 const byteLength=Math.ceil(bitLength/8);
 const mask=(1n<<BigInt(bitLength))-1n;
 for(;;){
  const digest=createHash("sha512").update(DOMAIN).update(randomBytes(64)).digest();
  const candidate=BigInt(`0x${digest.subarray(0,byteLength).toString("hex")}`)&mask;
  if(candidate<bound)return Number(candidate);
 }
}

/** Select one item uniformly, without modulo bias. */
export function secureChoice<T>(items:readonly T[]):T{
 if(items.length===0)throw new RangeError("Cannot choose from an empty sequence.");
 return items[secureRandBelow(items.length)]!;
}
