import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { active, canRun, requestFor, restoredRequest } from "../src/lib/api/run-policy.ts";
import { pollRuns } from "../src/lib/api/run-polling.ts";

const ready = { ready: true, reviewed: true, dirty: false, conflict: false, busy: false, occupied: false };
const preview = { revision: 7, source_sha256: `sha256:${"a".repeat(64)}`, plan_sha256: `sha256:${"b".repeat(64)}` };
const flush = () => new Promise(resolve => setImmediate(resolve));

test("Run requires saved readiness, reviewed hashes and free capacity", () => {
  assert.equal(canRun(ready), true);
  for (const field of ["ready", "reviewed", "dirty", "conflict", "busy", "occupied"]) {
    assert.equal(canRun({ ...ready, [field]: !ready[field] }), false, field);
  }
});

test("request contains frozen revision and hashes, never authoritative source or plan", () => {
  const id = randomUUID();
  assert.deepEqual(requestFor(preview, id), { request_id: id, expected_revision: 7, expected_source_sha256: preview.source_sha256, expected_plan_sha256: preview.plan_sha256 });
  assert.throws(() => requestFor({ ...preview, source_sha256: null }, id));
});

test("lost-response storage preserves logical identity; new attempt gets a different identity", () => {
  const first = requestFor(preview, randomUUID());
  const recovered = restoredRequest(JSON.stringify(first));
  assert.deepEqual(recovered, first);
  assert.notEqual(requestFor(preview, randomUUID()).request_id, recovered.request_id);
});

test("invalid storage cannot supply a revision or request identity", () => {
  for (const value of [null, "broken", "null", "{}", JSON.stringify({ ...requestFor(preview, randomUUID()), expected_revision: 0 }), JSON.stringify({ ...requestFor(preview, randomUUID()), request_id: "-".repeat(36) })]) {
    assert.equal(restoredRequest(value), null);
  }
});

test("only CREATED and RUNNING are active", () => {
  assert.equal(active("CREATED"), true);
  assert.equal(active("RUNNING"), true);
  assert.equal(active("SUCCEEDED"), false);
  assert.equal(active("FAILED"), false);
});

test("polls every two seconds and stops at SUCCEEDED", async context => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  const received = [];
  const states = ["CREATED", "RUNNING", "SUCCEEDED"];
  const dispose = pollRuns(async () => states.shift(), value => received.push(value), active, assert.fail);
  await flush();
  context.mock.timers.tick(1999); await flush();
  assert.deepEqual(received, ["CREATED"]);
  context.mock.timers.tick(1); await flush();
  context.mock.timers.tick(2000); await flush();
  context.mock.timers.tick(10000); await flush();
  assert.deepEqual(received, ["CREATED", "RUNNING", "SUCCEEDED"]);
  dispose();
});

test("FAILED is terminal and never auto-retries", async context => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  let count = 0;
  const dispose = pollRuns(async () => { count++; return "FAILED"; }, () => {}, active, assert.fail);
  await flush(); context.mock.timers.tick(10000); await flush();
  assert.equal(count, 1);
  dispose();
});

test("unmount aborts in-flight read and ignores its late stale response", async () => {
  let complete, signal;
  const received = [];
  const dispose = pollRuns(s => { signal = s; return new Promise(resolve => { complete = resolve; }); }, value => received.push(value), () => true, assert.fail);
  dispose(); complete("RUNNING"); await flush();
  assert.equal(signal.aborted, true);
  assert.deepEqual(received, []);
});

test("navigation clears the next poll timer", async context => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  let count = 0;
  const dispose = pollRuns(async () => { count++; return "RUNNING"; }, () => {}, active, assert.fail);
  await flush(); dispose(); context.mock.timers.tick(10000); await flush();
  assert.equal(count, 1);
});

test("network failure surfaces once and waits for explicit refresh", async context => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  const errors = [];
  const dispose = pollRuns(async () => { throw new Error("Offline"); }, assert.fail, () => true, error => errors.push(error.message));
  await flush(); context.mock.timers.tick(10000); await flush();
  assert.deepEqual(errors, ["Offline"]);
  dispose();
});
