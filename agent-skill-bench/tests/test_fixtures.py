"""Suite and case loading tests."""

from pathlib import Path

from agent_skill_bench import (
    BenchmarkKind,
    BenchmarkMode,
    get_execution_profile,
    load_case,
    load_suite,
    resolve_case,
)


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def test_load_case_from_json():
    case = load_case(FIXTURE_DIR / "sample-generate.json")

    assert case.schema_version == 1
    assert case.id == "uiux.generate.sample"
    assert case.mode is BenchmarkMode.GENERATE
    assert case.kind is BenchmarkKind.PROMPT
    assert case.expectations.must_cover == ["goal clarity", "primary action"]
    assert case.source_path is not None

    rendered = case.render_prompt()
    assert rendered.startswith("Design a pricing page.")
    assert "Context Notes:" in rendered
    assert "- desktop-first" in rendered
    assert "- comparison clarity matters" in rendered


def test_load_suite_from_json():
    suite = load_suite(FIXTURE_DIR / "sample-suite.json")

    assert suite.schema_version == 1
    assert suite.suite_id == "uiux"
    assert suite.default_execution_profile == "isolated_prompt"
    assert suite.default_evaluation_profile == "uiux-default"
    assert suite.default_judge_profile == "uiux-judge"
    assert "uiux-default" in suite.evaluation_profiles
    assert "uiux-judge" in suite.judge_profiles
    assert len(suite.resolve_default_skills()) == 1
    assert suite.resolve_default_skills()[0].name == "uiux"
    assert suite.benchmark_prompt is not None
    assert suite.benchmark_prompt.preamble == ["You are being benchmarked on a UI/UX skill."]
    assert suite.benchmark_prompt.mode_headings[BenchmarkMode.GENERATE][0] == "Screen Goal"


def test_prompt_case_renders_attached_files():
    case = load_case(FIXTURE_DIR / "sample-context-bundle.json")

    rendered = case.render_prompt()

    assert case.kind is BenchmarkKind.PROMPT
    assert "Review this settings screen." in rendered
    assert "Context Notes:" in rendered
    assert "mobile-first" in rendered
    assert "The design system already exists." in rendered


def test_prompt_case_without_context_renders_prompt_only():
    case = load_case(FIXTURE_DIR / "sample-generate.json")
    case.context = []

    assert case.render_prompt() == "Design a pricing page."


def test_repo_case_resolves_repo_root_and_working_dir():
    case = load_case(FIXTURE_DIR / "sample-repo.json")

    assert case.kind is BenchmarkKind.REPO
    assert case.resolve_repo_root() is not None
    assert case.resolve_repo_root().name == "fixtures-repo"
    assert case.resolve_working_dir() is not None
    assert case.resolve_working_dir().name == "app"


def test_resolve_case_applies_suite_defaults(tmp_path: Path):
    suite_dir = tmp_path / "agent-skill-uiux" / "benchmarks"
    case_dir = suite_dir / "cases"
    skill_dir = tmp_path / "agent-skill-uiux" / "skills" / "uiux"
    case_dir.mkdir(parents=True)
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("Use this skill.", encoding="utf-8")
    (suite_dir / "suite.json").write_text(
        """
        {
          "schema_version": 1,
          "suite_id": "uiux",
          "title": "UIUX Suite",
          "default_skills": ["../skills/uiux"],
          "default_execution_profile": "isolated_prompt",
          "default_evaluation_profile": "uiux-default",
          "default_judge_profile": "uiux-judge",
          "evaluation_profiles": {
            "uiux-default": {
              "forbid_code_fences": true,
              "require_first_heading": true,
              "mode_rules": {
                "Generate": [
                  {
                    "code": "generate_has_risks",
                    "kind": "section_non_empty",
                    "section": "Layout Blocks",
                    "message": "Layout Blocks section is non-empty."
                  }
                ]
              }
            }
          },
          "judge_profiles": {
            "uiux-judge": {
              "dimensions": [
                {
                  "name": "task_fit",
                  "description": "Does the answer perform the task?"
                }
              ]
            }
          },
          "benchmark_prompt": {
            "preamble": ["You are being benchmarked on a UI/UX skill."],
            "shared_rules": ["Use the required headings exactly once and in order."],
            "mode_headings": {
              "Generate": ["Screen Goal", "Layout Blocks"]
            }
          }
        }
        """,
        encoding="utf-8",
    )
    (case_dir / "sample.json").write_text(
        """
        {
          "schema_version": 1,
          "id": "uiux.generate.example",
          "title": "Example",
          "mode": "Generate",
          "prompt": "Design a page.",
          "expectations": {
            "must_cover": [],
            "must_avoid": [],
            "golden_signals": []
          }
        }
        """,
        encoding="utf-8",
    )

    resolved = resolve_case(case_dir / "sample.json")

    assert resolved.suite_id == "uiux"
    assert resolved.mode is BenchmarkMode.GENERATE
    assert resolved.execution_profile == get_execution_profile("isolated_prompt")
    assert resolved.evaluation_profile == "uiux-default"
    assert resolved.judge_profile == "uiux-judge"
    assert resolved.suite.resolve_evaluation_profile("uiux-default") is not None
    assert resolved.suite.resolve_judge_profile("uiux-judge") is not None
    assert resolved.skill_paths == [skill_dir.resolve()]
    rendered = resolved.render_prompt()
    assert "You are being benchmarked on a UI/UX skill." in rendered
    assert "User Request:" in rendered
    assert "Benchmark Rules:" in rendered
    assert "Required Output Headings (Generate):" in rendered
    assert "- Screen Goal" in rendered
    assert rendered.endswith("Return only the final answer.")


def test_resolve_case_can_disable_suite_skills(tmp_path: Path):
    suite_dir = tmp_path / "agent-skill-uiux" / "benchmarks"
    case_dir = suite_dir / "cases"
    case_dir.mkdir(parents=True)
    (suite_dir / "suite.json").write_text(
        """
        {
          "schema_version": 1,
          "suite_id": "uiux",
          "title": "UIUX Suite",
          "default_skills": ["../skills/uiux"],
          "default_execution_profile": "isolated_prompt"
        }
        """,
        encoding="utf-8",
    )
    (case_dir / "sample.json").write_text(
        """
        {
          "schema_version": 1,
          "id": "uiux.generate.example",
          "title": "Example",
          "mode": "Generate",
          "prompt": "Design a page.",
          "expectations": {
            "must_cover": [],
            "must_avoid": [],
            "golden_signals": []
          }
        }
        """,
        encoding="utf-8",
    )

    resolved = resolve_case(case_dir / "sample.json", no_skills=True)

    assert resolved.skill_paths == []
