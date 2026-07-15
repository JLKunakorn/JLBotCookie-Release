"""Parent-side process manager for Premium multi-screen AutoFarm."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


class FarmWorker:
    def __init__(self, serial: str, process, event_callback, finished_callback):
        self.serial = serial
        self.process = process
        self._event_callback = event_callback
        self._finished_callback = finished_callback
        self._write_lock = threading.Lock()
        self._reader = threading.Thread(target=self._read_events, name=f"farm-reader-{serial}", daemon=True)

    def start_reader(self):
        self._reader.start()

    def _read_events(self):
        try:
            for line in self.process.stdout:
                try:
                    event = json.loads(line)
                except Exception:
                    event = {"event": "error", "message": "worker returned invalid output"}
                if isinstance(event, dict):
                    self._event_callback(self.serial, event)
        finally:
            exit_code = self.process.wait()
            self._finished_callback(self.serial, self, exit_code)

    def send(self, payload: dict) -> bool:
        if self.process.poll() is not None:
            return False
        try:
            with self._write_lock:
                self.process.stdin.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
                self.process.stdin.flush()
            return True
        except (BrokenPipeError, OSError, ValueError):
            return False

    def stop(self, force_after=2.0) -> bool:
        sent = self.send({"command": "stop"})
        if sent and force_after:
            timer = threading.Timer(float(force_after), self.terminate)
            timer.daemon = True
            timer.start()
        return sent

    def terminate(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()


class MultiFarmManager:
    def __init__(self, event_callback=None, popen_factory=None):
        self._event_callback = event_callback or (lambda serial, event: None)
        self._popen = popen_factory or subprocess.Popen
        self._workers: dict[str, FarmWorker] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _worker_command() -> list[str]:
        if getattr(sys, "frozen", False):
            return [sys.executable, "--premium-worker"]
        return [sys.executable, str(Path(__file__).resolve().with_name("premium_worker.py"))]

    def start(self, serial: str, key: str, adb_path: str, settings: dict, max_loops=0, mail_min_count=0) -> FarmWorker:
        serial = str(serial or "").strip()
        key = str(key or "").strip()
        if not serial:
            raise ValueError("emulator serial is required")
        if not key:
            raise ValueError("license key is required for this screen")
        with self._lock:
            current = self._workers.get(serial)
            if current is not None and current.process.poll() is None:
                raise RuntimeError("this screen is already running")
            process = self._popen(
                self._worker_command(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=_NO_WINDOW,
            )
            worker = FarmWorker(serial, process, self._event_callback, self._worker_finished)
            self._workers[serial] = worker
            config = {
                "serial": serial,
                "key": key,
                "adb_path": str(adb_path or "").strip(),
                "settings": dict(settings or {}),
                "max_loops": max(0, int(max_loops or 0)),
                "mail_min_count": max(0, int(mail_min_count or 0)),
            }
            if not worker.send(config):
                self._workers.pop(serial, None)
                worker.terminate()
                raise RuntimeError("could not start the screen worker")
            worker.start_reader()
            return worker

    def _worker_finished(self, serial: str, worker: FarmWorker, exit_code: int):
        with self._lock:
            if self._workers.get(serial) is worker:
                self._workers.pop(serial, None)
        self._event_callback(serial, {"event": "process_exit", "exit_code": exit_code})

    def stop(self, serial: str, force_after=2.0) -> bool:
        with self._lock:
            worker = self._workers.get(str(serial or "").strip())
        return bool(worker and worker.stop(force_after=force_after))

    def stop_all(self, force_after=2.0) -> None:
        with self._lock:
            workers = list(self._workers.values())
        for worker in workers:
            worker.stop(force_after=force_after)

    def terminate_all(self) -> None:
        with self._lock:
            workers = list(self._workers.values())
        for worker in workers:
            worker.terminate()

    def is_running(self, serial: str) -> bool:
        with self._lock:
            worker = self._workers.get(str(serial or "").strip())
            return bool(worker and worker.process.poll() is None)

    def any_running(self) -> bool:
        with self._lock:
            return any(worker.process.poll() is None for worker in self._workers.values())

    def running_serials(self) -> list[str]:
        with self._lock:
            return [serial for serial, worker in self._workers.items() if worker.process.poll() is None]
