# -----------------------------------------------------------------------------
# Role: Implements the CLI block runtime and UI contract.
# File Name: block.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2024-04-21
# -----------------------------------------------------------------------------

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any
import re
import shlex
import subprocess
import time

from bloxsmith_app.block_api import (
    BlockDefinition,
    BlockRuntimeContext,
    BlockRuntimeOutput,
    BlockRuntimeResult,
    render_inspector_template,
    render_node_card_template,
    render_path_browser_control,
    TEXT_PLAIN,
)


DEFAULT_TIMEOUT_SEC = 30
DEFAULT_MAX_STDOUT_CHARS = 200_000
MAX_TIMEOUT_SEC = 3600
MAX_STDOUT_CHARS = 10_000_000
INPUT_REF_PATTERN = re.compile(r"@([A-Za-z_][A-Za-z0-9_]*)")


# Functional behavior:
# FB1 - Execute one local command per output port and emit stdout on the matching output.
# FB2 - Substitute named inputs referenced as @input_name, using shell quoting when configured.
# FB3 - Record command, stderr, exit code, duration, truncation state, and failure metadata in runtime logs/results.
# FB4 - Run commands only during runtime execution with the Python server process permissions.
# FB5 - Render a command-first modal where per-output commands are easier to edit than in the inspector.
class CliBlockError(ValueError):
    """Raised when a CLI block cannot execute a configured command."""


class CliBlock(BlockDefinition):
    """Autonomous block implementation for `CliBlock`."""
    kind = "cli"

    def render_modal(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the CLI block modal with command editing as the primary tab."""

        config = self._ui_config(node)
        template = (self.directory / "block_modal.html").read_text(encoding="utf-8")
        title = str(node.get("title") or self.default_title())
        replacements = {
            "node_id": escape(str(node.get("id") or ""), quote=True),
            "node_title": escape(title),
            "node_kind": escape(self.kind, quote=True),
            "node_kind_title": escape(str(self.model.get("title") or self.default_title())),
            "title_field_html": self._render_modal_title_field(title),
            "attributes_html": self._render_modal_attributes(config),
            "commands_html": self._render_command_rows(node),
            "input_refs_html": self._render_input_reference_list(node),
            "ports_html": self._render_generic_modal_ports(node),
            "runtime_html": self._render_generic_modal_runtime(payload or {}),
        }
        html = template
        for key, value in replacements.items():
            html = html.replace(f"{{{{ {key} }}}}", str(value))
        return {
            "html": html,
            "context": {
                "node_id": str(node.get("id") or ""),
                "node_kind": self.kind,
            },
        }

    def render_node_card(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the CLI canvas card body from the block-owned template."""

        config = self._ui_config(node)
        outputs = node.get("outputs") if isinstance(node.get("outputs"), list) else []
        first_command = next((str(port.get("command") or "").strip() for port in outputs if isinstance(port, dict) and str(port.get("command") or "").strip()), "")
        return render_node_card_template(
            block=self,
            node=node,
            node_classes=["cli-node"],
            replacements={
                "title": node.get("title") or self.default_title(),
                "command": self._truncate(first_command or "commande vide", 38),
                "timeout": f"{config['timeout_sec']}s",
                "outputs": f"{len(outputs)} sortie{'s' if len(outputs) > 1 else ''}",
            },
        )

    def render_inspector_panel(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the block-owned inspector panel HTML for the selected node.

        Args:
            node: Serialized graph node handled by the block.
            payload: Optional UI or runtime payload provided by the framework.
        """
        config = self._ui_config(node)
        template = (self.directory / "inspector_panel.html").read_text(encoding="utf-8")
        html = render_inspector_template(
            template=(
                template
                .replace("{{ working_directory }}", escape(config["working_directory"]))
                .replace("{{ working_directory_browser_html }}", self._render_working_directory_browser(config, input_id="cliInspectorWorkingDirectoryInput"))
                .replace("{{ timeout_sec }}", str(config["timeout_sec"]))
                .replace("{{ max_stdout_chars }}", str(config["max_stdout_chars"]))
                .replace("{{ use_shell_checked }}", "checked" if config["use_shell"] else "")
                .replace("{{ quote_inputs_checked }}", "checked" if config["quote_inputs"] else "")
                .replace("{{ quote_inputs_disabled }}", "" if config["use_shell"] else "disabled")
                .replace("{{ commands_html }}", self._render_command_rows(node))
            ),
            node={**node, "type": self.kind, "kind": self.kind},
            payload=payload,
        )
        return {"html": html, "context": {"node_id": str(node.get("id") or ""), "full_panel": True}}

    def _ui_config(self, node: dict[str, Any]) -> dict[str, Any]:
        """Provide internal CliBlock behavior for `_ui_config`.

        Args:
            node: Serialized graph node handled by the block.
        """
        raw = node.get("cli") if isinstance(node.get("cli"), dict) else node.get("config")
        raw = raw if isinstance(raw, dict) else {}
        return {
            "working_directory": str(raw.get("working_directory", "") or ""),
            "timeout_sec": self._normalize_int(raw.get("timeout_sec"), default=DEFAULT_TIMEOUT_SEC, minimum=1, maximum=MAX_TIMEOUT_SEC),
            "max_stdout_chars": self._normalize_int(raw.get("max_stdout_chars"), default=DEFAULT_MAX_STDOUT_CHARS, minimum=1, maximum=MAX_STDOUT_CHARS),
            "use_shell": self._normalize_bool(raw.get("use_shell", True)),
            "quote_inputs": self._normalize_bool(raw.get("quote_inputs", True)),
        }

    def _render_modal_title_field(self, title: str) -> str:
        """Render the editable title field without duplicating the modal footer apply action."""

        return (
            '<div class="field-group">'
            "<label>Block name</label>"
            f'<input data-block-title-field type="text" autocomplete="off" value="{escape(title, quote=True)}" />'
            "</div>"
        )

    def _render_modal_attributes(self, config: dict[str, Any]) -> str:
        """Render CLI execution settings for the modal attributes tab."""

        return "\n".join(
            [
                '<div class="cli-modal-config-grid">',
                '  <div class="cli-modal-config-wide">',
                self._render_working_directory_browser(config, input_id="cliModalWorkingDirectoryInput"),
                "  </div>",
                '  <div class="field-group">',
                "    <label>Timeout secondes</label>",
                (
                    f'    <input data-cli-timeout data-block-config-field="timeout_sec" data-block-value-type="integer" '
                    f'type="number" min="1" max="{MAX_TIMEOUT_SEC}" step="1" value="{config["timeout_sec"]}" />'
                ),
                "  </div>",
                '  <div class="field-group">',
                "    <label>Max stdout chars</label>",
                (
                    f'    <input data-cli-max-stdout data-block-config-field="max_stdout_chars" data-block-value-type="integer" '
                    f'type="number" min="1" max="{MAX_STDOUT_CHARS}" step="1000" value="{config["max_stdout_chars"]}" />'
                ),
                "  </div>",
                '  <label class="checkbox-field">',
                (
                    f'    <input data-cli-use-shell data-block-config-field="use_shell" data-block-value-type="boolean" '
                    f'type="checkbox" {"checked" if config["use_shell"] else ""} />'
                ),
                "    <span>Utiliser le shell</span>",
                "  </label>",
                '  <label class="checkbox-field">',
                (
                    f'    <input data-cli-quote-inputs data-block-config-field="quote_inputs" data-block-value-type="boolean" '
                    f'type="checkbox" {"checked" if config["quote_inputs"] else ""} {"disabled" if not config["use_shell"] else ""} />'
                ),
                "    <span>Shell-quoter les valeurs @input</span>",
                "  </label>",
                "</div>",
            ]
        )

    def _render_working_directory_browser(self, config: dict[str, Any], *, input_id: str) -> str:
        """Render the shared directory browser for the CLI working directory."""

        return render_path_browser_control(
            input_id=input_id,
            label="Répertoire de travail",
            value=str(config.get("working_directory") or ""),
            placeholder="vide = racine du projet",
            input_attrs='data-cli-working-directory data-block-config-field="working_directory"',
            select_mode="directory",
        )

    def _render_command_rows(self, node: dict[str, Any]) -> str:
        """Render a block-owned HTML fragment used by the modal or inspector.

        Args:
            node: Serialized graph node handled by the block.
        """
        outputs = node.get("outputs") if isinstance(node.get("outputs"), list) else []
        if not outputs:
            return '<div class="ports-editor-empty">No CLI output.</div>'
        rows: list[str] = []
        for port in outputs:
            if not isinstance(port, dict):
                continue
            port_id = int(port.get("id") or 0)
            label = f"{port.get('title') or 'Out'} · {port.get('name') or f'out{port_id}'}"
            rows.append(
                "\n".join(
                    [
                        f'<div class="cli-command-row" data-port-id="{port_id}">',
                        f"  <label>{escape(label)}</label>",
                        (
                            f'  <textarea rows="3" data-cli-command-port-id="{port_id}" '
                            f'data-block-output-field="command" data-block-output-port-id="{port_id}" '
                            f'placeholder=\'printf "%s" @in\' spellcheck="false" autocapitalize="off" '
                            f'autocomplete="off">{escape(str(port.get("command") or ""))}</textarea>'
                        ),
                        "  <small>Utilise @nom_input pour injecter une entrée. Les valeurs sont shell-quotées par défaut.</small>",
                        "</div>",
                    ]
                )
            )
        return "\n".join(rows)

    def _render_input_reference_list(self, node: dict[str, Any]) -> str:
        """Render placeholder references available for command substitution."""

        inputs = node.get("inputs") if isinstance(node.get("inputs"), list) else []
        refs: list[str] = []
        for port in inputs:
            if not isinstance(port, dict):
                continue
            name = str(port.get("name") or "").strip()
            if name:
                refs.append(f"@{name}")
        if not refs:
            return '<div class="ports-editor-empty">No input available.</div>'
        return "\n".join(f"<code>{escape(ref)}</code>" for ref in refs)

    def _truncate(self, value: str, max_length: int) -> str:
        """Return a compact one-line label for the node card preview."""

        text = str(value or "").replace("\n", " ").strip()
        return text if len(text) <= max_length else f"{text[: max_length - 1]}..."

    def normalize_config(self, config: dict[str, Any] | None) -> dict[str, Any]:
        """Normalize raw node configuration into safe block runtime settings.

        Args:
            config: Raw or normalized block configuration.
        """
        raw_config = config if isinstance(config, dict) else {}
        return {
            "working_directory": str(raw_config.get("working_directory", "") or "").strip(),
            "timeout_sec": self._normalize_int(
                raw_config.get("timeout_sec"),
                default=DEFAULT_TIMEOUT_SEC,
                minimum=1,
                maximum=MAX_TIMEOUT_SEC,
            ),
            "max_stdout_chars": self._normalize_int(
                raw_config.get("max_stdout_chars"),
                default=DEFAULT_MAX_STDOUT_CHARS,
                minimum=1,
                maximum=MAX_STDOUT_CHARS,
            ),
            "use_shell": self._normalize_bool(raw_config.get("use_shell", True)),
            "quote_inputs": self._normalize_bool(raw_config.get("quote_inputs", True)),
        }

    def execute(
        self,
        *,
        root_dir: Path,
        config: dict[str, Any] | None,
        inputs: dict[str, Any],
        outputs: list[Any] | tuple[Any, ...],
    ) -> dict[str, Any]:
        """Execute the block business logic with normalized inputs and configuration.

        Args:
            root_dir: Directory path used by the block runtime.
            config: Raw or normalized block configuration.
            inputs: Input values received by the block.
            outputs: Output definitions or output accumulator for the block.
        """
        normalized_config = self.normalize_config(config)
        root = root_dir.expanduser().resolve()
        cwd = self._resolve_working_directory(root, normalized_config["working_directory"])
        if not cwd.exists() or not cwd.is_dir():
            raise CliBlockError(f"Répertoire de travail CLI introuvable: {cwd}")

        output_results: list[dict[str, Any]] = []
        for output in outputs:
            command_template = str(getattr(output, "command", "") or "").strip()
            port_id = int(getattr(output, "id", getattr(output, "port_id", 0)) or 0)
            port_name = str(getattr(output, "name", getattr(output, "port_name", "")) or port_id)
            output_results.append(
                self._execute_output_command(
                    command_template,
                    port_id=port_id,
                    port_name=port_name,
                    root=root,
                    cwd=cwd,
                    inputs=inputs,
                    config=normalized_config,
                )
            )

        failed = [item for item in output_results if int(item.get("exit_code") or 0) != 0]
        return {
            "status": "failed" if failed else "success",
            "outputs": output_results,
            "working_directory": str(cwd),
            "timeout_sec": normalized_config["timeout_sec"],
            "max_stdout_chars": normalized_config["max_stdout_chars"],
            "use_shell": normalized_config["use_shell"],
            "quote_inputs": normalized_config["quote_inputs"],
        }

    def execute_runtime(self, context: BlockRuntimeContext) -> BlockRuntimeResult:
        """Execute the block through the generic runtime context and return runtime outputs.

        Args:
            context: Generic runtime context injected by the execution engine.
        """
        execution = self.execute(
            root_dir=context.root_dir,
            config=context.config,
            inputs=self._named_inputs(context),
            outputs=context.output_ports,
        )
        output_records = execution.get("outputs") if isinstance(execution.get("outputs"), list) else []
        outputs: list[BlockRuntimeOutput] = []
        logs: list[str] = []
        last_message = ""
        failed_records: list[dict[str, Any]] = []

        for record in output_records:
            if not isinstance(record, dict):
                continue
            port_id = int(record.get("port_id") or 0)
            stdout = str(record.get("stdout") or "")
            stderr = str(record.get("stderr") or "")
            exit_code = int(record.get("exit_code") or 0)
            status = "success" if exit_code == 0 else "failed"
            expanded_command = str(record.get("expanded_command") or record.get("command") or "")
            port_name = str(record.get("port_name") or "")
            logs.append(f"[cli-cmd] {context.node_id}.{port_name or port_id}: {expanded_command}")
            logs.append(f"[cli-exit] {context.node_id}.{port_name or port_id}: exit_code={exit_code}")
            logs.extend(f"[cli-stderr] {line}" for line in stderr.splitlines())
            if bool(record.get("stdout_truncated")):
                logs.append(f"[cli-warn] {context.node_id}.{port_name or port_id}: stdout tronque.")
            outputs.append(
                BlockRuntimeOutput(
                    port_id=port_id,
                    port_name=port_name,
                    value=stdout,
                    content_type=TEXT_PLAIN,
                    status=status,
                    exit_code=exit_code,
                    metadata={
                        "stderr": stderr,
                        "command": str(record.get("command") or ""),
                        "expanded_command": expanded_command,
                        "duration": record.get("duration"),
                        "stdout_truncated": bool(record.get("stdout_truncated")),
                    },
                )
            )
            if stdout:
                last_message = stdout
            if exit_code != 0:
                failed_records.append(record)

        if failed_records:
            error = str(failed_records[0].get("stderr") or "Commande CLI en echec.").strip()
            logs.append(f"[cli-error] {context.node_id}: {error or 'commande en echec.'}")
            return BlockRuntimeResult(
                status="failed",
                outputs=outputs,
                logs=logs,
                error=error,
                exit_code=1,
                last_message=error or last_message,
                worker_received=error or last_message or "-",
                metadata=self._runtime_metadata(execution),
            )
        logs.append(f"[done] CLI {context.node_id}: {len(outputs)} output(s) emis.")
        return BlockRuntimeResult(
            status="success",
            outputs=outputs,
            logs=logs,
            last_message=last_message,
            worker_received=last_message or "-",
            metadata=self._runtime_metadata(execution),
        )

    def _named_inputs(self, context: BlockRuntimeContext) -> dict[str, str]:
        """Provide internal CliBlock behavior for `_named_inputs`.

        Args:
            context: Generic runtime context injected by the execution engine.
        """
        inputs: dict[str, str] = {}
        for input_port in context.input_ports:
            port_id = str(getattr(input_port, "id", "") or "")
            port_name = str(getattr(input_port, "name", "") or "").strip() or port_id
            inputs[port_name] = str(context.input_value(port_name, port_id) or "")
        return inputs

    def _runtime_metadata(self, execution: dict[str, Any]) -> dict[str, Any]:
        """Provide internal CliBlock behavior for `_runtime_metadata`.

        Args:
            execution: Execution value used by this block helper.
        """
        return {
            "working_directory": str(execution.get("working_directory") or ""),
            "timeout_sec": execution.get("timeout_sec"),
            "max_stdout_chars": execution.get("max_stdout_chars"),
            "use_shell": execution.get("use_shell"),
            "quote_inputs": execution.get("quote_inputs"),
        }

    def _execute_output_command(
        self,
        command_template: str,
        *,
        port_id: int,
        port_name: str,
        root: Path,
        cwd: Path,
        inputs: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Provide internal CliBlock behavior for `_execute_output_command`.

        Args:
            command_template: Command template value used by this block helper.
            port_id: Numeric port identifier.
            port_name: Port name used in runtime payloads.
            root: Mounted UI root element or repository root depending on the caller.
            cwd: Cwd value used by this block helper.
            inputs: Input values received by the block.
            config: Raw or normalized block configuration.
        """
        started = time.perf_counter()
        if not command_template:
            return {
                "port_id": port_id,
                "port_name": port_name,
                "command": "",
                "expanded_command": "",
                "stdout": "",
                "stderr": "Commande CLI vide.",
                "exit_code": 2,
                "duration": 0,
                "stdout_truncated": False,
            }

        expanded_command = self._substitute_inputs(
            command_template,
            inputs=inputs,
            quote=bool(config["use_shell"] and config["quote_inputs"]),
        )
        try:
            completed = subprocess.run(
                expanded_command if config["use_shell"] else shlex.split(expanded_command),
                cwd=str(cwd),
                shell=bool(config["use_shell"]),
                text=True,
                capture_output=True,
                timeout=int(config["timeout_sec"]),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = self._decode_process_text(exc.stdout)
            stderr = self._decode_process_text(exc.stderr)
            stdout, stdout_truncated = self._truncate_stdout(stdout, int(config["max_stdout_chars"]))
            return {
                "port_id": port_id,
                "port_name": port_name,
                "command": command_template,
                "expanded_command": expanded_command,
                "stdout": stdout,
                "stderr": stderr or f"CLI timeout after {config['timeout_sec']}s.",
                "exit_code": -1,
                "duration": round(time.perf_counter() - started, 3),
                "stdout_truncated": stdout_truncated,
            }
        except (OSError, ValueError) as exc:
            return {
                "port_id": port_id,
                "port_name": port_name,
                "command": command_template,
                "expanded_command": expanded_command,
                "stdout": "",
                "stderr": f"Execution CLI impossible: {exc}",
                "exit_code": 1,
                "duration": round(time.perf_counter() - started, 3),
                "stdout_truncated": False,
            }

        stdout, stdout_truncated = self._truncate_stdout(
            completed.stdout or "",
            int(config["max_stdout_chars"]),
        )
        return {
            "port_id": port_id,
            "port_name": port_name,
            "command": command_template,
            "expanded_command": expanded_command,
            "stdout": stdout,
            "stderr": completed.stderr or "",
            "exit_code": int(completed.returncode),
            "duration": round(time.perf_counter() - started, 3),
            "stdout_truncated": stdout_truncated,
        }

    def _substitute_inputs(self, command: str, *, inputs: dict[str, Any], quote: bool) -> str:
        """Provide internal CliBlock behavior for `_substitute_inputs`.

        Args:
            command: Command value used by this block helper.
            inputs: Input values received by the block.
            quote: Quote value used by this block helper.
        """
        def replace(match: re.Match[str]) -> str:
            """Provide internal CliBlock behavior for `replace`.

            Args:
                match: Match value used by this block helper.
            """
            name = match.group(1)
            value = "" if inputs.get(name) is None else str(inputs.get(name))
            return shlex.quote(value) if quote else value

        return INPUT_REF_PATTERN.sub(replace, command)

    def _resolve_working_directory(self, root: Path, raw_value: str) -> Path:
        """Resolve a configured value against runtime or project context.

        Args:
            root: Mounted UI root element or repository root depending on the caller.
            raw_value: Raw value received from configuration or runtime input.
        """
        if not raw_value:
            return root
        path = Path(raw_value).expanduser()
        if not path.is_absolute():
            path = root / path
        return path.resolve()

    def _truncate_stdout(self, stdout: str, max_chars: int) -> tuple[str, bool]:
        """Provide internal CliBlock behavior for `_truncate_stdout`.

        Args:
            stdout: Stdout value used by this block helper.
            max_chars: Max chars value used by this block helper.
        """
        if len(stdout) <= max_chars:
            return stdout, False
        return stdout[:max_chars], True

    def _decode_process_text(self, raw_value: Any) -> str:
        """Provide internal CliBlock behavior for `_decode_process_text`.

        Args:
            raw_value: Raw value received from configuration or runtime input.
        """
        if isinstance(raw_value, str):
            return raw_value
        if raw_value is None:
            return ""
        if isinstance(raw_value, bytes):
            return raw_value.decode("utf-8", "replace")
        return str(raw_value)

    def _normalize_bool(self, raw_value: Any) -> bool:
        """Normalize a raw value into the format expected by the block.

        Args:
            raw_value: Raw value received from configuration or runtime input.
        """
        if isinstance(raw_value, str):
            return raw_value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(raw_value)

    def _normalize_int(self, raw_value: Any, *, default: int, minimum: int, maximum: int) -> int:
        """Normalize a raw value into the format expected by the block.

        Args:
            raw_value: Raw value received from configuration or runtime input.
            default: Default value used when normalization fails.
            minimum: Lower bound accepted by the normalizer.
            maximum: Upper bound accepted by the normalizer.
        """
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))
