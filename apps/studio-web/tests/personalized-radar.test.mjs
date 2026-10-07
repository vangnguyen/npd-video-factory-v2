import assert from 'node:assert/strict';
import test from 'node:test';
import {clusterScore, filterClusters} from '../trend-utils.mjs';

const original = score => ({topic: 'fixture', summary: 'fixture', score: {total_score: score}});
const advised = (base, personal) => ({...original(base), learning_feedback: {personalized_opportunity: {
  algorithm_version: 'personalized-opportunity-estimate-v1', estimated: true, recommendation_only: true,
  autonomous_execution: false, personalized_planning_score: personal}}});

test('explicit personal planning scores rank proposals while preserving base trend facts', () => {
  const a = advised(80, 65), b = advised(70, 85);
  assert.equal(clusterScore(a), 65); assert.equal(a.score.total_score, 80);
  assert.deepEqual(filterClusters([a, b], {}).map(item => item.score.total_score), [70, 80]);
});

test('absent or contradictory personalization preserves original estimates', () => {
  assert.equal(clusterScore(original(80)), 80);
  for (const value of [NaN, Infinity, -1, 101, '90']) assert.equal(clusterScore(advised(80, value)), 80);
  const invalid = advised(80, 95); invalid.learning_feedback.personalized_opportunity.autonomous_execution = true;
  assert.equal(clusterScore(invalid), 80);
});
