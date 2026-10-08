"""The repository's own skills folder builds both teams (every referenced skill exists and parses)."""

from __future__ import annotations

import pytest

from bidcore.ledger.models import SECTIONS, new_ledger
from harness import llm
from harness.context import RunContext
from harness.skills import list_skills
from harness.teams import build_team, team_roster
from harness.workspace import BidWorkspace
from tests.harness.fakes import factory


@pytest.mark.parametrize("team", ["effort", "proposal"])
def test_team_builds_from_repo_skills(tmp_path, team):
    llm.set_model_factory(factory({}))
    try:
        ws = BidWorkspace.open(f"skills-{team}", base=tmp_path)
        ws.ledger.save(new_ledger(ws.bid_id))
        run = RunContext(ws=ws, team=team)
        build_team(run, "ACME")
        roster = team_roster(run)
        written = {s for r in roster for s in r["writes"]}
        required = set(run.team_config["required_sections"]) - {"drafts"}
        assert required <= written | {"drafts"}, required - written
        assert all(s in SECTIONS or s in ("drafts", "review") for s in written)
    finally:
        llm.set_model_factory(None)


def test_every_skill_has_valid_frontmatter():
    skills = {s.name: s for s in list_skills()}
    for name, skill in skills.items():
        assert skill.description and len(skill.description) <= 1024, name
        assert skill.path.name == name
        assert (skill.path / "SKILL.md").read_text(encoding="utf-8").count("\n") < 500, name
