import test from "node:test";
import assert from "node:assert/strict";

import { AuthRequiredError, authenticatedHeaders } from "../auth.mjs";


test("human session header is attached without mutating caller headers", () => {
  const source = { "Content-Type": "application/json" };
  const headers = authenticatedHeaders(source, "vf1.test-owner.fixture-secret-value-long-enough");
  assert.deepEqual(source, { "Content-Type": "application/json" });
  assert.equal(headers.Authorization, "Bearer vf1.test-owner.fixture-secret-value-long-enough");
});


test("missing human session fails closed", () => {
  assert.throws(() => authenticatedHeaders({}, ""), AuthRequiredError);
});
