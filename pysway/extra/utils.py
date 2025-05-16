from pysway.ipc import SwayIPC
from typing import Dict, Any, Optional, List


class Utils:
    def __init__(self):
        self._sock = SwayIPC()
        pass

    def show_desktop(self, output_id: int) -> None:
        """
        Toggle minimize state of all views in the current workspace of the specified output.
        Uses only get_output(..., key="current_workspace") and get_output(..., key="nodes").

        Args:
            output_id (int): ID of the output
        """
        # Step 1: Get current workspace ID
        workspace_id = self._sock.get_output(output_id, key="current_workspace")
        if not workspace_id:
            print(f"Output {output_id} has no current workspace")
            return

        # Step 2: Get all nodes from the output
        output_nodes = self._sock.get_output(output_id, key="nodes")
        if not output_nodes:
            print(f"No nodes found on output {output_id}")
            return

        # Step 3: Find the workspace node among output nodes
        workspace_node = None
        for node in output_nodes:
            if isinstance(node, dict) and node.get("type") == "workspace":
                if node.get("id") == workspace_id:
                    workspace_node = node
                    break

        if not workspace_node:
            print(f"Workspace {workspace_id} not found in output {output_id}")
            return

        # Step 4: Get all views in the workspace's nodes
        workspace_views = [
            node
            for node in workspace_node.get("nodes", [])
            if isinstance(node, dict) and node.get("type") in ["con", "floating_con"]
        ]

        if not workspace_views:
            print(f"No views found in workspace {workspace_id}")
            return

        # Step 5: Determine action: minimize or restore
        should_minimize = not all(
            view.get("minimized", False) for view in workspace_views
        )

        # Step 6: Send commands based on view type
        for view in workspace_views:
            view_id = view["id"]
            if self._sock.is_xwayland_view(view):
                self._sock._send(
                    0,
                    f"[id={view_id}] minimize {'enable' if should_minimize else 'disable'}",
                )
            else:
                self._sock._send(
                    0,
                    f"[con_id={view_id}] minimize {'enable' if should_minimize else 'disable'}",
                )

    def get_output_by_name(self, name) -> Optional[Dict[str, Any]]:
        """Find output by its name (e.g., 'DP-1')"""
        outputs = self._sock.list_outputs()
        if outputs:
            for output in outputs:
                if output.get("name") == name:
                    return output
            return None
