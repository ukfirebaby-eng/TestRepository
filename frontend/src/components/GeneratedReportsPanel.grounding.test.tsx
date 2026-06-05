import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ExecutiveReport } from "./GeneratedReportsPanel";

describe("ExecutiveReport grounding", () => {
  it("renders confidence and claim support for grounded issues", () => {
    render(<ExecutiveReport payload={{
      overall_assessment: "High Risk",
      summary_narrative: "Migration may start before certification.",
      issues: [{
        severity: "high",
        title: "Migration starts before certification",
        plain_english: "Cloud migration is starting before security certification.",
        solution: "Move migration until certification is complete.",
        grounding: {
          confidence_score: 0.96,
          confidence_level: "high",
          claim_ids: ["claim_1"],
          evidence_span_ids: ["span_1", "span_2"],
          evidence_basis: "validated_claims",
        },
      }],
    }} />);

    expect(screen.getByText("High confidence 96%")).toBeTruthy();
    expect(screen.getByText("1 validated claim · 2 evidence spans")).toBeTruthy();
  });

  it("renders provenance when executive issues expose claim fields directly", () => {
    render(<ExecutiveReport payload={{
      overall_assessment: "High Risk",
      summary_narrative: "Migration may start before certification.",
      issues: [{
        severity: "high",
        title: "Migration starts before certification",
        plain_english: "Cloud migration is starting before security certification.",
        solution: "Move migration until certification is complete.",
        confidence_score: 0.88,
        confidence_level: "high",
        claim_ids: ["claim_1", "claim_2"],
        evidence_span_ids: ["span_1"],
      }],
    }} />);

    expect(screen.getByText("High confidence 88%")).toBeTruthy();
    expect(screen.getByText("2 claims · 1 evidence span")).toBeTruthy();
  });
});
