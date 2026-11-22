#!/usr/bin/env python3
"""Restore default-branch-only GitHub Pages publish guards.

Upptime v1.46.5 `update-template` rewrites site.yml, setup.yml, and
update-template.yml from a hardcoded template. There is no .upptimerc.yml
field that injects a branch filter (`status-website.publish` only affects
private repos; `skipGeneratingWebsite` would disable master publishes too).

This script is invoked by `.github/workflows/assert-pages-publish-guards.yml`
whose filename is not in update-template's overwrite list.

Guards:
  * peaceiris "GitHub Pages Deploy" only on the repository default branch
  * keep_files: true so a cached SPA 404.html can still load previous hashed JS
  * Setup CI "Update template" only on the default branch
  * Update Template CI job only on the default branch
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

DEFAULT_BRANCH_IF = (
    "github.ref == format('refs/heads/{0}', github.event.repository.default_branch)"
)

# From upptime/uptime-monitor v1.46.5 src/update-template.ts
OVERWRITTEN_BY_UPDATE_TEMPLATE = frozenset(
    {
        "graphs.yml",
        "response-time.yml",
        "setup.yml",
        "site.yml",
        "summary.yml",
        "update-template.yml",
        "updates.yml",
        "uptime.yml",
    }
)

DEPLOY_USES = "uses: peaceiris/actions-gh-pages@v4"
DEPLOY_NAME = "name: GitHub Pages Deploy"
UPDATE_TEMPLATE_STEP = "Update template"
FORCE_ORPHAN = 'force_orphan: "false"'
KEEP_FILES_LINE = "keep_files: true"


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" "))]


def insert_if_after(lines: list[str], index: int) -> list[str]:
    line = lines[index]
    indent = _indent_of(line)
    if line.lstrip().startswith("- "):
        indent += "  "
    if_line = f"{indent}if: {DEFAULT_BRANCH_IF}\n"
    nxt = lines[index + 1] if index + 1 < len(lines) else ""
    if nxt.strip().startswith("if:") and DEFAULT_BRANCH_IF in nxt:
        if nxt == if_line:
            return lines
        lines[index + 1] = if_line
        return lines
    if nxt.strip().startswith("if:"):
        lines[index + 1] = if_line
        return lines
    lines.insert(index + 1, if_line)
    return lines


def ensure_pages_deploy_if(text: str) -> str:
    if DEPLOY_USES not in text:
        return text
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        if DEPLOY_USES not in lines[i]:
            i += 1
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines) or DEPLOY_NAME not in lines[j]:
            raise SystemExit("peaceiris step missing GitHub Pages Deploy name")
        lines = insert_if_after(lines, j)
        i = j + 2
    return "".join(lines)


def ensure_keep_files(text: str) -> str:
    if "keep_files:" in text:
        return text
    if FORCE_ORPHAN not in text:
        raise SystemExit("expected force_orphan in generated Pages deploy step")
    return text.replace(FORCE_ORPHAN, FORCE_ORPHAN + "\n          " + KEEP_FILES_LINE)


def ensure_named_step_if(text: str, step_name: str) -> str:
    lines = text.splitlines(keepends=True)
    needle = f"name: {step_name}"
    for i, line in enumerate(lines):
        stripped = line.strip().lstrip("-").strip()
        if stripped != needle:
            continue
        return "".join(insert_if_after(lines, i))
    return text


def ensure_job_if_after_runs_on(text: str) -> str:
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip().startswith("runs-on:"):
            return "".join(insert_if_after(lines, i))
    raise SystemExit("runs-on not found")


def patch_site(text: str) -> str:
    return ensure_keep_files(ensure_pages_deploy_if(text))


def patch_setup(text: str) -> str:
    text = ensure_named_step_if(text, UPDATE_TEMPLATE_STEP)
    text = ensure_pages_deploy_if(text)
    return ensure_keep_files(text)


def patch_update_template(text: str) -> str:
    return ensure_job_if_after_runs_on(text)


PATCHERS = {
    "site.yml": patch_site,
    "setup.yml": patch_setup,
    "update-template.yml": patch_update_template,
}


def would_run_pages_deploy(github_ref: str, default_branch: str) -> bool:
    """Semantics of DEFAULT_BRANCH_IF (GitHub expression)."""
    return github_ref == f"refs/heads/{default_branch}"


def apply(check_only: bool) -> int:
    dirty = False
    for name, patcher in PATCHERS.items():
        path = WORKFLOWS / name
        original = path.read_text()
        patched = patcher(original)
        if patched != original:
            dirty = True
            if check_only:
                print(f"missing guards in {name}", file=sys.stderr)
            else:
                path.write_text(patched)
                print(f"patched {name}")
        else:
            print(f"ok {name}")
    return 1 if (check_only and dirty) else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    return apply(check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
