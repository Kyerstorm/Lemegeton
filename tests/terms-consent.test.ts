import test from "node:test";
import assert from "node:assert/strict";
import {buildConsentComponents,buildConsentEmbed,CONSENT_POLICY_VERSIONS,POLICY_LINKS,parseConsentAction} from "../helpers/security/terms-consent.js";
import {secureChoice,secureRandBelow} from "../helpers/security/crypto-random.js";

test("first-use consent prompt links all published policies",()=>{
 const embed=buildConsentEmbed().toJSON();
 assert.equal(embed.color,0x62676d);
 assert.deepEqual(embed.fields?.map(field=>field.name),POLICY_LINKS.map(policy=>policy.label));
 for(const policy of POLICY_LINKS)assert.ok(embed.fields?.some(field=>field.value?.includes(policy.url)));
 assert.deepEqual(CONSENT_POLICY_VERSIONS,{terms:"2026-11-12",privacy:"2026-11-12",guidelines:"2026-11-12"});
});

test("consent controls are user-bound and have disabled states",()=>{
 const enabled=buildConsentComponents("123456789012345678");
 const disabled=buildConsentComponents("123456789012345678",true);
 assert.equal(enabled[1]?.components.length,2);
 assert.equal(disabled[1]?.components.every(component=>component.toJSON().disabled===true),true);
 assert.deepEqual(parseConsentAction("terms-consent:agree:123456789012345678"),{action:"agree",ownerId:"123456789012345678"});
 assert.equal(parseConsentAction("terms-consent:agree:123"),null);
 assert.equal(parseConsentAction("terms-consent:admin:123456789012345678"),null);
});

test("SHA-512 random selection is bounded and validates its input",()=>{
 assert.equal(secureRandBelow(1),0);
 for(let i=0;i<100;i++){
  const value=secureRandBelow(7);
  assert.ok(Number.isInteger(value)&&value>=0&&value<7);
 }
 assert.throws(()=>secureRandBelow(0),/positive safe integer/);
 assert.throws(()=>secureRandBelow(Number.MAX_SAFE_INTEGER+1),/positive safe integer/);
 assert.ok(["a","b","c"].includes(secureChoice(["a","b","c"])));
 assert.throws(()=>secureChoice([]),/empty sequence/);
});
