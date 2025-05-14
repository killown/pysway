import socket
import struct
import json
from typing import Dict, Any, Optional, List
import os

# Message type from sway IPC docs
GET_TREE = 4
GET_SEATS = 101
GET_INPUTS = 100


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

        return json.loads(buffer[14 : 14 + length])

    def get_tree(self) -> Optional[Dict[str, Any]]:
        self._send(GET_TREE)
        return self._recv()

    # FIXME: move to stipc.py
    def run_command(self, cmd: str) -> None:
        """
        Run a raw Sway command via IPC.
        """
        self._send(0, cmd)

    # FIXME: move to stipc.py
    def list_seats(self) -> Optional[Dict[str, Any]]:
        """
        Get list of available seats with their capabilities.

        Returns:
            List of seat dictionaries or None if failed.
        """
        self._send(GET_SEATS)
        response = self._recv()
        return response

    # FIXME: move to stipc.py
    def list_inputs(self) -> Optional[Dict[str, Any]]:
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

    def get_view(self, view_id: int) -> Optional[Dict[str, Any]]:
        tree = self.get_tree()

        def traverse(node):
            if isinstance(node, dict):
                if node.get("id") == view_id:
                    return node
                for child in node.get("nodes", []) + node.get("floating_nodes", []):
                    result = traverse(child)
                    if result:
                        return result
            return None

        return traverse(tree)

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

    def get_output_by_name(self, name) -> Optional[Dict[str, Any]]:
        """Find output by its name (e.g., 'HDMI-A-1')"""
        outputs = self.list_outputs()
        for output in outputs:
            if output.get("name") == name:
                return output
        return None

    def focus_output(self, output_id) -> None:
        """Focus an output by ID using Sway command"""
        self._send(0, f"[id={output_id}] focus")
