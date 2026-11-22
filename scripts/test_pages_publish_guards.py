#!/usr/bin/env python3
"""Offline tests for default-branch Pages publish guards. No network, no deploys."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import assert_pages_publish_guards as g

ROOT = Path(__file__).resolve().parents[1]


def _vanilla(text: str) -> str:
    lines = []
    for line in text.splitlines(keepends=True):
        if g.DEFAULT_BRANCH_IF in line and line.strip().startswith("if:"):
            continue
        if line.strip() == g.KEEP_FILES_LINE:
            continue
        lines.append(line)
    return "".join(lines)


def test_feature_branch_cannot_publish_default_can() -> None:
    assert g.would_run_pages_deploy("refs/heads/master", "master") is True
    assert g.would_run_pages_deploy("refs/heads/imcom/pages-default-branch-aa9a", "master") is False
    assert g.would_run_pages_deploy("refs/heads/main", "master") is False


def test_custom_workflow_survives_update_template() -> None:
    name = "assert-pages-publish-guards.yml"
    assert name not in g.OVERWRITTEN_BY_UPDATE_TEMPLATE
    assert (ROOT / ".github/workflows" / name).is_file()
    assert (ROOT / "scripts/assert_pages_publish_guards.py").is_file()


def test_secret_mapping_and_theme_untouched() -> None:
    cfg = (ROOT / ".upptimerc.yml").read_text()
    assert "X-Nexusguard-Uptime-Token: $UPTIME_WAF_TOKEN" in cfg
    assert "nexusguard-theme.css" in cfg
    assert cfg.count("https://www.nexusguard.com") == 2
    for name in ("uptime.yml", "response-time.yml", "setup.yml"):
        text = (ROOT / ".github/workflows" / name).read_text()
        assert '"UPTIME_WAF_TOKEN":${{ toJson(secrets.UPTIME_WAF_TOKEN) }}' in text


def test_apply_on_vanilla_generated_workflows() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        src = ROOT / ".github" / "workflows"
        for name in g.PATCHERS:
            (wf / name).write_text(_vanilla((src / name).read_text()))
        # Point the module at the temp tree
        old_root, old_wf = g.ROOT, g.WORKFLOWS
        try:
            g.ROOT = tmp_path
            g.WORKFLOWS = wf
            for name in g.PATCHERS:
                vanilla = (wf / name).read_text()
                assert g.DEFAULT_BRANCH_IF not in vanilla or name == "assert-pages-publish-guards.yml"
                assert "keep_files:" not in vanilla
            rc = g.apply(check_only=False)
            assert rc == 0
            site = (wf / "site.yml").read_text()
            setup = (wf / "setup.yml").read_text()
            upd = (wf / "update-template.yml").read_text()
            assert site.count("if: " + g.DEFAULT_BRANCH_IF) == 1
            assert "keep_files: true" in site
            assert setup.count("if: " + g.DEFAULT_BRANCH_IF) == 2  # update-template + deploy
            assert "keep_files: true" in setup
            assert '"UPTIME_WAF_TOKEN":${{ toJson(secrets.UPTIME_WAF_TOKEN) }}' in setup
            assert "if: " + g.DEFAULT_BRANCH_IF in upd
            rc2 = g.apply(check_only=True)
            assert rc2 == 0, "apply must be idempotent"
        finally:
            g.ROOT = old_root
            g.WORKFLOWS = old_wf


def test_live_files_have_guards() -> None:
    rc = g.apply(check_only=True)
    assert rc == 0
    site = (ROOT / ".github/workflows/site.yml").read_text()
    setup = (ROOT / ".github/workflows/setup.yml").read_text()
    # Generate site still runs on feature branches (validation, no publish)
    assert "command: \"site\"" in site
    assert "command: \"site\"" in setup
    assert "peaceiris/actions-gh-pages@v4" in site
    assert "peaceiris/actions-gh-pages@v4" in setup


def main() -> None:
    test_feature_branch_cannot_publish_default_can()
    test_custom_workflow_survives_update_template()
    test_secret_mapping_and_theme_untouched()
    test_apply_on_vanilla_generated_workflows()
    test_live_files_have_guards()
    print("ok all pages-publish-guard tests")


if __name__ == "__main__":
    main()
