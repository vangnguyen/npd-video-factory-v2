import test from "node:test";
import assert from "node:assert/strict";

import {
  RADAR_VIEWS,
  filterClusters,
  formatScore,
  formatVnd,
  lifecycleLabel,
  viewMatches,
} from "../trend-utils.mjs";

const clusters = [
  {
    cluster_id: "trc_breakout",
    topic: "AI video bất động sản",
    summary: "Cross-platform signal",
    lifecycle: "breakout",
    signal_count: 3,
    platforms: ["youtube", "tiktok", "google_trends"],
    countries: ["VN"],
    languages: ["vi"],
    formats: ["vertical_short"],
    last_observed_at: "2026-08-26T06:30:00Z",
    score: { total_score: 84.2, components: { competition: 25, monetization_fit: 86, saturation: 42 } },
    provenance: {},
  },
  {
    cluster_id: "trc_saturated",
    topic: "Lãi suất vay mua nhà",
    summary: "Competitive topic",
    lifecycle: "saturated",
    signal_count: 12,
    platforms: ["rss"],
    countries: ["VN"],
    languages: ["vi"],
    formats: ["news_explainer"],
    last_observed_at: "2026-08-20T06:30:00Z",
    score: { total_score: 51.4, components: { competition: 88, monetization_fit: 82, saturation: 82 } },
    provenance: {},
  },
];

test("declares all eight required radar views", () => {
  assert.equal(Object.keys(RADAR_VIEWS).length, 8);
  assert.ok(RADAR_VIEWS.cross_platform);
  assert.ok(RADAR_VIEWS.low_competition);
  assert.ok(RADAR_VIEWS.saturation);
});

test("radar view rules remain deterministic and explainable", () => {
  assert.equal(viewMatches(clusters[0], "breakout"), true);
  assert.equal(viewMatches(clusters[0], "cross_platform"), true);
  assert.equal(viewMatches(clusters[0], "low_competition"), true);
  assert.equal(viewMatches(clusters[1], "saturation"), true);
  assert.equal(viewMatches(clusters[1], "low_competition"), false);
});

test("filters by view, platform and search while sorting by estimate", () => {
  assert.deepEqual(filterClusters(clusters, { view: "trending" }).map((item) => item.cluster_id), ["trc_breakout", "trc_saturated"]);
  assert.deepEqual(filterClusters(clusters, { view: "cross_platform" }).map((item) => item.cluster_id), ["trc_breakout"]);
  assert.deepEqual(filterClusters(clusters, { view: "trending", platform: "rss" }).map((item) => item.cluster_id), ["trc_saturated"]);
  assert.deepEqual(filterClusters(clusters, { view: "trending", country: "VN", language: "vi", format: "vertical_short" }).map((item) => item.cluster_id), ["trc_breakout"]);
  assert.deepEqual(filterClusters(clusters, { view: "trending", days: 2, now: "2026-08-27T00:00:00Z" }).map((item) => item.cluster_id), ["trc_breakout"]);
  assert.deepEqual(filterClusters(clusters, { view: "trending", query: "AI VIDEO" }).map((item) => item.cluster_id), ["trc_breakout"]);
});

test("formats scores, VND and Vietnamese lifecycle labels", () => {
  assert.equal(formatScore(84.24), "84.2");
  assert.match(formatVnd(100_000_000), /100[.\s]000[.\s]000\s₫/);
  assert.equal(lifecycleLabel("breakout"), "Bùng nổ");
});
