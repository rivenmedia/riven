/** KPI heading with an info control that shows a description on hover or focus. */
export function KpiCardHeading({
  label,
  description,
}: {
  label: string;
  description: string;
}) {
  return (
    <h3 className="kpi-card__heading">
      <span>{label}</span>
      <span className="kpi-info-tip">
        <button
          type="button"
          className="kpi-info-tip__trigger"
          aria-label={`${label}: ${description}`}
        >
          i
        </button>
        <span className="kpi-info-tip__popup" role="tooltip">
          {description}
        </span>
      </span>
    </h3>
  );
}
