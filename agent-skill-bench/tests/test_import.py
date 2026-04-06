"""Smoke tests for the agent_skill_bench package."""

from agent_skill_bench import __version__


def test_package_version():
    assert __version__ == "0.1.0"
