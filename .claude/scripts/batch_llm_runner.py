#!/usr/bin/env python3
"""Shared provider selection and CLI command building for batch runners."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


DEFAULT_PROVIDER = "claude"
VALID_PROVIDERS = ("claude", "codex")
CODEX_COMMIT_CAPABLE_SANDBOX_MODE = "danger-full-access"
CODEX_SANDBOX_NETWORK_DISABLED_ENV = "CODEX_SANDBOX_NETWORK_DISABLED"
CODEX_CHILD_NETWORK_ALLOWED_ENV = "CODEX_CHILD_NETWORK_ALLOWED"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
PROVIDER_INSTALL_NAMES = {
    "claude": "Claude Code",
    "codex": "Codex CLI",
}
PROVIDER_PROBE_COMMANDS = {
    "claude": ["claude", "--version"],
    # `codex --version` can hang in some environments even when `codex exec`
    # works, so probe the exec subcommand through its lightweight help path.
    "codex": ["codex", "exec", "--help"],
}
PROVIDER_PROBE_RUN_KWARGS = {
    # Claude Code can stall when stdout/stderr are captured through subprocess
    # pipes (same issue as Codex). DEVNULL keeps the probe lightweight.
    "claude": {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    },
    # Codex can stall when stdout/stderr are captured through subprocess pipes.
    # DEVNULL keeps the probe lightweight and avoids the hang.
    "codex": {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    },
}

CODEX_PROCEDURAL_OVERRIDES = ['model_reasoning_effort="low"']
CODEX_ANALYTICAL_OVERRIDES = ['model_reasoning_effort="medium"']
CODEX_HIGH_LEVEL_OVERRIDES = ['model_reasoning_effort="xhigh"']
CODEX_PROCEDURAL_MODEL_ENV = "SCRAPECRAB_CODEX_PROCEDURAL_MODEL"
CODEX_ANALYTICAL_MODEL_ENV = "SCRAPECRAB_CODEX_ANALYTICAL_MODEL"
CODEX_HIGH_LEVEL_MODEL_ENV = "SCRAPECRAB_CODEX_HIGH_LEVEL_MODEL"
DEFAULT_CODEX_PROCEDURAL_MODEL = "gpt-5.4-mini"
_LIGHTWEIGHT_CODEX_MODEL_MAP = {
    "gpt-5.4": "gpt-5.4-mini",
}
DEFAULT_CODEX_NOTIFY_LOG = "/tmp/codex-notify.log"
DEFAULT_CODEX_NOTIFY_STATE_DIR = "/tmp/codex-telegram-notify"


@dataclass(frozen=True)
class RunnerProfile:
    model: str | None
    config_overrides: list[str] | None


def codex_child_network_blocked(
    provider: str,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Whether the current parent session forbids child Codex network startup."""
    if provider != "codex":
        return False
    source = env or os.environ
    return source.get(CODEX_SANDBOX_NETWORK_DISABLED_ENV, "").strip().lower() in _TRUTHY_ENV_VALUES


def codex_child_network_allowed(
    provider: str,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Whether an explicit audited override allows child Codex network startup."""
    if provider != "codex":
        return False
    source = env or os.environ
    return source.get(CODEX_CHILD_NETWORK_ALLOWED_ENV, "").strip().lower() in _TRUTHY_ENV_VALUES


def codex_child_network_failure_reason(task_label: str) -> str:
    """Standardize the DNS/startup failure string across child Codex call sites."""
    return f"network lookup failed while starting the {task_label}"


def build_runner_env(
    provider: str,
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a subprocess environment for child runner sessions."""
    child_env = dict(env or os.environ)
    if provider == "claude":
        # Claude Code refuses to launch inside another Claude Code session when
        # CLAUDECODE is set.  Child orchestration sessions are intentionally
        # fresh, so drop the parent session marker before spawning them.
        child_env.pop("CLAUDECODE", None)
    if provider == "codex":
        if codex_child_network_allowed(provider, child_env):
            child_env.pop(CODEX_SANDBOX_NETWORK_DISABLED_ENV, None)
        # Child Codex runs should not emit Telegram notifications that belong
        # to the parent interactive session.
        child_env["CODEX_NOTIFY_DISABLE"] = "1"
        child_env.setdefault("CODEX_NOTIFY_LOG", DEFAULT_CODEX_NOTIFY_LOG)
        child_env.setdefault("CODEX_NOTIFY_STATE_DIR", DEFAULT_CODEX_NOTIFY_STATE_DIR)
    return child_env


def choose_provider(
    requested_provider: str | None,
    interactive: bool,
    input_func: Callable[[str], str] = input,
    print_func: Callable[[str], None] = print,
) -> str:
    """Resolve the runner provider, prompting once during interactive preflight."""
    if requested_provider:
        return requested_provider
    if not interactive:
        return DEFAULT_PROVIDER

    prompt = f"Provider [{DEFAULT_PROVIDER}/codex] (default: {DEFAULT_PROVIDER}): "
    while True:
        answer = input_func(prompt).strip().lower()
        if not answer:
            return DEFAULT_PROVIDER
        if answer in VALID_PROVIDERS:
            return answer
        print_func("Invalid provider. Choose 'claude' or 'codex'.")


def resolve_model(
    provider: str,
    requested_model: str | None,
    claude_default: str,
) -> str | None:
    """Resolve the model override for the selected provider."""
    if provider == "claude":
        return requested_model or claude_default
    return requested_model or None


def format_model_display(
    provider: str,
    model: str | None,
    claude_default: str,
) -> str:
    """Format the effective runtime model for preflight display."""
    if model:
        return model
    if provider == "claude":
        return claude_default
    return "configured default"


def format_budget_display(provider: str, max_budget: float) -> str:
    """Format provider-specific budget messaging for preflight display."""
    if provider == "claude":
        return f"${max_budget:.2f}/session"
    return f"ignored for codex (flag value: ${max_budget:.2f})"


def infer_lightweight_codex_model(model: str | None) -> str | None:
    """Map heavyweight Codex models to a lighter sibling when one is known."""
    if not model:
        return None
    normalized = model.strip().lower()
    if normalized.endswith("-mini"):
        return model
    return _LIGHTWEIGHT_CODEX_MODEL_MAP.get(normalized, model)


def select_runner_profile(
    provider: str,
    requested_model: str | None,
    session_class: str = "analytical",
) -> RunnerProfile:
    """Resolve model + reasoning profile for one runner session.

    `session_class` is one of:
    - `procedural`: mechanical or tightly bounded task handling
    - `analytical`: normal balanced reasoning
    - `high_level`: strategy, writing, review, or synthesis-heavy work
    """
    if provider != "codex":
        return RunnerProfile(model=requested_model, config_overrides=None)

    normalized = (session_class or "analytical").strip().lower()
    if normalized == "procedural":
        model = (
            os.getenv(CODEX_PROCEDURAL_MODEL_ENV)
            or infer_lightweight_codex_model(requested_model)
            or DEFAULT_CODEX_PROCEDURAL_MODEL
        )
        return RunnerProfile(model=model, config_overrides=list(CODEX_PROCEDURAL_OVERRIDES))
    if normalized == "high_level":
        model = os.getenv(CODEX_HIGH_LEVEL_MODEL_ENV) or requested_model
        return RunnerProfile(model=model, config_overrides=list(CODEX_HIGH_LEVEL_OVERRIDES))

    model = os.getenv(CODEX_ANALYTICAL_MODEL_ENV) or requested_model
    return RunnerProfile(model=model, config_overrides=list(CODEX_ANALYTICAL_OVERRIDES))


def verify_provider_cli(provider: str) -> None:
    """Fail fast if the selected provider CLI is unavailable."""
    install_name = PROVIDER_INSTALL_NAMES.get(provider, provider)
    probe_cmd = PROVIDER_PROBE_COMMANDS.get(provider, [provider, "--version"])
    run_kwargs = PROVIDER_PROBE_RUN_KWARGS.get(provider, {
        "capture_output": True,
        "text": True,
    })
    probe_label = " ".join(probe_cmd)
    try:
        result = subprocess.run(
            probe_cmd,
            timeout=10,
            check=False,
            **run_kwargs,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Error: '{provider}' not found on PATH. Install {install_name} first."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Error: '{probe_label}' timed out during preflight."
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr.strip() if isinstance(result.stderr, str) else ""
        stdout = result.stdout.strip() if isinstance(result.stdout, str) else ""
        detail = stderr or stdout or f"exit {result.returncode}"
        raise RuntimeError(
            f"Error: '{probe_label}' failed during preflight: {detail}"
        )


def build_runner_command(
    provider: str,
    root: Path,
    prompt: str,
    model: str | None,
    max_budget: float | None,
    config_overrides: list[str] | None = None,
    sandbox_mode: str | None = None,
) -> list[str]:
    """Build the non-interactive CLI invocation for the selected provider."""
    if provider == "claude":
        cmd = [
            "claude",
            "--dangerously-skip-permissions",
            "--no-session-persistence",
        ]
        if model:
            cmd.extend(["--model", model])
        if max_budget is not None:
            cmd.append(f"--max-budget-usd={max_budget}")
        cmd.extend(["-p", prompt])
        return cmd

    # Keep Codex child sessions in inline plain-text mode so terminal-forwarding
    # notifiers can follow incremental output instead of alt-screen redraws.
    cmd = [
        "codex",
        "--no-alt-screen",
    ]
    if sandbox_mode:
        cmd.extend([
            "-a",
            "never",
            "exec",
            "--cd",
            str(root),
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            sandbox_mode,
        ])
    else:
        cmd.extend([
            "exec",
            "--full-auto",
            "--cd",
            str(root),
            "--skip-git-repo-check",
            "--ephemeral",
        ])
    for override in config_overrides or []:
        cmd.extend(["-c", override])
    if model:
        cmd.extend(["-m", model])
    cmd.append(prompt)
    return cmd
