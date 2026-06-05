import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ExecutiveReport, NarrativeReport } from "./GeneratedReportsPanel";

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

describe("NarrativeReport grounding", () => {
  it("renders provenance when chapters expose claim fields directly", () => {
    render(<NarrativeReport payload={{
      overall_assessment: "High Risk",
      summary_narrative: "Narrative report is grounded by claims.",
      chapters: [{
        title: "Schedule and dependency risk",
        narrative: "The programme depends on a security approval chain.",
        confidence_score: 0.74,
        confidence_level: "medium",
        claim_ids: ["claim_7"],
        evidence_span_ids: ["span_7", "span_8"],
      }],
    }} />);

    expect(screen.getByText("Medium confidence 74%")).toBeTruthy();
    expect(screen.getByText("1 claim · 2 evidence spans")).toBeTruthy();
  });
});
