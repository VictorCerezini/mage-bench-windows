"""Launch the ordinary match GUI and its private local server; no inference at startup."""

import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from windows import local_smoke as local
from windows import model_catalog, paths, subscription_client


def launch_gui(env, port, catalog, run, log):
    support = paths.LOCAL_ROOT / "support"
    classpath = str(support / "classes") + ";" + (support / "gui-classpath.txt").read_text().strip()
    properties = {
        "catalog": str(catalog),
        "repo": str(paths.REPO),
        "python": str(paths.REPO / ".venv/Scripts/python.exe"),
        "serverPort": str(port),
        "runs": str(run / "players"),
    }
    arguments = [
        *paths.common_java_arguments(),
        "-Xmx1536m",
        "-Dxmage.fullScreen=false",
        "-Dxmage.aiPuppeteer.autoConnect=true",
        "-Dxmage.aiPuppeteer.autoStart=false",
        f"-Dexperiment.deck={(paths.WINDOWS / 'decks/mirror-slither.dck').as_posix()}",
        *(f"-Dxmage.subscription.{key}={value}" for key, value in properties.items()),
        "-cp",
        classpath,
        "experiment.MatchGui",
    ]
    args_file = run / "match-gui.args"
    args_file.write_text(
        "\n".join('"' + arg.replace("\\", "/").replace('"', '\\"') + '"' for arg in arguments), encoding="utf-8"
    )
    return subprocess.Popen(
        [str(local.JDK / "bin/java.exe"), "@" + str(args_file)],
        cwd=paths.REPO / "Mage.Client",
        env=env | {"XMAGE_AI_PUPPETEER": "0"},
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def main():
    run = paths.LOCAL_ROOT / "outputs/gui-sessions" / datetime.now(UTC).strftime("match_%Y%m%d_%H%M%S_UTC")
    run.mkdir(parents=True)
    print(f"Local session logs: {run}", flush=True)
    catalog = model_catalog.discover()
    catalog_path = run / "chatgpt-models.json"
    local.save_json(catalog_path, catalog)
    print(f"Discovered {len(catalog['models'])} ChatGPT models; no model turn started", flush=True)
    env = subscription_client.clean_env()
    env["JAVA_HOME"] = str(local.JDK)
    env["PATH"] = str(local.JDK / "bin") + ";" + str(local.MAVEN.parent) + ";" + env["PATH"]
    port, reservations = local.reserve_ports()
    env.update(
        {
            "XMAGE_AI_PUPPETEER_SERVER": "127.0.0.1",
            "XMAGE_AI_PUPPETEER_PORT": str(port),
            "XMAGE_AI_PUPPETEER_USER": "You",
            "XMAGE_AI_PUPPETEER_PASSWORD": "",
            "XMAGE_AI_PUPPETEER_DISABLE_WHATS_NEW": "1",
        }
    )
    config = ET.parse(paths.REPO / "Mage.Server/config/config.xml")
    server_config = config.getroot().find("server")
    assert server_config is not None
    for key, value in {"serverAddress": "127.0.0.1", "port": str(port), "secondaryBindPort": str(port + 8)}.items():
        server_config.set(key, value)
    config_path = run / "server_config.xml"
    config.write(config_path, encoding="utf-8", xml_declaration=True)
    processes = []
    manifest = {"status": "starting", "inference_on_startup": False, "server_port": port}
    try:
        for sock in reservations:
            sock.close()
        with (
            (run / "server.log").open("w", encoding="utf-8") as server_log,
            (run / "gui.log").open("w", encoding="utf-8") as gui_log,
        ):
            common = subprocess.list2cmdline(paths.common_java_arguments())
            server = local.launch(
                "Mage.Server",
                env
                | {
                    "MAVEN_OPTS": (
                        f"{common} -Xmx1024m -Dxmage.testMode=false -Dxmage.config.path={config_path.as_posix()}"
                    )
                },
                server_log,
            )
            processes.append(server)
            local.wait_server(server, port)
            gui = launch_gui(env, port, catalog_path, run, gui_log)
            processes.append(gui)
            manifest["status"] = "gui_open"
            local.save_json(run / "manifest.json", manifest)
            while gui.poll() is None:
                if server.poll() is not None:
                    raise RuntimeError("The local XMage server stopped; see server.log")
                time.sleep(1)
            if gui.returncode != 0:
                raise RuntimeError("The XMage GUI stopped with an error; see gui.log")
            manifest["status"] = "closed"
    except Exception as error:
        manifest.update(status="failed", error=str(error))
        raise
    finally:
        for proc in reversed(processes):
            local.stop_tree(proc)
        manifest["cleanup_complete"] = all(proc.poll() is not None for proc in processes)
        local.save_json(run / "manifest.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
