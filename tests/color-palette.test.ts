import test from "node:test";
import assert from "node:assert/strict";
import {colorForState,PALETTE} from "../helpers/color-palette.js";

test("semantic palette exposes the legacy values and maps states",()=>{
 assert.equal(PALETTE.PRIMARY,0x7c5cff);
 assert.equal(colorForState("success"),PALETTE.SUCCESS);
 assert.equal(colorForState("OK"),PALETTE.SUCCESS);
 assert.equal(colorForState("failure"),PALETTE.DANGER);
 assert.equal(colorForState("panel"),PALETTE.PANEL);
 assert.equal(colorForState("unknown"),PALETTE.PRIMARY);
});
