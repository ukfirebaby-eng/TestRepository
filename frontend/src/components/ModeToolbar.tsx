import type { ReportAction } from "../reports/navigation";
import type { ViewMode } from "../ui/modeChrome";

type Props = {
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  exportReportActions: ReportAction[];
  onOpenConfiguration: () => void;
  focusedFromReport: boolean;
  onBackToReports: () => void;
};

export function ModeToolbar({
  viewMode,
  onViewModeChange,
  exportReportActions,
  onOpenConfiguration,
  focusedFromReport,
  onBackToReports,
}: Props) {
  return (
    <nav className="command-actions">
      <button onClick={() => onViewModeChange("spatial")} className={viewMode === "spatial" ? "dm-button dm-button-primary active" : "dm-button"}>3D Canvas</button>
      <button onClick={() => onViewModeChange("analyst")} className={viewMode === "analyst" ? "dm-button dm-button-primary active" : "dm-button"}>Analyst Map</button>
      <button onClick={() => onViewModeChange("reports")} className={viewMode === "reports" ? "dm-button dm-button-primary active" : "dm-button"}>Reports</button>
      <button onClick={() => onViewModeChange("accuracy")} className={viewMode === "accuracy" ? "dm-button dm-button-primary active" : "dm-button"}>Accuracy</button>
      {focusedFromReport && (
        <button type="button" className="dm-button dm-button-quiet mode-return-action" onClick={onBackToReports}>Back to Reports</button>
      )}
      {exportReportActions.map((action) => (
        <a key={action.href} href={action.href} target="_blank" rel="noreferrer" className="dm-button command-export">
          {action.label}
        </a>
      ))}
      <button type="button" className="dm-button config-icon-action" aria-label="Configuration" title="Configuration" onClick={onOpenConfiguration}>&#9881;</button>
    </nav>
  );
}
