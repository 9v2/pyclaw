"""Desktop automation tools."""

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from pyclaw.agent.tools import Tool, ToolResult
from pyclaw.agent.session import Session


class TakeScreenshotTool(Tool):
    """Take a screenshot of the user's entire screen."""

    def __init__(self, session: Optional[Session] = None) -> None:
        super().__init__(
            name="take_screenshot",
            description=(
                "Take a full-screen screenshot and show it in the chat. "
                "Useful when the user asks you to look at their screen."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "delay": {
                        "type": "integer",
                        "description": "Delay in seconds before taking screenshot. Default 0.",
                    }
                },
                "required": [],
            }
        )
        self.session = session
        self.requires_confirmation = False

    def bind_session(self, session: Session) -> None:
        """Bind the active session to inject the screenshot."""
        self.session = session

    async def run(self, delay: int = 0) -> ToolResult:
        """Take a screenshot using scrot or gnome-screenshot."""
        tool = "scrot"
        if not shutil.which("scrot"):
             tool = "gnome-screenshot"
             if not shutil.which("gnome-screenshot"):
                 return ToolResult(
                     error="Neither `scrot` nor `gnome-screenshot` found. "
                           "Please ask the user to install `scrot`."
                 )

        if not self.session:
            return ToolResult(error="No active session to display image in.")

        # Create temp file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            path = tf.name
        # Close handle so subprocess can write
        # NamedTemporaryFile deletes on close by default if not delete=False? 
        # delete=False is set above.

        cmd = []
        if tool == "scrot":
            cmd = ["scrot", path, "--overwrite"]
            if delay > 0:
                cmd.extend(["--delay", str(delay)])
        elif tool == "gnome-screenshot":
            cmd = ["gnome-screenshot", "-f", path]
            if delay > 0:
                cmd.extend(["-d", str(delay)])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return ToolResult(error=f"Screenshot failed: {stderr.decode().strip()}")

            # Read bytes
            p = Path(path)
            if not p.exists() or p.stat().st_size == 0:
                return ToolResult(error="Screenshot file empty or missing.")

            data = p.read_bytes()
            
            # Inject into session
            # We add it as a user message part so the model sees it in history
            self.session.add_image("user", data, "image/png", "Screenshot of my screen")
            
            # Cleanup
            p.unlink(missing_ok=True)
            
            return ToolResult(
                result="Screenshot captured and added to conversation. "
                       "You can now see the user's screen."
            )

        except Exception as e:
            return ToolResult(error=f"Failed to take screenshot: {e}")
