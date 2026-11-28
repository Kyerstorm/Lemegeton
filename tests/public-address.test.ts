import test from "node:test";
import assert from "node:assert/strict";
import { isPublicUnicastAddress } from "../helpers/security/public-address.js";

test("public IPv4 unicast addresses are accepted", () => {
  for (const address of ["8.8.8.8", "1.1.1.1", "192.0.1.1"]) {
    assert.equal(isPublicUnicastAddress(address), true, address);
  }
});

test("non-public and special-use IPv4 ranges are rejected", () => {
  for (const address of [
    "0.0.0.1",
    "10.0.0.1",
    "100.64.0.1",
    "127.0.0.1",
    "169.254.1.1",
    "172.16.0.1",
    "192.0.0.1",
    "192.0.2.1",
    "192.31.196.1",
    "192.52.193.1",
    "192.88.99.1",
    "192.168.1.1",
    "192.175.48.1",
    "198.18.0.1",
    "198.51.100.1",
    "203.0.113.1",
    "224.0.0.1",
    "240.0.0.1",
    "255.255.255.255",
  ]) {
    assert.equal(isPublicUnicastAddress(address), false, address);
  }
});

test("public IPv6 global-unicast addresses are accepted", () => {
  for (const address of ["2001:4860:4860::8888", "2606:4700:4700::1111"]) {
    assert.equal(isPublicUnicastAddress(address), true, address);
  }
});

test("IPv6 local, documentation, transition and special-purpose ranges are rejected", () => {
  for (const address of [
    "::",
    "::1",
    "::ffff:7f00:1",
    "fc00::1",
    "fd12:3456::1",
    "fe80::1",
    "ff02::1",
    "2001::1",
    "2001:20::1",
    "2001:db8::1",
    "2002:0808:0808::1",
    "3fff:0001::1",
    "64:ff9b::7f00:1",
  ]) {
    assert.equal(isPublicUnicastAddress(address), false, address);
  }
});

test("IPv4-mapped IPv6 addresses inherit the embedded IPv4 policy", () => {
  assert.equal(isPublicUnicastAddress("::ffff:8.8.8.8"), true);
  assert.equal(isPublicUnicastAddress("::ffff:127.0.0.1"), false);
  assert.equal(isPublicUnicastAddress("::ffff:192.0.2.1"), false);
});

test("malformed and non-IP values fail closed", () => {
  for (const address of ["", "example.com", "2001:::1", "fe80::1%eth0", "999.1.1.1"]) {
    assert.equal(isPublicUnicastAddress(address), false, address);
  }
});
