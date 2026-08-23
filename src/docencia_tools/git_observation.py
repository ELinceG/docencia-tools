"""Observación local del PR usando merge-base, head SHA y contenido confiable."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import InfrastructureError


def git_output(repo: str | Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=False)
    if result.returncode:
        raise InfrastructureError(f"Git falló ({' '.join(args)}): {result.stderr.strip()}")
    return result.stdout


def observe_diff(repo: str | Path, trusted_ref: str, head_sha: str) -> tuple[str, list[str], set[str]]:
    merge_base = git_output(repo, "merge-base", trusted_ref, head_sha).strip()
    if not merge_base:
        raise InfrastructureError("No se pudo determinar merge_base.")
    changed = git_output(repo, "diff", "--name-only", f"{merge_base}...{head_sha}").splitlines()
    head_files = set(git_output(repo, "ls-tree", "-r", "--name-only", head_sha).splitlines())
    return merge_base, changed, head_files
