#!/usr/bin/env python3
"""CLI entry for LangGraph-uitest.

Phase 0: init / run
Phase 1: run YAML cases for a requirement
Phase 4+: compile
Phase 5+: discover
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def cmd_init(args: argparse.Namespace) -> int:
    from framework.paths import init_requirement

    path = init_requirement(args.req)
    print(f"Initialized requirement workspace: {path}")
    for child in sorted(path.iterdir()):
        if child.is_dir():
            print(f"  - {child.name}/")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run pytest for a requirement (or smoke if --smoke)."""
    if args.smoke:
        results_dir = ROOT / "allure-results"
        results_dir.mkdir(parents=True, exist_ok=True)
        pytest_args = [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_phase0_smoke.py",
            "tests/test_schema.py",
            f"--alluredir={results_dir}",
        ]
    else:
        from framework.paths import init_requirement, req_dir
        from framework.schema.loader import list_case_files

        init_requirement(args.req)
        results_dir = req_dir(args.req) / "allure-results"
        import shutil

        if results_dir.exists():
            shutil.rmtree(results_dir)
        results_dir.mkdir(parents=True, exist_ok=True)
        yaml_cases = list_case_files(req_dir(args.req) / "yaml")
        if not yaml_cases:
            print(f"No YAML cases in runs/{args.req}/yaml — nothing to run.")
            return 1

        pytest_args = [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_yaml_runner.py",
            f"--req={args.req}",
            f"--alluredir={results_dir}",
            "-m",
            "req",
        ]
        if args.pytest_args:
            pytest_args.extend(args.pytest_args)

    print("Running:", " ".join(pytest_args))
    completed = subprocess.run(pytest_args, cwd=ROOT)

    from framework.runner.allure_report import generate_allure_report

    report = generate_allure_report(results_dir)
    print(f"\nAllure results: {results_dir}")
    if report and report.suffix.lower() == ".html":
        print(f"Allure report (double-click): {report}")
    elif report:
        print(f"Allure report: {report / 'index.html'}")
        print("This copy needs a local server: python -m http.server 18787 --directory {report}")
    else:
        print("Allure HTML not generated or still empty after sanitize.")
        print(f"Raw results: {results_dir}")

    if not args.smoke and not getattr(args, "no_excel_backfill", False):
        from framework.runner.excel_backfill import backfill_requirement_excel

        excel_summary = backfill_requirement_excel(
            args.req,
            source=getattr(args, "excel", None),
            allure_dir=results_dir,
        )
        if excel_summary.get("skipped"):
            print(f"Excel backfill skipped: {excel_summary.get('reason')}")
        elif excel_summary.get("ok"):
            stats = excel_summary.get("stats") or {}
            print(
                "Excel backfill: "
                f"通过={stats.get('通过', 0)} 失败={stats.get('失败', 0)} "
                f"Block={stats.get('Block', 0)}"
            )
            print(f"Excel report: {excel_summary.get('excel')}")
        else:
            print(f"Excel backfill failed: {excel_summary}")

    if not args.smoke:
        from framework.notify import notify_report, should_notify_after_run

        if should_notify_after_run():
            for item in notify_report(args.req, exit_code=completed.returncode):
                flag = "ok" if item.ok else "FAIL"
                print(f"Notify [{flag}] {item.channel}: {item.message}")

    return completed.returncode


def cmd_notify(args: argparse.Namespace) -> int:
    """Send latest Excel/HTML report for a requirement (no re-run)."""
    from framework.notify import notify_report

    results = notify_report(
        args.req,
        exit_code=getattr(args, "exit_code", None),
        channels=getattr(args, "channel", None),
        force=True,
    )
    failed = 0
    for item in results:
        flag = "ok" if item.ok else "FAIL"
        print(f"[{flag}] {item.channel}: {item.message}")
        if item.details.get("uploaded"):
            for u in item.details["uploaded"]:
                print(f"      uploaded: {u.get('name')}")
        if item.details.get("errors"):
            for err in item.details["errors"]:
                print(f"      upload error: {err.get('file')}: {err.get('error')}")
        if not item.ok:
            failed += 1
    return 1 if failed else 0


def cmd_excel_backfill(args: argparse.Namespace) -> int:
    """Re-write Excel from existing Allure results without re-running cases."""
    from framework.runner.excel_backfill import backfill_requirement_excel

    summary = backfill_requirement_excel(args.req, source=getattr(args, "excel", None))
    if summary.get("skipped"):
        print(f"Excel backfill skipped: {summary.get('reason')}")
        return 1
    if not summary.get("ok"):
        print(f"Excel backfill failed: {summary}")
        return 1
    stats = summary.get("stats") or {}
    print(
        "Excel backfill: "
        f"通过={stats.get('通过', 0)} 失败={stats.get('失败', 0)} "
        f"Block={stats.get('Block', 0)}"
    )
    print(f"Excel report: {summary.get('excel')}")
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    """NL → YAML via LLM (required). Stub only when --allow-stub (tests/debug)."""
    from framework.agents.compile.service import compile_requirement
    from framework.llm.profiles import compile_backend, resolve_profile

    profile = resolve_profile(args.llm)
    allow_stub = bool(getattr(args, "allow_stub", False))
    force = "stub" if allow_stub else "llm"
    mode = compile_backend()
    print(f"compile backend config: {mode}  force={force}")
    print(f"LLM profile: {profile.name}  model={profile.model}")
    print(f"  key env {profile.api_key_env}: {'set' if profile.has_key else 'empty'}")
    if force == "llm" and not profile.has_key:
        print(f"ERROR: NL→YAML must use LLM, but {profile.api_key_env} is empty.")
        return 1
    try:
        results = compile_requirement(
            args.req,
            llm_profile=args.llm,
            force_backend=force,
            case_ids=getattr(args, "case", None),
        )
    except FileNotFoundError as exc:
        print(exc)
        return 1
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1
    failed = 0
    review = 0
    for item in results:
        flag = "REVIEW" if item["needs_review"] else "ok"
        if not item["ok"]:
            flag = "FAIL"
            failed += 1
        elif item["needs_review"]:
            review += 1
        print(f"[{flag}] backend={item.get('backend')} {item['nl']}")
        if item.get("out"):
            print(f"      → {item['out']}")
        for err in item.get("errors") or []:
            print(f"      error: {err}")
    print(f"Summary: ok={len(results) - failed} fail={failed} review={review}")
    print(f"YAML written under runs/{args.req}/yaml/*.yaml (overwrite).")
    return 1 if failed else 0


def cmd_discover(args: argparse.Namespace) -> int:
    """Find YAML element names on the live/fixture page and write POM locators."""
    from framework.agents.discover.service import discover_requirement

    use_llm = not bool(getattr(args, "no_llm", False))
    try:
        report = discover_requirement(
            args.req,
            force=bool(args.force),
            llm_profile=getattr(args, "llm", None),
            use_llm=use_llm,
        )
    except FileNotFoundError as exc:
        print(exc)
        return 1
    bound = report.get("bound") or {}
    kept = report.get("kept") or []
    unbound = report.get("unbound") or []
    print(
        f"discover {args.req}: backend={report.get('backend')} "
        f"bound={len(bound)} kept={len(kept)} unbound={len(unbound)}"
    )
    for name in bound:
        print(f"  [ok] {name}")
    for name in kept:
        print(f"  [kept] {name}")
    for name in unbound:
        print(f"  [blocked] {name}")
    if report.get("llm_error"):
        print(f"LLM error: {report['llm_error']}")
    print(f"POM: {report.get('pom')}")
    print(f"bindings: runs/{args.req}/bindings/discover.yaml")
    if unbound:
        print("Unbound elements were not written. Fix the page/YAML or bind manually, then run.")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="LangGraph UI test framework CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # keep help text honest about post-run artifacts
    p_init = sub.add_parser("init", help="Create runs/<req>/ workspace")
    p_init.add_argument("--req", required=True, help="Requirement id")
    p_init.set_defaults(func=cmd_init)

    p_run = sub.add_parser(
        "run",
        help="Execute YAML cases, Allure report, and Excel result backfill",
    )
    p_run.add_argument("--req", required=True, help="Requirement id")
    p_run.add_argument(
        "--smoke",
        action="store_true",
        help="Run Phase 0/1 unit smoke (no browser requirement cases)",
    )
    p_run.add_argument(
        "--excel",
        default=None,
        help="Source Excel path for result backfill (default: runs/<req>/excel/*.xlsx)",
    )
    p_run.add_argument(
        "--no-excel-backfill",
        action="store_true",
        help="Skip writing pass/fail/Block + screenshots back into Excel",
    )
    p_run.add_argument(
        "pytest_args",
        nargs="*",
        help="Extra args passed to pytest",
    )
    p_run.set_defaults(func=cmd_run)

    p_notify = sub.add_parser(
        "notify",
        help="Send latest Excel/HTML test report (Feishu etc., no re-run)",
    )
    p_notify.add_argument("--req", required=True, help="Requirement id")
    p_notify.add_argument(
        "--channel",
        action="append",
        default=None,
        help="Only these channels (repeatable). Default: enabled channels in config/notify.yaml",
    )
    p_notify.add_argument(
        "--exit-code",
        type=int,
        default=None,
        help="Optional exit code to show in the summary text",
    )
    p_notify.set_defaults(func=cmd_notify)

    p_compile = sub.add_parser(
        "compile",
        help="NL → YAML via LLM (required for all requirements)",
    )
    p_compile.add_argument("--req", required=True)
    p_compile.add_argument(
        "--llm",
        default=None,
        help="LLM profile in config/llm.yaml (default: config active profile)",
    )
    p_compile.add_argument(
        "--allow-stub",
        action="store_true",
        help="Allow offline stub (tests/debug only; not for real Excel/NL cases)",
    )
    p_compile.add_argument(
        "--case",
        action="append",
        default=None,
        help="Only compile these case_id values (repeatable). Default: all NL files",
    )
    p_compile.set_defaults(func=cmd_compile)

    p_discover = sub.add_parser("discover", help="Find elements → POM (Phase 5)")
    p_discover.add_argument("--req", required=True)
    p_discover.add_argument(
        "--force",
        action="store_true",
        help="Re-bind every element even if POM already has it",
    )
    p_discover.add_argument(
        "--llm",
        default=None,
        help="LLM profile for unbound elements (default: config active profile)",
    )
    p_discover.add_argument(
        "--no-llm",
        action="store_true",
        help="Heuristics only; do not call remote LLM",
    )
    p_discover.set_defaults(func=cmd_discover)

    p_excel = sub.add_parser(
        "excel-backfill",
        help="Backfill Excel with latest Allure results (no re-run)",
    )
    p_excel.add_argument("--req", required=True, help="Requirement id")
    p_excel.add_argument(
        "--excel",
        default=None,
        help="Source Excel path (default: runs/<req>/excel/*.xlsx)",
    )
    p_excel.set_defaults(func=cmd_excel_backfill)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
