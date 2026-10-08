const { test } = require("node:test");
const assert = require("node:assert/strict");
const { approvalBlockers, sourceMatches, epoch } = require("../../src/mostrador/static/app.js");

const now = Date.parse("2026-10-08T12:00:00Z");
const workspace = { actor: { role: "operator" }, source_revision: "r1", analyzed_revision: "r1", analysis_status: "ready" };
const recommendation = { status: "pending", approvable: true, expires_at: now / 1000 + 900, grounding: { blockers: [] } };

test("approval requires matching analyzed source revision", () => {
  assert.deepEqual(approvalBlockers(workspace, recommendation, now), []);
  assert.ok(approvalBlockers({ ...workspace, source_revision: "r2" }, recommendation, now).some(text => text.includes("fuentes")));
  assert.ok(approvalBlockers({ ...workspace, analyzed_revision: null }, recommendation, now).length);
  assert.ok(approvalBlockers({ ...workspace, analysis_status: "analysis_failed" }, recommendation, now).length);
});
test("viewer, already-decided, blocked and expired proposals cannot be approved", () => {
  assert.ok(approvalBlockers({ ...workspace, actor: { role: "viewer" } }, recommendation, now).length);
  for (const change of [{ status: "approved" }, { approvable: false }, { expires_at: now / 1000 }, { expires_at: null }, { grounding: { blockers: ["Falta presupuesto"] } }]) {
    assert.ok(approvalBlockers(workspace, { ...recommendation, ...change }, now).length);
  }
});
test("expiry accepts API epoch seconds and ISO timestamps", () => {
  assert.equal(epoch(now / 1000), now);
  assert.equal(epoch("2026-10-08T12:00:00Z"), now);
  assert.deepEqual(approvalBlockers(workspace, { ...recommendation, expires_at: "2026-10-08T12:15:00Z" }, now), []);
});
test("sources can be searched without matching case or accents", () => {
  const source = { messages: [{ text: "¿Hay promoción en Quito?" }] };
  assert.equal(sourceMatches(source, "PROMOCION"), true);
  assert.equal(sourceMatches(source, "guayaquil"), false);
  assert.equal(sourceMatches(source, ""), true);
});
