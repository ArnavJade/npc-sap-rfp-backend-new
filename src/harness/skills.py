"""Skill discovery and per-run skill bundles.

Knowledge lives in skills/<name>/SKILL.md (+ reference files). At run start each agent gets its OWN
bundle copied into the bid workspace (workspace/<bid>/skills/<agent>/<skill>/), mounted read-only at
/skills/<agent>/. So:
  * a specialist only ever sees its own skill (no prompt bloat, no cross-talk);
  * the run is reproducible - the exact skill text it used is kept with the bid;
  * a presales edit to a SKILL.md reaches the next run with no code change or image build.
Every skills/scope-* folder is auto-discovered as an effort-team specialist.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

import yaml

from bidcore.paths import skills_dir


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    path: Path
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def ledger_sections(self) -> list[str]:
        raw = self.metadata.get("ledger_sections", "")
        return [s.strip() for s in raw.split(",") if s.strip()]


def read_skill(folder: Path) -> SkillInfo | None:
    md = folder / "SKILL.md"
    if not md.is_file():
        return None
    text = md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    try:
        front = yaml.safe_load(text.split("---", 2)[1]) or {}
    except yaml.YAMLError:
        return None
    name = str(front.get("name") or folder.name).strip()
    meta = {str(k): str(v) for k, v in (front.get("metadata") or {}).items()}
    return SkillInfo(name, str(front.get("description", "")).strip(), folder, meta)


def list_skills(root: Path | None = None) -> list[SkillInfo]:
    root = root or skills_dir()
    found = [read_skill(p) for p in sorted(root.iterdir()) if p.is_dir()] if root.is_dir() else []
    return [s for s in found if s is not None]


def discover(pattern: str, root: Path | None = None) -> list[SkillInfo]:
    """Skills whose folder name matches a glob, e.g. 'scope-*'."""
    return [s for s in list_skills(root) if fnmatch(s.path.name, pattern)]


def bundle(ws_skills_dir: Path, agent: str, skill_names: list[str], root: Path | None = None) -> str:
    """Copy the named skills into the run's bundle for `agent`; return the virtual source path."""
    root = root or skills_dir()
    target = ws_skills_dir / agent
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in skill_names:
        src = root / name
        if not (src / "SKILL.md").is_file():
            raise FileNotFoundError(f"skill '{name}' not found under {root}")
        shutil.copytree(src, target / name)
    return f"/skills/{agent}/"
