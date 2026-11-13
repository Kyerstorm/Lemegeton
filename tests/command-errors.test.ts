import test from "node:test";
import assert from "node:assert/strict";
import {safeInteractionErrorMessage} from "../helpers/commands/command-errors.js";

test("interaction errors map permission, missing-resource and expiry failures safely",()=>{
 assert.match(safeInteractionErrorMessage({code:50013}),/missing a required permission/i);
 assert.match(safeInteractionErrorMessage({code:10008}),/no longer available/i);
 assert.match(safeInteractionErrorMessage({code:10062}),/expired/i);
});

test("interaction errors map invalid payloads and service failures",()=>{
 assert.match(safeInteractionErrorMessage({code:50035}),/invalid/i);
 assert.match(safeInteractionErrorMessage({status:429}),/rate-limiting/i);
 assert.match(safeInteractionErrorMessage({status:503}),/temporarily unavailable/i);
});

test("unknown errors never expose exception messages",()=>{
 const message=safeInteractionErrorMessage(new Error("secret token=do-not-leak"));
 assert.match(message,/\/feedback/);
 assert.doesNotMatch(message,/secret|do-not-leak/);
});
