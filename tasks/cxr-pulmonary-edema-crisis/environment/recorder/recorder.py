"""
recorder.py

The "security camera in the hallway" - a tiny HTTP server running as its
own compose service, outside the agent's (`main`'s) container. The agent
POSTs each log_step() entry here as it works; this process is the one
that actually writes log.jsonl to disk, on a filesystem `main` has no
access to. `main` can add new events - it has no route to edit, delete,
or replace ones already written. Harbor pulls the finished file out of
THIS service (via task.toml's artifacts array) after `main` is stopped,
the same way [[verifier.collect]] already pulls ground truth out of the
`mysql` service rather than trusting anything the agent's own container
claims.

Stdlib only, deliberately - this container has one job and shouldn't need
a dependency install step to do it.
"""

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA_DIR = Path("/data")
# Matches agent_episode.py's own episode_dir naming
# (f"{patient_id}_{visit_date}_{timestamp}") - rejects anything else so a
# path-traversal attempt (e.g. "../../etc") can't escape DATA_DIR.
EPISODE_NAME_RE = re.compile(r"^[A-Za-z0-9]+_\d{4}-\d{2}-\d{2}_\d+$")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # noqa: A003 - stdlib override
        pass  # keep container logs quiet; nothing here is worth alerting on

    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        # Only real endpoint: append one JSON log entry to one episode's
        # log.jsonl. No GET-back, no edit, no delete - an append-only API
        # has no way to rewrite history even if `main` is fully
        # compromised, which is the actual property this service exists
        # to provide.
        match = re.fullmatch(r"/episodes/([^/]+)/events", self.path)
        if not match or not EPISODE_NAME_RE.match(match.group(1)):
            self.send_response(404)
            self.end_headers()
            return

        episode_name = match.group(1)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            entry = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        episode_dir = DATA_DIR / episode_name
        episode_dir.mkdir(parents=True, exist_ok=True)
        with (episode_dir / "log.jsonl").open("a") as f:
            f.write(json.dumps(entry) + "\n")

        self.send_response(204)
        self.end_headers()


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
