"""Case discovery tests."""

from pathlib import Path

from agent_skill_bench import discover_case_files


def test_discover_case_files_finds_json_cases(tmp_path: Path):
    case_dir = tmp_path / "agent-skill-uiux" / "benchmarks" / "cases"
    case_dir.mkdir(parents=True)
    expected = case_dir / "sample.json"
    expected.write_text("{}", encoding="utf-8")

    discovered = discover_case_files(tmp_path)

    assert discovered == [expected]
