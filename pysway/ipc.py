import socket
import struct
import json
from typing import Dict, Any, Optional, List
import os

# Message type from sway IPC docs
GET_TREE = 4


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

    def send(self, msg_type: int, payload="") -> None:
        payload_bytes = payload.encode("utf-8")
        header = struct.pack("=6sII", b"i3-ipc", len(payload_bytes), msg_type)
        self.sock.sendall(header + payload_bytes)

    def recv(self) -> Optional[Dict[str, Any]]:
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
        self.send(GET_TREE)
        return self.recv()

    def list_views(self, tree: Dict[str, Any]) -> List[Dict[str, Any]]:
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

    def get_focused_output(self, key=None) -> Optional[Dict[str, Any]]:
        """Get info about the currently focused output."""
        tree = self.get_tree()

        def traverse(node) -> Optional[Dict[str, Any]]:
            if isinstance(node, dict):
                if node.get("focused"):
                    return node
                for child in node.get("nodes", []):
                    result = traverse(child)
                    if result:
                        return result
            return None

        focused_node = traverse(tree)
        if not focused_node:
            return None

        # Traverse again to find corresponding output
        while focused_node.get("type") != "output":
            parent = focused_node.get("parent")
            if not parent:
                return None
            focused_node = parent

        return focused_node if key is None else focused_node.get(key)
