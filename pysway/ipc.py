import socket
import struct
import json
from typing import Dict, Any, Optional, List
import os

# Message type from sway IPC docs
RUN_COMMAND = 0
GET_WORKSPACES = 1
SUBSCRIBE = 2
GET_OUTPUTS = 3
GET_TREE = 4
GET_MARKS = 5
GET_BAR_CONFIG = 6
GET_VERSION = 7
GET_BINDING_MODES = 8
GET_CONFIG = 9
SEND_TICK = 10
SYNC = 11
GET_BINDING_STATE = 12
GET_INPUTS = 100
GET_SEATS = 101


class SwayIPC:
    def __init__(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._connect()

    def _find_socket(self):
        swaysock = os.getenv("SWAYSOCK")
        if swaysock and os.path.exists(swaysock):
            return swaysock
        raise RuntimeError("Not running inside a Sway session")

    def _connect(self) -> None:
        self.sock.connect(self._find_socket())

    def _send(self, msg_type: int, payload="") -> None:
        payload_bytes = payload.encode("utf-8")
        header = struct.pack("=6sII", b"i3-ipc", len(payload_bytes), msg_type)
        self.sock.sendall(header + payload_bytes)

    def read_next_event(self) -> Optional[Dict[str, Any]]:
        """
        Read a single event from the IPC socket.

        Returns:
            Optional[Dict]: An event dictionary or None on failure.
        """
        return self._recv()

    def _recv(self) -> Optional[Dict[str, Any]]:
        buffer = b""
        while len(buffer) < 14:
            chunk = self.sock.recv(14 - len(buffer))
            if not chunk:
                return None
            buffer += chunk
        magic, length, msg_type = struct.unpack("=6sII", buffer[:14])
        if magic != b"i3-ipc":
            raise ValueError("Invalid IPC magic")
        while len(buffer) < 14 + length:
            chunk = self.sock.recv(length + 14 - len(buffer))
            if not chunk:
                return None
            buffer += chunk

        try:
            data = json.loads(buffer[14 : 14 + length])
            return data
        except json.JSONDecodeError:
            return None

    def is_connected(self) -> bool:
        """
        Check if the Sway socket is still connected.
        Sends zero-byte data to check if the connection is alive.
        """
        try:
            # Try to send 0 bytes (doesn't block or send real data)
            self.sock.send(b"")
            return True
        except OSError:
            return False

    def is_xwayland_view(self, view: Dict[str, Any]) -> bool:
        """
        Determine if a view is an XWayland client

        Args:
            view (dict): A node from the sway tree

        Returns:
            bool: True if XWayland, False otherwise
        """
        return view.get("shell") == "xwayland"

    def get_tree(self) -> Optional[Dict[str, Any]]:
        self._send(GET_TREE)
        return self._recv()

    def run_command(self, cmd: str) -> None:
        """
        Run a raw Sway command via IPC.
        """
        self._send(0, cmd)

    def list_seats(self) -> Optional[Dict[str, Any]]:
        """
        Get list of available seats with their capabilities.

        Returns:
            List of seat dictionaries or None if failed.
        """
        self._send(GET_SEATS)
        response = self._recv()
        return response

    def close(self) -> None:
        """Close the Sway IPC socket connection."""
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            # Socket may already be closed or disconnected
            pass
        finally:
            self.sock.close()

    def close_view(self, view_id: int) -> bool:
        """
        Close a view by its ID.

        Args:
            view_id (int): The numeric ID of the view to close

        Returns:
            bool: True if command was sent successfully, False otherwise
        """
        try:
            self._send(0, f"[id={view_id}] kill")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to close view {view_id}: {e}")
            return False

    def set_view_alpha(self, view_id: int, opacity: float) -> None:
        """
        Set the opacity of a view (0.0 = fully transparent, 1.0 = opaque)

        Args:
            view_id (int): ID of the view
            opacity (float): Opacity value between 0.0 and 1.0
        """
        if not (0.0 <= opacity <= 1.0):
            raise ValueError("Opacity must be between 0.0 and 1.0")
        self._send(0, f"[id={view_id}] opacity {opacity}")

    def set_workspace(
        self, x: int, y: int, view_id: Optional[int] = None
    ) -> Optional[bool]:
        tree = self.get_tree()
        if tree:
            outputs = [o for o in tree.get("nodes", []) if o.get("type") == "output"]

            for output in outputs:
                geometry = output.get("rect", {})
                ox = geometry.get("x", 0)
                oy = geometry.get("y", 0)
                width = geometry.get("width", 1920)
                height = geometry.get("height", 1080)

                # Check if point (x, y) is inside this output
                if ox <= x < ox + width and oy <= y < oy + height:
                    workspace = output.get("current_workspace")
                    if not workspace:
                        continue

                    if view_id is None:
                        return self._send(0, f"workspace {workspace}")
                    else:
                        return self._send(
                            0, f"[id={view_id}] move workspace {workspace}"
                        )

            return False

    def configure_view(
        self,
        view_id: int,
        x: int,
        y: int,
        w: int,
        h: int,
        output_id: Optional[int] = None,
    ) -> bool:
        """
        Configure a view's position and size, handling both Wayland and XWayland views

        Args:
            view_id (int): The internal ID of the view
            x (int): X coordinate
            y (int): Y coordinate
            w (int): Width
            h (int): Height
            output_id (Optional[int]): Output ID to move to

        Returns:
            bool: True if successful
        """
        view = self.get_view(view_id)
        if not view:
            print(f"View {view_id} not found")
            return False

        if self.is_xwayland_view(view):
            selector = f"[id={view_id}]"
        else:
            selector = f"[con_id={view_id}]"

        try:
            # Optionally move to a specific output first
            if output_id is not None:
                self._send(0, f"{selector} move to output id {output_id}")

            # Set absolute position and size
            self._send(0, f"{selector} floating enable")

            # skip moving the view
            if x > 0 or y > 0:
                self._send(0, f"{selector} move position {x} {y}")

            self._send(0, f"{selector} resize set {w} {h}")

            return True
        except Exception as e:
            print(f"[ERROR] Failed to configure view {view_id}: {e}")
            return False

    def list_input_devices(self) -> Optional[Dict[str, Any]]:
        """
        Get list of available inputs with their capabilities.

        Returns:
            List of input dictionaries or None if failed.
        """
        self._send(GET_INPUTS)
        response = self._recv()
        return response

    def list_views(self) -> List[Dict[str, Any]]:
        """Extract all views with titles and app_ids"""
        views = []

        def traverse(node) -> Optional[Dict[str, Any]]:
            if isinstance(node, dict):
                # Real view condition based on sway's IPC tree
                if node.get("type") in ["con", "floating_con"]:
                    if node.get("id"):
                        views.append(node)
                for child in node.get("nodes", []) + node.get("floating_nodes", []):
                    traverse(child)

        tree = self.get_tree()
        traverse(tree)
        return views

    def get_view(self, view_id: int, max_retries=10) -> Optional[Dict[str, Any]]:
        """
        Get a view by ID with retry logic to handle async updates

        Args:
            view_id (int): ID of the view to find
            max_retries (int): Maximum number of times to try
            delay (float): Time to wait between retries

        Returns:
            Optional[Dict]: View data if found, None otherwise
        """
        # for some reason sway doesn't always return the view when using get_tree
        # this is a temporary solution to make it always return the view
        for attempt in range(max_retries):
            tree = self.get_tree()
            if not tree:
                continue

            def traverse(node):
                if isinstance(node, dict):
                    if node.get("id") == view_id:
                        return node
                    for child in node.get("nodes", []) + node.get("floating_nodes", []):
                        result = traverse(child)
                        if result:
                            return result
                return None

            result = traverse(tree)
            if result:
                return result

        return None

    def get_focused_view(self) -> Optional[Dict[str, Any]]:
        tree = self.get_tree()

        def traverse(node):
            if isinstance(node, dict):
                if node.get("focused"):
                    return node
                for child in node.get("nodes", []) + node.get("floating_nodes", []):
                    result = traverse(child)
                    if result:
                        return result
            return None

        return traverse(tree)

    def get_output(self, output_id: int, key=None) -> Optional[Dict[str, Any]]:
        """Get info about a specific output by ID."""
        tree = self.get_tree()
        if tree:
            outputs = [
                node for node in tree.get("nodes", []) if node.get("type") == "output"
            ]

            for output in outputs:
                if output.get("id") == output_id:
                    return output if key is None else output.get(key)
        return None

    def get_focused_output(self):
        """Find the output of the currently focused container"""
        tree = self.get_tree()

        def find_focused_node(node):
            if isinstance(node, dict):
                if node.get("focused"):
                    return node
                for child in node.get("nodes", []) + node.get("floating_nodes", []):
                    result = find_focused_node(child)
                    if result:
                        return result
            return None

        focused_node = find_focused_node(tree)
        if not focused_node:
            return None

        # Traverse upward until we reach the output
        while focused_node.get("type") != "output":
            parent = focused_node.get("parent")
            if not parent:
                return None
            focused_node = parent

        return focused_node

    def list_outputs(self) -> Optional[List[Dict[str, Any]]]:
        """List all outputs (outputs are top-level nodes with type == 'output')"""
        tree = self.get_tree()
        return [node for node in tree.get("nodes", []) if node.get("type") == "output"]

    def focus_output(self, output_id) -> None:
        """Focus an output by ID using Sway command"""
        self._send(0, f"[id={output_id}] focus")

    def set_view_minimized(self, view_id: int, state: bool) -> None:
        """
        Set the minimized state of a view

        Args:
            view_id (int): ID of the view to modify
            state (bool): True to minimize, False to unminimize
        """
        action = "enable" if state else "disable"
        self._send(0, f"[id={view_id}] minimize {action}")

    def set_view_maximized(self, view_id: int, state: bool) -> None:
        """
        Set the maximized state of a view

        Args:
            view_id (int): ID of the view to modify
            state (bool): True to maximize, False to restore
        """
        action = "enable" if state else "disable"
        self._send(0, f"[id={view_id}] maximize {action}")

    def set_view_fullscreen(self, view_id: int, state: bool) -> None:
        """
        Set the fullscreen state of a view

        Args:
            view_id (int): ID of the view to modify
            state (bool): True to enter fullscreen, False to exit
        """
        action = "enable" if state else "disable"
        self._send(0, f"[id={view_id}] fullscreen {action}")

    def set_view_focus(self, view_id: int) -> None:
        """
        Set focus to a specific view by its ID

        Args:
            view_id (int): The numeric ID of the view to focus
        """
        try:
            self._send(0, f"[id={view_id}] focus")
        except Exception as e:
            print(f"[ERROR] Failed to focus view {view_id}: {e}")

    def watch(self, events=None):
        """
        Subscribe to one or more event types.
        If no events are specified, subscribes to all available events.

        Valid event types: workspace, window, output, mode, barconfig_update, binding, shutdown, tick, bar_state_update, input
        """
        valid_events = [
            "workspace",
            "window",
            "output",
            "mode",
            "barconfig_update",
            "binding",
            "shutdown",
            "tick",
            "bar_state_update",
            "input",
        ]
        if events is None:
            events = valid_events  # Watch all events by default
        else:
            # Validate provided events
            invalid = [e for e in events if e not in valid_events]
            if invalid:
                raise ValueError(
                    f"Invalid event(s): {', '.join(invalid)}. "
                    f"Valid events: {', '.join(valid_events)}"
                )

        payload = json.dumps(events)
        self._send(SUBSCRIBE, payload)

        response = self._recv()
        if isinstance(response, dict) and response.get("success", False):
            print(f"Watching events: {', '.join(events)}\n{'-' * 40}")
            return True
        else:
            raise RuntimeError("Failed to subscribe to Sway events.")
