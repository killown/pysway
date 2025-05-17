from pysway.ipc import SwayIPC
from typing import Dict, Any, Optional, List
from itertools import islice, cycle


class Utils:
    def __init__(self):
        self._sock = SwayIPC()

    def show_desktop(self, output_id: int) -> None:
        """
        Toggle visibility of all views in the current workspace of the specified output.
        If any view is visible (not in scratchpad), move all to scratchpad (minimize).
        If all are already in scratchpad, restore them.

        Args:
            output_id (int): ID of the output
        """
        # Step 1: Get current workspace info for the given output
        workspace_info = self._sock.get_output(output_id, key="current_workspace")
        if not workspace_info:
            print(f"Output {output_id} has no current workspace")
            return

        # Step 2: Get all nodes from the output
        output_nodes = self._sock.get_output(output_id, key="nodes")
        if not isinstance(output_nodes, list):
            print(f"Expected list for output nodes, got {type(output_nodes)}")
            return

        # Step 3: Find the workspace node among output nodes
        workspace_node = None
        for node in output_nodes:
            if isinstance(node, dict) and node.get("type") == "workspace":
                if node.get("name") == workspace_info:
                    workspace_node = node
                    break

        if not workspace_node:
            print(f"Workspace {workspace_info} not found in output {output_id}")
            return

        # Step 4: Extract views from the workspace
        workspace_views = [
            node
            for node in workspace_node.get("nodes", [])
            if isinstance(node, dict) and node.get("type") in ["con", "floating_con"]
        ]

        if not workspace_views:
            print(f"No views found in workspace {workspace_info}")
            return

        # Step 5: Determine action based on scratchpad state (only for current workspace views)
        all_in_scratchpad = all(
            view.get("scratchpad_state") == "fresh" for view in workspace_views
        )

        # Step 6: Apply action
        for view in workspace_views:
            view_id = view["id"]

            # Use [id=] for XWayland, [con_id=] for Wayland
            if self._sock.is_xwayland_view(view):
                selector = f"[id={view_id}]"
            else:
                selector = f"[con_id={view_id}]"

            if all_in_scratchpad:
                # Restore from scratchpad
                self._sock._send(0, f"{selector} scratchpad show")
            else:
                # Move to scratchpad
                self._sock._send(0, f"{selector} move scratchpad")

    def get_workspace_with_views(self) -> List[Dict[str, Any]]:
        """
        Get all workspaces that contain at least one view (window).

        Returns:
            List of workspace dictionaries that have visible views
        """
        tree = self._sock.get_tree()
        if not tree:
            return []

        result = []

        def traverse(node):
            if not isinstance(node, dict):
                return

            if node.get("type") == "workspace":
                # Extract only immediate child views
                views = [
                    child
                    for child in node.get("nodes", [])
                    if isinstance(child, dict)
                    and child.get("type") in ["con", "floating_con"]
                ]
                if views:
                    result.append({"workspace": node, "views": views})
            elif node.get("nodes") or node.get("floating_nodes"):
                for child in node.get("nodes", []) + node.get("floating_nodes", []):
                    traverse(child)

        traverse(tree)
        return result

    def get_views_from_workspace(self, workspace_number: int) -> List[Dict[str, Any]]:
        """
        Get all views from a specific workspace by its ID.

        Args:
            workspace_number (int): The numeric ID of the workspace

        Returns:
            List of view dictionaries from the specified workspace
        """
        tree = self._sock.get_tree()
        if not tree:
            return []

        # Find the workspace node
        workspace_node = None

        def find_workspace(node):
            nonlocal workspace_node
            if isinstance(node, dict):
                if (
                    node.get("type") == "workspace"
                    and node.get("id") == workspace_number
                ):
                    workspace_node = node
                    return
                for child in node.get("nodes", []) + node.get("floating_nodes", []):
                    find_workspace(child)

        find_workspace(tree)

        if not workspace_node:
            return []

        # Extract views from the workspace
        views = [
            node
            for node in workspace_node.get("nodes", [])
            if isinstance(node, dict) and node.get("type") in ["con", "floating_con"]
        ]

        return views

    def get_workspaces_from_focused_output(self) -> List[Dict[str, Any]]:
        """
        Get all workspaces from the currently focused output.

        Returns:
            List of workspace dictionaries from the focused output
        """
        # Step 1: Get focused output ID
        focused_output_id = self._sock.get_focused_output()
        if not isinstance(focused_output_id, int):
            print("Focused output ID is not an integer")
            return []

        # Step 2: Get output node by ID
        output_node = self._sock.get_output(focused_output_id)
        if not output_node:
            print(f"Failed to get output with ID {focused_output_id}")
            return []

        # Step 3: Extract only workspace nodes
        workspaces = [
            node
            for node in output_node.get("nodes", [])
            if isinstance(node, dict) and node.get("type") == "workspace"
        ]

        if not workspaces:
            print(f"No workspaces found on output {focused_output_id}")

        return workspaces

    def get_focused_workspace(self) -> Optional[Dict[str, Any]]:
        """
        Get the currently focused workspace from the focused output.

        Returns:
            Optional[Dict]: The focused workspace dictionary, or None if not found.
        """
        focused_output_id = self._sock.get_focused_output()
        if not isinstance(focused_output_id, int):
            return None

        # Step 2: Get full output node
        output_node = self._sock.get_output(focused_output_id)
        if not output_node:
            return None

        # Step 3: Get current workspace name
        current_workspace_name = output_node.get("current_workspace")
        if not current_workspace_name:
            return None

        # Step 4: Find the matching workspace node
        for node in self.get_workspaces_from_focused_output():
            if (
                node.get("type") == "workspace"
                and node.get("name") == current_workspace_name
            ):
                return node

        return None

    def get_output_by_name(self, name) -> Optional[Dict[str, Any]]:
        """Find output by its name (e.g., 'DP-1')"""
        outputs = self._sock.list_outputs()
        if outputs:
            for output in outputs:
                if output.get("name") == name:
                    return output
            return None

    def get_next_workspace_with_views(self) -> Optional[int]:
        """
        Get the next non-empty workspace ID from the currently focused output.
        Returns:
            Optional[int]: The ID of the next workspace with views, or None if none found.
        """

        # Step 1: Get all workspaces from focused output
        workspaces = self.get_workspaces_from_focused_output()
        if not workspaces:
            return None

        # Step 2: Filter only workspaces with views
        def has_view(workspace):
            for node in workspace.get("nodes", []):
                if isinstance(node, dict) and node.get("type") in [
                    "con",
                    "floating_con",
                ]:
                    return True
            return False

        non_empty_ids = [ws["id"] for ws in workspaces if has_view(ws)]
        if not non_empty_ids:
            return None

        # Step 3: Get current workspace ID
        current_workspace = self.get_focused_workspace()
        if not current_workspace:
            return non_empty_ids[0]  # fallback to first if can't detect current

        try:
            current_idx = non_empty_ids.index(current_workspace["id"])
        except ValueError:
            return non_empty_ids[0]  # fallback if current not in list

        # Step 4: Create circular iterator starting after current
        circular_iter = islice(cycle(non_empty_ids), current_idx + 1, None)

        # Step 5: Return next valid workspace ID
        for wid in circular_iter:
            return wid  # returns first match (next in line)

        return None  # should never happen unless list is empty

    def go_next_workspace_with_views(self) -> None:
        """
        Switch to the next workspace with views using workspace IDs.
        Only considers non-empty workspaces and respects Sway's natural order.
        """
        workspace_id = self.get_next_workspace_with_views()
        print(workspace_id)
        if workspace_id is None:
            return
        self._sock.run_command(f"workspace ID {workspace_id}")
