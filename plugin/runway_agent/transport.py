"""Reaching a worker: hand it the packet, start it through Herdr, pull its outbox, ask Herdr how it is.

Everything goes over the SSH link the controller already has. The Herdr commands are templates in
~/.runway-agent/config.json, because they must match the Herdr version on the fleet; nothing here
guesses at a flag the operator hasn't confirmed.
"""

import json
import subprocess

from . import store

WORKER_HOME = "~/.runway-agent"
WORK_PROMPT = ("Work Runway Agent ticket {ticket}. Use the runway-agent:work-ticket skill with the packet at "
               "{packet_path}. Its claim check comes first.")


class TransportError(Exception):
    pass


def config():
    path = store.home() / "config.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _sh(machine, command, stdin=None):
    """Run a shell command on the machine: locally for the controller, over ssh otherwise."""
    if _local(machine):
        args = ["sh", "-c", command]
    else:
        args = ["ssh", "-o", "BatchMode=yes", machine["ssh_host"], command]
    out = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise TransportError(f"{machine['label']}: {out.stderr.strip() or 'exit ' + str(out.returncode)}")
    return out.stdout


def _local(machine):
    return machine["kind"] == "local" or not machine["ssh_host"]


def send_packet(machine, packet):
    if _local(machine):
        path = store.home() / "packets" / f"{packet['dispatch_id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(packet, indent=2))
        return str(path)
    path = f"{WORKER_HOME}/packets/{packet['dispatch_id']}.json"
    _sh(machine, f"mkdir -p {WORKER_HOME}/packets && cat > {path}", stdin=json.dumps(packet, indent=2))
    return path


def launch_args(machine, packet, packet_path, cfg=None):
    template = (cfg if cfg is not None else config()).get("herdr_launch")
    if not template:
        raise TransportError("no herdr_launch template in config.json; see the plugin README, Launching through Herdr")
    values = {
        "herdr_label": machine["herdr_label"] or machine["label"],
        "machine": machine["label"],
        "dispatch_id": packet["dispatch_id"],
        "ticket": packet["ticket"],
        "packet_path": packet_path,
        "prompt": WORK_PROMPT.format(ticket=packet["ticket"], packet_path=packet_path),
    }
    return [part.format(**values) for part in template]


def launch(conn, machine, packet):
    """Send the packet and start the session. Returns the Herdr session id if Herdr printed one."""
    packet_path = send_packet(machine, packet)
    args = launch_args(machine, packet, packet_path)
    out = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise TransportError(f"herdr launch failed: {out.stderr.strip()}")
    session = None
    try:
        data = json.loads(out.stdout)
        session = str(data.get("id") or data.get("session") or data.get("pane") or "") or None
    except ValueError:
        pass
    store.set_herdr_session(conn, packet["dispatch_id"], session or "unknown")
    return session


def read_outbox(machine):
    if _local(machine):
        return [line for f in sorted((store.home() / "outbox").glob("*.jsonl")) for line in f.read_text().splitlines()]
    return _sh(machine, f"cat {WORKER_HOME}/outbox/*.jsonl 2>/dev/null || true").splitlines()


def herdr_states(machine, cfg=None):
    """Map Herdr session id -> state, from the operator's herdr_list template. Empty when unconfigured."""
    template = (cfg if cfg is not None else config()).get("herdr_list")
    if not template:
        return {}
    args = [p.format(herdr_label=machine["herdr_label"] or machine["label"]) for p in template]
    out = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        return {}
    try:
        rows = json.loads(out.stdout)
    except ValueError:
        return {}
    rows = rows.get("agents", rows) if isinstance(rows, dict) else rows
    return {str(r.get("id") or r.get("session") or r.get("pane")): r.get("state", "unknown") for r in rows}
