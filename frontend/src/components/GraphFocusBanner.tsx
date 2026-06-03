type Props = {
  visible: boolean;
  label: string;
  onBackToReports: () => void;
  onClearFocus: () => void;
};

export function GraphFocusBanner({ visible, label, onBackToReports, onClearFocus }: Props) {
  if (!visible) return null;

  return (
    <div className="graph-focus-banner">
      <span>Focused from report: {label}</span>
      <button type="button" onClick={onBackToReports}>Back to Reports</button>
      <button type="button" onClick={onClearFocus}>Clear focus</button>
    </div>
  );
}
