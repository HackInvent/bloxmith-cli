# CLI Block

<!-- block-metadata:start -->
[![Block version: unversioned](https://img.shields.io/badge/block-unversioned-lightgrey)](model.json)
[![BloxSmith compatibility: 1.0.9](https://img.shields.io/badge/BloxSmith-1.0.9-brightgreen)](compatibility.json)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

Verified BloxSmith versions: **1.0.9** (bundled-block tests; see [test evidence](compatibility.json)).
<!-- block-metadata:end -->


## Role

`cli` executes configured command lines and emits command stdout.

## Files

- `block.py`: command normalization, input substitution, process execution, timeout, stdout truncation, and inspector rendering.
- `model.json`: default input, stdout output command, and execution config.
- `inspector_panel.html`: CLI inspector UI.
- `block_modal.html`: command-first modal UI.
- `assets/css/block_modal.css`: modal layout and command editor styles.
- `assets/js/block_modal.js`: modal tab, shortcut, and shell-option bindings.
- `node_card.html`: block-owned canvas card body.

## Ports

- Inputs:
  - `in` (`id: 1`): optional input; accepts text, JSON, file paths, and generic messages.
- Outputs:
  - `stdout` (`id: 1`): emits `message/*` and `text/plain`; its `command` field contains the command for that output.

## Configuration

- `working_directory`: optional working directory, resolved from the project root when relative.
- `timeout_sec`: process timeout.
- `max_stdout_chars`: maximum stdout retained/emitted.
- `use_shell`: executes through the shell when true.
- `quote_inputs`: shell-quotes substituted input placeholders when true.

## Runtime Behavior

`execute_runtime()` builds named inputs, executes each output port command, substitutes placeholders such as `@in`, enforces timeout/truncation, and emits stdout per output.

## UI Behavior

The inspector renders global execution settings and command rows derived from
output ports. Editable inspector fields use the generic block UI field-binding
contract. Settings and per-output commands are kept pending while edited and are
persisted through the GraphController only when the user clicks **Apply**.

The modal is optimized for command editing. It opens on a **Command** tab, shows
one command editor per output port, lists available `@input` placeholders, and
keeps `Ctrl+Enter` bound to **Apply**. **Attributes** contains title and execution
settings, including a shared `CWPathBrowser` directory picker for `working_directory`.
The inspector uses the same shared picker for the same field. **Ports & state** keeps port and latest runtime information visible
without mixing them with the command editor.

## Editor Display

The canvas card is rendered by this block through `node_card.html`. It exposes the block-specific command preview, output count, and timeout while the shared editor shell keeps ports, dragging, status, and graph links generic.

## Modal

`block_modal.html` is owned by this block and rendered by `CliBlock.render_modal()`.
The modal uses block-owned assets declared by `ui_assets("modal")`, declares
`data-block-runtime-refresh="autonomous"`, and keeps all editable fields on the
existing generic binding contract: `data-block-title-field`,
`data-block-config-field`, `data-block-output-field`, and `data-block-apply`.
The working directory field remains generic but is rendered through the shared
path browser with directory-selection mode.

## Maintenance Notes

Command execution belongs here. The `shell` block is intentionally passthrough and must not gain command execution by accident.

## Compatibility policy

[compatibility.json](compatibility.json) records HackInvent's verified BloxSmith versions and test evidence. Only the versions listed above have been verified, using the block-owned suites in a **bundled-block test installation**. This is not a certification of managed-package installation, every browser/OS, or live provider availability. Other framework versions are unverified, not necessarily incompatible.

The block-version badge follows `model.json`, not a published Git tag. `unversioned` means that no block release version is declared; no number is inferred from the framework version. The framework still uses `model.json` for its runtime/install contract; the tester-owned JSON does not replace it. Official integration tests run in the private `bloxmith-blocs` workspace. Test helpers and the proprietary framework are not bundled in this public block repository.
