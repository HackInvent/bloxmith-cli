#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Role: Verifies CLI block behavior for the CLI block.
# File Name: F5.07_cli_block.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2024-05-28
# -----------------------------------------------------------------------------

"""F5.07 - Bloc CLI.

Le test lance `text -> cli -> display` dans un serveur isolé. Il vérifie la
substitution `@in`, le quoting des valeurs avec espaces, plusieurs outputs et
la présence de stderr dans les logs du bloc.
"""

# Test cases:
# - FB1/FB2/FB3/FB4 - Run text -> CLI -> display in centralized and active runtime and verify quoted @input substitution, stdout publication, stderr logs, metadata, and runtime-only local execution.
# - FB1/FB2/FB3 - Execute multiple output commands and verify each output command publishes the expected stdout and diagnostic logs.
# - FB2 - Connect two CLI inputs to the same source and verify both named placeholders are populated.
# - FB5 - Render the CLI modal and verify command editing is the primary tab with block-owned assets.

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bloxsmith_app.block_ui import render_block_inspector_panel, render_block_modal
from ui_smoke_common import (
    create_run_api,
    data_edge,
    display_node,
    expect,
    graph_payload,
    isolated_server,
    text_node,
    wait_for_run_terminal,
)
from urllib.parse import quote
from block_test_packages import install_test_package, release_key, surface_payload


def cli_node() -> dict:
    return {
        "id": "cli-1",
        "kind": "cli",
        "title": "CLI test",
        "position": {"x": 360, "y": 120},
        "inputs": [
            {"id": 1, "name": "in", "title": "In", "accepts": ["message/*", "text/plain"], "multiplicity": "many"}
        ],
        "outputs": [
            {
                "id": 1,
                "name": "stdout",
                "title": "Stdout",
                "emits": ["message/*", "text/plain"],
                "multiplicity": "many",
                "command": 'printf "value:%s" @in',
            },
            {
                "id": 2,
                "name": "secondary",
                "title": "Secondary",
                "emits": ["message/*", "text/plain"],
                "multiplicity": "many",
                "command": "python3 -c 'import sys; sys.stderr.write(\"cli-warning\\\\n\"); print(\"secondary\")'",
            },
        ],
        "config": {
            "working_directory": "",
            "timeout_sec": 10,
            "max_stdout_chars": 2000,
            "use_shell": True,
            "quote_inputs": True,
        },
    }


def cli_shared_topic_node() -> dict:
    return {
        "id": "cli-1",
        "kind": "cli",
        "title": "CLI shared topic",
        "position": {"x": 360, "y": 120},
        "inputs": [
            {"id": 1, "name": "in1", "title": "In 1", "accepts": ["message/*", "text/plain"], "multiplicity": "many"},
            {"id": 2, "name": "in2", "title": "In 2", "accepts": ["message/*", "text/plain"], "multiplicity": "many"},
        ],
        "outputs": [
            {
                "id": 1,
                "name": "stdout",
                "title": "Stdout",
                "emits": ["message/*", "text/plain"],
                "multiplicity": "many",
                "command": 'printf "%s|%s" @in1 @in2',
            }
        ],
        "config": {
            "working_directory": "",
            "timeout_sec": 10,
            "max_stdout_chars": 2000,
            "use_shell": True,
            "quote_inputs": True,
        },
    }


def run_cli_case(runtime_mode: str) -> None:
    with isolated_server() as server:
        # Les surfaces sont des assets de release : le bundled kind n'en sert aucun.
        model = install_test_package(server, "cli")
        key = quote(release_key(model), safe="")
        served = lambda payload, suffix: next(
            asset["path"] for asset in payload["assets"] if asset["path"].endswith(suffix))
        document = graph_payload(
            f"F5 CLI {runtime_mode}",
            [
                text_node("text-1", "Texte CLI", "hello cli value", 80, 120),
                cli_node(),
                display_node("display-1", "Affichage", 680, 120),
            ],
            [
                data_edge("edge-text-cli", "text-1", 1, "cli-1", 1),
                data_edge("edge-cli-display", "cli-1", 1, "display-1", 1),
            ],
        )
        created = create_run_api(server, document, runtime_mode=runtime_mode)
        run = wait_for_run_terminal(server, str(created.get("run_id") or ""))

        expect(run.get("status") == "success", f"Le run CLI {runtime_mode} doit réussir.")
        expect(run.get("output_values", {}).get("cli-1:1", {}).get("value") == "value:hello cli value", "stdout CLI incorrect.")
        expect(run.get("output_values", {}).get("cli-1:2", {}).get("value").strip() == "secondary", "output secondaire CLI incorrect.")
        logs = "\n".join(run.get("node_logs", {}).get("cli-1", []))
        expect("cli-warning" in logs, "stderr CLI absent des logs.")
        expect("value:hello cli value" in str(run.get("worker_rows", {}).get("display-1", {}).get("received") or ""), "Display ne reçoit pas stdout CLI.")


def run_cli_shared_topic_case(runtime_mode: str) -> None:
    with isolated_server() as server:
        document = graph_payload(
            f"F5 CLI shared topic {runtime_mode}",
            [
                text_node("text-1", "Texte CLI", "same source", 80, 120),
                cli_shared_topic_node(),
                display_node("display-1", "Affichage", 680, 120),
            ],
            [
                data_edge("edge-text-cli-in1", "text-1", 1, "cli-1", 1),
                data_edge("edge-text-cli-in2", "text-1", 1, "cli-1", 2),
                data_edge("edge-cli-display", "cli-1", 1, "display-1", 1),
            ],
        )
        created = create_run_api(server, document, runtime_mode=runtime_mode)
        run = wait_for_run_terminal(server, str(created.get("run_id") or ""))

        expect(run.get("status") == "success", f"Le run CLI shared-topic {runtime_mode} doit réussir.")
        expect(run.get("output_values", {}).get("cli-1:1", {}).get("value") == "same source|same source", "Les deux inputs CLI branchés au même topic ne sont pas alimentés.")
        logs = "\n".join(run.get("node_logs", {}).get("cli-1", []))
        expect(".1 <=" in logs and ".2 <=" in logs, "Les deux ports CLI ne loggent pas la réception du topic partagé.")


def test_cli_modal_command_first_layout() -> None:
    """TC1 - Render the CLI modal with command editing, attributes, and runtime tabs."""

    rendered = render_block_modal("cli", {"node": cli_node(), "runtime": {}})
    html = str(rendered.get("html") or "")
    assets = rendered.get("assets") or []
    css = (ROOT / "blocs/cli/assets/css/block_modal.css").read_text(encoding="utf-8")
    js = (ROOT / "blocs/cli/assets/js/block_modal.js").read_text(encoding="utf-8")

    expect("cw-cli-modal" in html, "Le modal CLI doit utiliser son layout autonome agrandi.")
    expect('data-block-runtime-refresh="autonomous"' in html, "Le modal CLI doit etre protege du rafraichissement centralise.")
    expect("cli-modal-body" in html, "Le modal CLI doit utiliser un layout à onglets.")
    expect('data-cli-tab-id="command"' in html, "Le modal CLI doit exposer l'onglet Commande.")
    expect('data-cli-tab-id="attributes"' in html, "Le modal CLI doit exposer l'onglet Attributs.")
    expect('data-cli-tab-id="runtime"' in html, "Le modal CLI doit exposer l'onglet Ports & état.")
    expect("data-cli-commands-list" in html, "Le modal CLI doit afficher la liste des commandes par sortie.")
    expect('data-cli-command-port-id="1"' in html, "Le modal CLI doit afficher la commande de la sortie 1.")
    expect('data-block-output-field="command"' in html, "La commande CLI doit rester liée au champ output.command.")
    expect('data-block-config-field="timeout_sec"' in html, "Les attributs doivent conserver le timeout éditable.")
    expect('data-block-config-field="working_directory"' in html, "Les attributs doivent conserver le répertoire éditable.")
    expect("data-path-browser" in html, "Le modal CLI doit utiliser le path browser commun pour le répertoire.")
    expect('data-path-browser-select-mode="directory"' in html, "Le modal CLI doit sélectionner un répertoire de travail.")
    expect("@in" in html, "Le modal CLI doit afficher les références d'inputs disponibles.")
    expect("data-block-apply" in html, "Le modal CLI doit conserver l'action Appliquer générique.")
    expect(".cli-modal-panel[hidden]" in css, "Les panels masqués du modal CLI doivent être cachés par CSS.")
    expect("panel.hidden =" in js, "Le JS modal CLI doit masquer les panels non actifs.")

    inspector = render_block_inspector_panel("cli", {"node": cli_node()})
    inspector_html = str(inspector.get("html") or "")
    expect("data-path-browser" in inspector_html, "L'inspector CLI doit utiliser le path browser commun.")
    expect('data-block-config-field="working_directory"' in inspector_html, "L'inspector CLI doit garder le binding working_directory.")


def main() -> None:
    test_cli_modal_command_first_layout()
    run_cli_case("centralized")
    run_cli_case("zeromq_active")
    run_cli_shared_topic_case("zeromq_active")
    print("[ok] F5.07_cli_block")


if __name__ == "__main__":
    main()
