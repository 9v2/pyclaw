"""Gateway process manager — PID-based start/stop/restart.

Manages the Telegram gateway as a background daemon process using
PID files for lifecycle control.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

_PID_FILE = Path.home() / ".pyclaw" / "gateway.pid"
_LOG_FILE = Path.home() / ".pyclaw" / "gateway.log"


class GatewayManager:
    """Manages the gateway background process."""

    __slots__ = ()

    @staticmethod
    def is_running() -> bool:
        """Check if the gateway process is alive."""
        pid = GatewayManager._read_pid()
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            # Stale PID file — clean it up
            _PID_FILE.unlink(missing_ok=True)
            return False

    @staticmethod
    def get_pid() -> int | None:
        """Get the gateway PID if running."""
        if GatewayManager.is_running():
            return GatewayManager._read_pid()
        return None

    @staticmethod
    def start() -> tuple[bool, str]:
        """Start the gateway as a background process.

        Returns (success, message).
        """
        if GatewayManager.is_running():
            return False, "gateway is already running"

        # Ensure no orphans exist
        GatewayManager._cleanup_orphans()

        _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Launch the gateway runner script as a detached subprocess
        log_fd = open(_LOG_FILE, "a")
        proc = subprocess.Popen(
            [sys.executable, "-m", "pyclaw.gateway._runner"],
            stdout=log_fd,
            stderr=log_fd,
            start_new_session=True,
        )

        # Write PID
        _PID_FILE.write_text(str(proc.pid))
        return True, f"gateway started (pid {proc.pid})"

    @staticmethod
    def stop() -> tuple[bool, str]:
        """Stop the gateway process.

        Returns (success, message).
        """
        pid = GatewayManager._read_pid()
        # Even if PID file missing, try to cleanup orphans if requested by user context?
        # But here we stick to regular flow. 
        # If PID missing, we return False usually.
        # But to be robust, we should run cleanup if user says 'stop'.
        
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                # Wait for process to exit
                import time
                for _ in range(30):  # 3 seconds timeout
                    try:
                        os.kill(pid, 0)
                        time.sleep(0.1)
                    except OSError:
                        break
            except (OSError, ProcessLookupError):
                pass

        # Robust cleanup
        GatewayManager._cleanup_orphans()

        _PID_FILE.unlink(missing_ok=True)
        
        if pid:
            return True, f"gateway stopped (pid {pid})"
        # If no PID but we ran cleanup, say stopped?
        return True, "gateway stopped (cleaned up)"

    @staticmethod
    def restart() -> tuple[bool, str]:
        """Restart the gateway."""
        was_running = GatewayManager.is_running()
        if was_running:
            GatewayManager.stop()

        ok, msg = GatewayManager.start()
        if ok:
            return True, "gateway restarted" if was_running else msg
        return ok, msg

    @staticmethod
    def log_path() -> Path:
        return _LOG_FILE

    @staticmethod
    def pid_path() -> Path:
        return _PID_FILE

    @staticmethod
    def _cleanup_orphans() -> None:
        """Kill any lingering gateway processes."""
        try:
             subprocess.run(["pkill", "-f", "pyclaw.gateway._runner"], capture_output=True)
             import time
             time.sleep(0.5)
        except Exception:
             pass

    # ── Internals ───────────────────────────────────────────────────

    @staticmethod
    def _read_pid() -> int | None:
        if not _PID_FILE.exists():
            return None
        try:
            return int(_PID_FILE.read_text().strip())
        except (ValueError, OSError):
            return None
