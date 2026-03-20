"""
agent_propose.py — Calls the Claude API to propose a modification to train.py.

Usage:
    python agent_propose.py \\
        --program program.md \\
        --code train.py \\
        --log results.tsv \\
        [--error-log run.log]

Outputs the new train.py content to stdout.
Requires ANTHROPIC_API_KEY environment variable.
"""

import argparse
import os
import sys


def read_file(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def build_prompt(program, code, log, error_log):
    parts = []

    parts.append(
        "You are an expert machine learning researcher running an automated experiment loop.\n"
        "Your job is to propose ONE focused, concrete improvement to train.py that will lower "
        "the validation bits-per-byte (BPB) on a character-level language model.\n\n"
        "## Rules\n"
        "- Return ONLY the complete new contents of train.py. No explanation, no markdown fences, "
        "no commentary — just raw Python code.\n"
        "- The final stdout line must remain exactly: FINAL_VAL_BPB=<float>\n"
        "- Training must complete within 300 seconds (cfg.train_seconds must stay 300).\n"
        "- Propose exactly ONE change. Do not rewrite everything.\n"
    )

    parts.append(f"\n## Research Agenda (program.md)\n\n{program}\n")
    parts.append(f"\n## Current train.py\n\n{code}\n")

    if log:
        parts.append(f"\n## Experiment History (results.tsv)\n\n{log}\n")

    if error_log:
        parts.append(
            f"\n## IMPORTANT: The last experiment CRASHED with this error log.\n"
            f"Fix the bug that caused the crash before proposing any new improvement.\n\n"
            f"{error_log}\n"
        )
    else:
        parts.append(
            "\n## Your Task\n"
            "Analyze the experiment history and the current train.py, then propose ONE specific "
            "change that is likely to lower the validation BPB. Consider what has already been "
            "tried (from results.tsv) and pick something novel.\n"
        )

    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", default="program.md")
    parser.add_argument("--code", default="train.py")
    parser.add_argument("--log", default="results.tsv")
    parser.add_argument("--error-log", default=None)
    args = parser.parse_args()

    # Read inputs
    program = read_file(args.program)
    code = read_file(args.code)
    log = read_file(args.log)
    error_log = read_file(args.error_log) if args.error_log else ""

    prompt = build_prompt(program, code, log, error_log)

    # Call Claude API
    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic package not installed. Run: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=(
            "You are a machine learning researcher working on an automated experiment loop. "
            "When asked to propose a change to train.py, return ONLY the complete new Python "
            "source code — no markdown, no explanation, no code fences. Raw Python only."
        ),
        messages=[{"role": "user", "content": prompt}],
    )

    new_code = response.content[0].text.strip()

    # Strip accidental markdown fences if the model added them
    if new_code.startswith("```"):
        lines = new_code.splitlines()
        # Remove first and last fence lines
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        new_code = "\n".join(lines)

    print(new_code)


if __name__ == "__main__":
    main()
