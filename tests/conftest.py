from __future__ import annotations

import socket
import threading
import time
from types import SimpleNamespace

import pytest
import uvicorn

from app.db import Database
from app.main import create_app
from app.seed import seed_demo


@pytest.fixture()
def env(tmp_path) -> SimpleNamespace:
    db = Database(tmp_path / "test.db")
    db.init_schema()
    seed_demo(db)
    app = create_app(db, serve_static=False)
    return SimpleNamespace(db=db, app=app, dir=tmp_path)


@pytest.fixture()
def live_server(env) -> str:
    """Real uvicorn server, needed for streaming and concurrency assertions (A6)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    config = uvicorn.Config(
        env.app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    if not server.started:
        raise RuntimeError("uvicorn failed to start for the live test")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)
