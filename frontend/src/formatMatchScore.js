export function formatMatchScore(value) {
  if (value === null || value === undefined || value === "") {
    return "Not available";
  }
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) {
    return "Not available";
  }
  const percent = Math.round(numeric * 10000) / 100;
  const label = Number.isInteger(percent)
    ? String(percent)
    : percent.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  return `${label}%`;
}

export function formatMatchLabel(value) {
  const score = formatMatchScore(value);
  if (score === "Not available") return score;
  return `${score} ML score`;
}

export const LOW_TEXT_SIMILARITY = 0.35;

export function hasLowTextSimilarity(value) {
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) && numeric < LOW_TEXT_SIMILARITY;
}

export function matchScoreValue(value) {
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : -1;
}

export function sortByMatchScore(items, getScore = (item) => item.final_score) {
  return [...items].sort((left, right) => matchScoreValue(getScore(right)) - matchScoreValue(getScore(left)));
}

