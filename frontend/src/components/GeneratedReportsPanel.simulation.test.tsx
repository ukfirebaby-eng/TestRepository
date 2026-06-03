import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SimulationReport } from "./GeneratedReportsPanel";

describe("SimulationReport", () => {
  it("renders simulator payloads as readable report cards instead of raw JSON", () => {
    const payload = {
      blast_radius: {
        svi: 0.0005,
        nodes: [
          {
            id: "analytics_engine",
            name: "Analytics Engine",
            svi_contribution: 0.0005,
            dependency_count: 3,
            cascade_depth: 3,
            blast_radius_count: 7,
          },
        ],
      },
      black_swan: {
        scenarios: [
          {
            title: "Unexpected authentication service outage",
            trigger_node: "Central Authentication Service",
            cascade_path: ["Central Authentication Service", "approval gate", "dependent workflow"],
          },
        ],
      },
      monte_carlo: {
        available: true,
        p50_delay_days: 125,
        p80_delay_days: 230,
        p95_delay_days: 369,
        at_risk_nodes: [
          { id: "n6", name: "deadline", mean_delay_days: 90 },
        ],
      },
    };

    const { container } = render(<SimulationReport payload={payload} />);

    expect(screen.getByText("SVI 0.0005")).toBeTruthy();
    expect(screen.getByText(/Analytics Engine affects 7 downstream nodes/i)).toBeTruthy();
    expect(screen.getByText("1 scenario")).toBeTruthy();
    expect(screen.getAllByText(/Unexpected authentication service outage/i).length).toBeGreaterThan(0);
    expect(screen.getByText("P95 369 days")).toBeTruthy();
    expect(screen.getByText(/P50 125 days/i)).toBeTruthy();
    expect(container.textContent).not.toContain('{"');
  });

  it("renders zero-day Monte Carlo forecasts as available without delay-sensitive nodes", () => {
    const payload = {
      blast_radius: { svi: 0, nodes: [] },
      black_swan: { scenarios: [] },
      monte_carlo: {
        available: true,
        p50_delay_days: 0,
        p80_delay_days: 0,
        p95_delay_days: 0,
        at_risk_nodes: Array.from({ length: 10 }, (_, index) => ({
          id: `node_${index}`,
          name: `Node ${index}`,
          mean_delay_days: 0,
        })),
      },
    };

    render(<SimulationReport payload={payload} />);

    expect(screen.getByText("P95 0 days")).toBeTruthy();
    expect(screen.getByText(/P50 0 days/i)).toBeTruthy();
    expect(screen.getByText(/No delay-sensitive nodes identified/i)).toBeTruthy();
    expect(screen.queryByText("Forecast unavailable")).toBeNull();
    expect(screen.queryByText(/10 nodes flagged as delay-sensitive/i)).toBeNull();
    expect(screen.queryByText("Node 0")).toBeNull();
  });

  it("does not show stale delay-sensitive node counts when Monte Carlo is unavailable", () => {
    const payload = {
      blast_radius: { svi: 0, nodes: [] },
      black_swan: { scenarios: [] },
      monte_carlo: {
        available: false,
        reason: "No schedule data found in this document",
        at_risk_nodes: [{ id: "stale_node", name: "Stale node", mean_delay_days: 12 }],
      },
    };

    render(<SimulationReport payload={payload} />);

    expect(screen.getByText("Forecast unavailable")).toBeTruthy();
    expect(screen.getByText("No schedule data found in this document")).toBeTruthy();
    expect(screen.queryByText(/nodes flagged as delay-sensitive/i)).toBeNull();
    expect(screen.queryByText("Stale node")).toBeNull();
  });
});
