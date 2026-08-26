export const RADAR_VIEWS = Object.freeze({
  trending: "Trending now",
  rising: "Rising fast",
  breakout: "Breakout",
  early: "Early signals",
  cross_platform: "Cross-platform",
  low_competition: "Low competition",
  monetization: "High monetization",
  saturation: "Near saturation",
});

export function clusterScore(cluster) {
  return Number(cluster?.score?.total_score ?? 0);
}

export function viewMatches(cluster, view) {
  const components = cluster?.score?.components ?? {};
  switch (view) {
    case "rising":
      return ["rising", "breakout"].includes(cluster.lifecycle);
    case "breakout":
      return cluster.lifecycle === "breakout";
    case "early":
      return ["discovered", "rising"].includes(cluster.lifecycle) && Number(cluster.signal_count) <= 2;
    case "cross_platform":
      return (cluster.platforms ?? []).length >= 2;
    case "low_competition":
      return Number(components.competition ?? 100) <= 35;
    case "monetization":
      return Number(components.monetization_fit ?? 0) >= 80;
    case "saturation":
      return Number(components.saturation ?? 0) >= 65;
    default:
      return true;
  }
}

export function filterClusters(clusters, filters) {
  const now = filters.now ? new Date(filters.now) : new Date();
  const cutoff = filters.days ? new Date(now.getTime() - Number(filters.days) * 86_400_000) : null;
  return [...clusters]
    .filter((cluster) => viewMatches(cluster, filters.view ?? "trending"))
    .filter((cluster) => !filters.platform || (cluster.platforms ?? []).includes(filters.platform))
    .filter((cluster) => !filters.country || (cluster.countries ?? []).includes(filters.country))
    .filter((cluster) => !filters.language || (cluster.languages ?? []).includes(filters.language))
    .filter((cluster) => !filters.format || (cluster.formats ?? []).includes(filters.format))
    .filter((cluster) => !cutoff || new Date(cluster.last_observed_at) >= cutoff)
    .filter((cluster) => !filters.query || `${cluster.topic} ${cluster.summary}`.toLocaleLowerCase("vi").includes(filters.query.toLocaleLowerCase("vi")))
    .sort((left, right) => clusterScore(right) - clusterScore(left) || left.topic.localeCompare(right.topic, "vi"));
}

export function formatScore(value) {
  const number = Number(value ?? 0);
  return Number.isFinite(number) ? number.toFixed(1) : "0.0";
}

export function formatVnd(value) {
  if (value === null || value === undefined) return "Chưa đặt";
  return `${new Intl.NumberFormat("vi-VN").format(Number(value))} ₫`;
}

export function lifecycleLabel(value) {
  return ({
    discovered: "Mới phát hiện",
    rising: "Đang tăng",
    breakout: "Bùng nổ",
    mainstream: "Phổ biến",
    saturated: "Gần bão hòa",
    declining: "Đang giảm",
    expired: "Hết hạn",
  })[value] ?? value;
}

export function lifecycleTone(value) {
  if (value === "breakout") return "hot";
  if (value === "rising") return "rising";
  if (["saturated", "declining", "expired"].includes(value)) return "warning";
  return "neutral";
}
