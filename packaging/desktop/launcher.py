"""Frozen desktop entry point for the Hermes dashboard.

Modes (the frozen binary dispatches on argv so it can re-invoke itself — which
is how dashboard "action" buttons and the in-app chat PTY run hermes
subcommands without a separate Python interpreter):

    hermes-desktop                 -> start the dashboard
    hermes-desktop --selftest      -> bundle smoke test (providers + skills)
    hermes-desktop <hermes args>   -> delegate to the full hermes CLI
                                      (e.g. ``chat``, ``gateway restart``)
"""

import os
import sys
from pathlib import Path


def _bundle_dir() -> Path:
    # PyInstaller unpacks bundled data under sys._MEIPASS at runtime.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent


def _seed_skills(bundle: Path) -> None:
    """Seed bundled skills into HERMES_HOME on first run (idempotent).

    The dashboard's Skills page reads ~/.hermes/skills, which is populated from
    the bundled skills/ tree by tools.skills_sync. A normal install does this at
    setup time; the frozen app has no setup step, so do it here. Runs in-process
    (sync_skills does not spawn), and never blocks dashboard startup.
    """
    skills_src = bundle / "skills"
    if not skills_src.is_dir():
        return
    os.environ.setdefault("HERMES_BUNDLED_SKILLS", str(skills_src))
    try:
        from tools.skills_sync import sync_skills

        sync_skills(quiet=True)
    except Exception:
        pass


def _selftest(bundle: Path) -> int:
    """Smoke-test the frozen bundle: provider profiles + skills both resolve."""
    from providers import list_providers

    profiles = list_providers()
    print(f"providers discovered: {len(profiles)}")

    _seed_skills(bundle)
    from tools.skills_tool import _find_all_skills

    skills = _find_all_skills()
    print(f"skills discovered: {len(skills)}")
    return 0 if profiles else 1


def main() -> None:
    bundle = _bundle_dir()
    web_dist = bundle / "web_dist"
    # web_server reads WEB_DIST at import time, so set this before importing it.
    if web_dist.is_dir():
        os.environ.setdefault("HERMES_WEB_DIST", str(web_dist))

    argv = sys.argv[1:]

    if argv == ["--selftest"]:
        raise SystemExit(_selftest(bundle))

    # Any other args -> act as the hermes CLI (frozen self-reinvocation target).
    if argv:
        _seed_skills(bundle)
        from hermes_cli.main import main as hermes_main

        hermes_main()
        return

    # No args -> start the dashboard.
    _seed_skills(bundle)
    port = int(os.environ.get("HERMES_DESKTOP_PORT", "9119"))

    from hermes_cli.web_server import start_server

    # embedded_chat=True exposes the in-app Chat tab; its PTY runs the Python
    # chat (see web_server._resolve_chat_argv), not the Node TUI.
    start_server(
        host="127.0.0.1",
        port=port,
        open_browser=False,
        embedded_chat=True,
    )


if __name__ == "__main__":
    main()
