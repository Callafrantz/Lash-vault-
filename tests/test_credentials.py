"""Credential discovery — the check that runs before a run spends anything.

The failure this exists to stop: `export ANTHROPIC_API_KEY=...` does not outlive the
Terminal window it was typed in. A new tab, or a rotated key, leaves the shell with no
credential — and because the SDK resolves lazily (a keyless client constructs fine and
fails only at request time), the run reported zero claims, zero tokens and $0.00, which
is indistinguishable from a transcript that contained nothing.
"""

from __future__ import annotations

import pytest

from lashos_ke.cli.main import _credential_error
from lashos_ke.core.llm import (
    CredentialStatus,
    FatalLLMError,
    _is_auth_failure,
    credential_status,
    has_stored_profile,
)

_ENV_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "LKE_MODEL_API_KEY")


@pytest.fixture
def clean_env(monkeypatch, tmp_path):  # type: ignore[no-untyped-def]
    """No env credential and no profile on disk."""
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path / "no-such-config"))
    return tmp_path


def _write_profile(root, name: str = "default"):  # type: ignore[no-untyped-def]
    """A profile the SDK can load: both halves must exist."""
    config = root / "config"
    (config / "configs").mkdir(parents=True, exist_ok=True)
    (config / "credentials").mkdir(parents=True, exist_ok=True)
    (config / "configs" / f"{name}.json").write_text("{}")
    (config / "credentials" / f"{name}.json").write_text("{}")
    return config


class TestCredentialStatus:
    def test_no_key_and_no_profile_is_missing(self, clean_env) -> None:  # type: ignore[no-untyped-def]
        status, _ = credential_status()
        assert status is CredentialStatus.MISSING

    def test_a_real_key_is_ok(self, clean_env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-realkeymaterial")
        status, source = credential_status()
        assert status is CredentialStatus.OK
        assert source == "ANTHROPIC_API_KEY"

    def test_blank_key_counts_as_missing(self, clean_env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """An exported-but-empty var occupies the slot without authenticating —
        `export ANTHROPIC_API_KEY=` is a real way to end up here."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        assert credential_status()[0] is CredentialStatus.MISSING

    def test_whitespace_only_key_counts_as_missing(self, clean_env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
        assert credential_status()[0] is CredentialStatus.MISSING

    def test_placeholder_is_distinguished_from_missing(self, clean_env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-...")
        status, source = credential_status()
        assert status is CredentialStatus.PLACEHOLDER
        assert source == "ANTHROPIC_API_KEY"

    def test_falls_through_to_the_next_env_var(self, clean_env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("LKE_MODEL_API_KEY", "sk-ant-api03-realkeymaterial")
        status, source = credential_status()
        assert status is CredentialStatus.OK
        assert source == "LKE_MODEL_API_KEY"

    def test_a_stored_profile_authenticates_without_an_env_var(self, clean_env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """`ant auth login` is a legitimate setup — the check must not block it."""
        config = _write_profile(clean_env)
        monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(config))

        assert has_stored_profile()
        status, source = credential_status()
        assert status is CredentialStatus.OK
        assert source == "stored profile"

    def test_empty_profile_directory_is_not_a_credential(self, clean_env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        config = clean_env / "config"
        (config / "credentials").mkdir(parents=True)
        monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(config))

        assert not has_stored_profile()
        assert credential_status()[0] is CredentialStatus.MISSING


class TestCredentialMessage:
    def test_missing_explains_that_export_is_per_shell(self) -> None:
        """Restating the export command alone would not have prevented this — the
        operator ran it, in a different window."""
        msg = _credential_error(CredentialStatus.MISSING, "")
        assert "only for this Terminal window" in msg
        assert ".zshrc" in msg

    def test_missing_mentions_key_rotation(self) -> None:
        assert "rotating a key" in _credential_error(CredentialStatus.MISSING, "")

    def test_the_verification_command_does_not_print_the_key(self) -> None:
        msg = _credential_error(CredentialStatus.MISSING, "")
        assert "echo set" in msg
        assert "echo $ANTHROPIC_API_KEY" not in msg

    def test_placeholder_names_the_offending_variable(self) -> None:
        msg = _credential_error(CredentialStatus.PLACEHOLDER, "ANTHROPIC_API_KEY")
        assert "ANTHROPIC_API_KEY" in msg
        assert "placeholder" in msg
        assert "console.anthropic.com" in msg

    def test_the_two_messages_are_different(self) -> None:
        assert _credential_error(CredentialStatus.MISSING, "") != _credential_error(
            CredentialStatus.PLACEHOLDER, "ANTHROPIC_API_KEY"
        )


class TestRunAbortsBeforeDoingWork:
    def _pilot(self, tmp_path):  # type: ignore[no-untyped-def]
        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "episode.md").write_text(
            "**Speaker 1:** if you're above sixty percent humidity your glue is curing "
            "before it even touches the lash and that is why your bonds are brittle.\n"
        )
        return raw, tmp_path / "out"

    def test_exits_two_without_parsing_anything(self, clean_env, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """The check must precede the work. Parsing first would burn time and, on a
        ten-transcript run, produce a half-built audit sheet for a run that never
        authenticated."""
        import lashos_ke.cli.main as cli

        raw, out = self._pilot(tmp_path)
        monkeypatch.setattr(
            cli, "parse", lambda p: pytest.fail("parsed before the credential check")
        )

        assert cli.main(["pilot", "run", "--input", str(raw), "--out", str(out)]) == 2
        assert not (out / "claims.jsonl").exists()
        assert not (out / "audit.md").exists()

    def test_dry_run_needs_no_credential(self, clean_env, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Inspecting segmentation is free and must stay free — it is the step that
        catches recall problems before any money is spent."""
        import lashos_ke.cli.main as cli

        raw, out = self._pilot(tmp_path)
        rc = cli.main(
            ["pilot", "run", "--dry-run", "--input", str(raw), "--out", str(out)]
        )
        assert rc == 0

    def test_a_valid_key_gets_past_the_check(self, clean_env, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Guard against the check rejecting a legitimate run: with a key present it
        must reach transcript parsing."""
        import lashos_ke.cli.main as cli

        raw, out = self._pilot(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-realkeymaterial")
        reached = []
        monkeypatch.setattr(cli, "parse", lambda p: reached.append(p) or [])

        cli.main(["pilot", "run", "--input", str(raw), "--out", str(out)])
        assert reached, "credential check blocked a run that had a key"


class TestCredentialSourceIsReported:
    def test_run_states_which_credential_it_resolved(self, clean_env, tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
        """A shell test that disagrees with the run sends you looking in the wrong
        place. The run should say what it actually used."""
        import lashos_ke.cli.main as cli

        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "e.md").write_text("**Speaker 1:** something substantive about glue.\n")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-realkeymaterial")
        monkeypatch.setattr(cli, "parse", lambda p: [])

        cli.main(["pilot", "run", "--input", str(raw), "--out", str(tmp_path / "o")])
        assert "Using API key from ANTHROPIC_API_KEY." in capsys.readouterr().out

    def test_a_profile_is_named_as_such(self, clean_env, tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
        import lashos_ke.cli.main as cli
        import lashos_ke.core.llm as llm
        from lashos_ke.core.llm import LLMResult

        config = _write_profile(clean_env)
        monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(config))

        # The profile files here are placeholders, so a real SDK client cannot load
        # them. This test is about what the CLI reports, not about SDK construction.
        class _Stub:
            def __init__(self, **kw: object) -> None:
                self.total = LLMResult(data={})

        monkeypatch.setattr(llm, "StructuredClient", _Stub)

        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "e.md").write_text("**Speaker 1:** something substantive about glue.\n")
        monkeypatch.setattr(cli, "parse", lambda p: [])

        cli.main(["pilot", "run", "--input", str(raw), "--out", str(tmp_path / "o")])
        assert "stored ant auth login profile" in capsys.readouterr().out


class TestProgressPrinter:
    """Formatting of the per-chunk line. The point of the line is that it appears at
    all — but it also has to be readable, and correct when piped to a log."""

    class _Client:
        def __init__(self) -> None:
            from lashos_ke.core.llm import LLMResult

            self.total = LLMResult(data={}, model="claude-opus-5")

        def spend(self, input_tokens: int) -> None:
            self.total.input_tokens += input_tokens

    def _printer(self):  # type: ignore[no-untyped-def]
        import io

        from lashos_ke.cli.main import _ProgressPrinter

        out = io.StringIO()  # not a tty
        return _ProgressPrinter(self._Client(), stream=out), out

    def _event(self, **kw):  # type: ignore[no-untyped-def]
        from lashos_ke.extract.claims import ChunkProgress

        base = dict(index=1, total=4, sequence=0, words=310, phase="done")
        base.update(kw)
        return ChunkProgress(**base)  # type: ignore[arg-type]

    def test_non_tty_output_has_no_carriage_returns(self) -> None:
        """Piped to a file, `\\r` is literal noise that mangles the log."""
        printer, out = self._printer()
        printer(self._event(phase="start"))
        printer(self._event(elapsed_s=38.0, claims_kept=6))
        assert "\r" not in out.getvalue()

    def test_non_tty_prints_one_line_per_chunk(self) -> None:
        printer, out = self._printer()
        printer(self._event(phase="start"))
        printer(self._event(elapsed_s=38.0, claims_kept=6))
        assert len(out.getvalue().strip().splitlines()) == 1

    def test_line_reports_claims_progress_and_cost(self) -> None:
        printer, out = self._printer()
        printer(self._event(phase="start"))
        printer(self._event(elapsed_s=38.0, claims_kept=6))
        line = out.getvalue()
        assert "6 claims" in line
        assert "38s" in line
        assert "1/4" in line

    def test_estimates_remaining_time_while_chunks_are_left(self) -> None:
        printer, out = self._printer()
        printer(self._event(phase="start"))
        printer(self._event(index=1, total=4, elapsed_s=60.0))
        assert "left" in out.getvalue()

    def test_no_estimate_on_the_final_chunk(self) -> None:
        """'0s left' on the last chunk is noise."""
        printer, out = self._printer()
        printer(self._event(phase="start"))
        printer(self._event(index=4, total=4, elapsed_s=60.0))
        assert "left" not in out.getvalue()

    def test_durations_are_human_readable(self) -> None:
        from lashos_ke.cli.main import _fmt_duration

        assert _fmt_duration(3.2) == "3.2s"
        assert _fmt_duration(38.0) == "38s"
        assert _fmt_duration(600.0) == "10 min"


class TestAuthFailureIsFatal:
    """This error carries no HTTP status, so the 401/403/404 table cannot catch it —
    yet it is the most permanent failure of the lot."""

    def test_no_credential_message_is_recognised(self) -> None:
        exc = Exception(
            "Could not resolve authentication method. Expected one of api_key, "
            "auth_token, or credentials to be set."
        )
        assert _is_auth_failure(exc)

    def test_match_is_case_insensitive(self) -> None:
        assert _is_auth_failure(Exception("COULD NOT RESOLVE AUTHENTICATION METHOD"))

    def test_unrelated_errors_are_not_auth_failures(self) -> None:
        assert not _is_auth_failure(Exception("Error code: 529 - overloaded"))
        assert not _is_auth_failure(Exception("connection reset by peer"))

    def test_an_empty_message_is_not_an_auth_failure(self) -> None:
        assert not _is_auth_failure(Exception())

    def test_fatal_error_type_is_used(self) -> None:
        """extract_source re-raises FatalLLMError to stop on call #1 rather than
        grinding through the corpus reproducing one error."""
        assert issubclass(FatalLLMError, Exception)
