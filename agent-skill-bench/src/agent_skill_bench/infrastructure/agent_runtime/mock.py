"""Deterministic mock runtime for local plumbing tests."""

from __future__ import annotations

import json

from .base import AgentRunResult, AgentRunSpec


class MockAgentRuntime:
    """A deterministic runtime that handles both candidate and judge use cases."""

    name = "mock"

    def run(self, spec: AgentRunSpec) -> AgentRunResult:
        """Return stable mock outputs for the requested purpose."""

        if spec.purpose == "candidate":
            output_text = f"[mock:{spec.metadata.get('case_mode', 'unknown')}] {spec.prompt}"
            return AgentRunResult(output_text=output_text, metadata=dict(spec.metadata))

        payload = _mock_judge_payload(spec)
        return AgentRunResult(
            output_text=json.dumps(payload),
            parsed_output=payload,
            metadata=dict(spec.metadata),
        )


def _mock_judge_payload(spec: AgentRunSpec) -> dict[str, object]:
    """Build a deterministic mock judge payload from prior rule assessment."""

    contract_total = int(spec.metadata.get("rule_contract_total", 0))
    contract_passed = int(spec.metadata.get("rule_contract_passed", 0))
    rule_total = int(spec.metadata.get("rule_total", 0))
    rule_passed = int(spec.metadata.get("rule_passed", 0))
    candidate_output = str(spec.metadata.get("candidate_output", ""))
    rule_assessment_present = bool(spec.metadata.get("has_rule_assessment", False))
    rule_assessment_passed = bool(spec.metadata.get("rule_assessment_passed", False))

    passed = rule_assessment_passed if rule_assessment_present else bool(candidate_output.strip())
    return {
        "passed": passed,
        "summary": (
            f"Mock judge scored {spec.metadata.get('case_id', '<unknown>')} from existing rule assessment."
            if rule_assessment_present
            else f"Mock judge scored {spec.metadata.get('case_id', '<unknown>')} from non-empty output."
        ),
        "dimensions": [
            {
                "name": "contract_adherence",
                "score": _scaled_score(contract_passed, contract_total),
                "rationale": f"{contract_passed}/{contract_total} contract checks passed.",
            },
            {
                "name": "rule_adherence",
                "score": _scaled_score(rule_passed, rule_total),
                "rationale": f"{rule_passed}/{rule_total} rule checks passed.",
            },
        ],
    }


def _scaled_score(passed: int, total: int) -> int:
    """Map check counts to a stable 0-3 score."""

    if total == 0:
        return 0
    ratio = passed / total
    if ratio >= 1.0:
        return 3
    if ratio >= 0.67:
        return 2
    if ratio > 0:
        return 1
    return 0
