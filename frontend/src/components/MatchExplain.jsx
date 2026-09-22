import { formatMatchScore, hasLowTextSimilarity } from "../formatMatchScore";

export default function MatchExplain({ score, reasons, semanticScore }) {
  const percent = formatMatchScore(score);
  const checks = Array.isArray(reasons) ? reasons.filter(Boolean) : [];

  return (
    <div className="match-explain">
      <p className="match-score-label">ML Match Score</p>
      <p className="match-score-value">{percent}</p>
      {checks.length > 0 && (
        <div className="match-compat">
          <p className="match-compat__title">Compatibility checks</p>
          <ul className="match-compat__list">
            {checks.map((reason) => (
              <li key={reason}>✓ {reason}</li>
            ))}
          </ul>
        </div>
      )}
      {hasLowTextSimilarity(semanticScore) && (
        <p className="match-compat__note">
          Text similarity is lower because supplier and client product descriptions differ.
        </p>
      )}
    </div>
  );
}
