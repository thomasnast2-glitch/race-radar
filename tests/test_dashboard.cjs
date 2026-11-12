const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname, '..', 'radar-status.js'), 'utf8');
const summarize = vm.runInNewContext(script + '; RadarStatus.summarize');
const now = new Date('2026-11-12T12:00:00Z');

test('fresh reports with working sources are healthy', () => {
  assert.equal(summarize('hyrox', {last_checked: '2026-11-12', flux_accessibles: 3,
    flux_total: 3, erreurs: []}, now).warning, false);
});
test('old or undated reports require attention', () => {
  assert.equal(summarize('running', {checkedAt: '2026-11-01', sources: []}, now).warning, true);
  assert.equal(summarize('running', {sources: []}, now).warning, true);
});
test('source failures stay visible even after a successful workflow', () => {
  const report = summarize('cycling', {lastCheckedAt: '2026-11-12',
    sources: [{result: 'OK'}, {result: 'ERROR'}]}, now);
  assert.equal(report.warning, true);
  assert.match(report.text, /1\/2 source/);
  assert.match(report.text, /1 erreur/);
});
