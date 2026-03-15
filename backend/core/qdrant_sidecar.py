"""Qdrant server sidecar — for DMG/packaged distribution."""
from __future__ import annotations

import os
import socket
import subprocess
import time
from typing import Optional

from core.logger import logger


def find_free_port(start: int = 6333) -> int:
    """Scan for a free TCP port starting from `start`."""
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


def _wait_for_ready(port: int, timeout: float = 15.0) -> bool:
    """Poll until Qdrant is accepting connections or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def start_qdrant_sidecar(
    binary_path: str,
    storage_path: str,
    port: Optional[int] = None,
) -> tuple[subprocess.Popen, int]:
    """
    Launch Qdrant as a sidecar process.

    Args:
        binary_path: Path to the qdrant binary (bundled in DMG).
        storage_path: Directory for Qdrant data (e.g. ~/.localrag/qdrant/).
        port: Port to bind (auto-selected if None).

    Returns:
        (process, port) tuple.
    """
    if not os.path.isfile(binary_path):
        raise FileNotFoundError(f"Qdrant binary not found at: {binary_path}")

    port = port or find_free_port()
    os.makedirs(storage_path, exist_ok=True)

    proc = subprocess.Popen(
        [
            binary_path,
            "--storage-path", storage_path,
            "--port", str(port),
            "--grpc-port", str(port + 1),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    logger.info(f"Qdrant sidecar starting on port {port} (pid={proc.pid})")

    if not _wait_for_ready(port):
        proc.terminate()
        raise RuntimeError(f"Qdrant sidecar did not become ready on port {port} within 15s")

    logger.info(f"Qdrant sidecar ready on port {port}")
    return proc, port


def stop_qdrant_sidecar(proc: subprocess.Popen) -> None:
    """Gracefully terminate the Qdrant sidecar process."""
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        logger.info("Qdrant sidecar stopped")
