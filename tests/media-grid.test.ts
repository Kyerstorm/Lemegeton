import test from "node:test";
import assert from "node:assert/strict";
import {parseGridTitles} from "../helpers/media-grid.js";

test("3x3 grid title parser keeps exactly nine cleaned titles",()=>{
 const titles=parseGridTitles(" One \n Two\nThree\nFour\nFive\nSix\nSeven\nEight\nNine ");
 assert.equal(titles.length,9);
 assert.deepEqual(titles.slice(0,2),["One","Two"]);
 assert.equal(titles[8],"Nine");
});

test("3x3 grid title parser rejects wrong counts and oversized entries",()=>{
 assert.throws(()=>parseGridTitles("one\ntwo"),/exactly nine/);
 assert.throws(()=>parseGridTitles(Array.from({length:10},(_,i)=>"Title "+i).join("\n")),/exactly nine/);
 assert.throws(()=>parseGridTitles(["x",...Array.from({length:8},(_,i)=>"Title "+i)].join("\n")),/between 2 and 100/);
 assert.throws(()=>parseGridTitles(["x".repeat(101),...Array.from({length:8},(_,i)=>"Title "+i)].join("\n")),/between 2 and 100/);
});
