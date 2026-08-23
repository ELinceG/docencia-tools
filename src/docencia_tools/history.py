"""Reconstrucción auditable de first_complete_at."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import ActivityConfig
from .errors import InfrastructureError


@dataclass(frozen=True)
class Observation:
    sha: str
    observed_at: datetime
    files: frozenset[str]
    source: str
    approximate: bool = False


@dataclass(frozen=True)
class FirstComplete:
    timestamp: datetime
    sha: str
    source: str
    approximate: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "sha": self.sha,
            "source": self.source,
            "approximate": self.approximate,
        }


def first_complete_at(config: ActivityConfig, slug: str, observations: list[Observation]) -> FirstComplete | None:
    required = set(config.required_for(slug))
    for observation in sorted(observations, key=lambda item: (item.observed_at, item.sha)):
        if required <= observation.files:
            return FirstComplete(observation.observed_at, observation.sha, observation.source, observation.approximate)
    return None


def clamp_to_pr_creation(observations: list[Observation], created_at: datetime) -> list[Observation]:
    """Ninguna entrega puede existir en el PR antes de que el PR sea creado."""

    adjusted: list[Observation] = []
    for observation in observations:
        if observation.observed_at < created_at:
            adjusted.append(
                Observation(
                    observation.sha,
                    created_at,
                    observation.files,
                    f"{observation.source}_clamped_to_pr_created_at",
                    True,
                )
            )
        else:
            adjusted.append(observation)
    return adjusted


def observations_from_git(repo: str | Path, merge_base: str, head_sha: str) -> list[Observation]:
    """Usa fechas de committer; se marca aproximado porque Git no registra el push."""

    root = Path(repo)

    def git(*args: str) -> str:
        result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=False)
        if result.returncode:
            raise InfrastructureError(f"Git no pudo reconstruir el historial: {result.stderr.strip()}")
        return result.stdout

    commits = git("rev-list", "--reverse", "--topo-order", f"{merge_base}..{head_sha}").splitlines()
    observations: list[Observation] = []
    for sha in commits:
        timestamp = datetime.fromisoformat(git("show", "-s", "--format=%cI", sha).strip())
        files = frozenset(git("ls-tree", "-r", "--name-only", sha).splitlines())
        observations.append(Observation(sha, timestamp, files, "git_commit_committer_timestamp", True))
    return observations
