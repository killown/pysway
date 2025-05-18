from typing import Dict, Any, Optional, List
from itertools import islice, cycle

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
BIND_INPUT = 102


class SwayUtils:
    def __init__(self, socket):
        self._sock = socket
        self.floating_views = {}

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

    def get_next_workspace_with_views(self) -> Optional[str]:
        workspaces = self.get_workspaces_from_focused_output()
        if not workspaces:
            return None

        seen = set()
        non_empty_names = []

        for ws in workspaces:
            name = ws["name"]
            if name in seen:
                continue
            seen.add(name)

            for node in ws.get("nodes", []):
                if isinstance(node, dict) and node.get("type") in [
                    "con",
                    "floating_con",
                ]:
                    non_empty_names.append(name)
                    break

        if not non_empty_names:
            return None

        current_workspace = self.get_focused_workspace()
        if not current_workspace:
            return non_empty_names[0]

        try:
            current_idx = non_empty_names.index(current_workspace["name"])
        except ValueError:
            return non_empty_names[0]

        next_idx = (current_idx + 1) % len(non_empty_names)
        return non_empty_names[next_idx]

    def go_next_workspace_with_views(self) -> None:
        """
        Switch to the next workspace with views using workspace IDs.
        Only considers non-empty workspaces and respects Sway's natural order.
        """
        workspace_name = self.get_next_workspace_with_views()
        if workspace_name is None:
            return
        self._sock.run_command(f"workspace {workspace_name}")

    def move_view_to_workspace(self, view_id: int, workspace_name: str) -> bool:
        view = self._sock.get_view(view_id)
        if not view:
            print(f"View {view_id} not found")
            return False

        if self._sock.is_xwayland_view(view):
            selector = f"[id={view_id}]"
        else:
            selector = f"[con_id={view_id}]"

        try:
            self._sock._send(0, f"{selector} move workspace {workspace_name}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to move view {view_id}: {e}")
            return False

    def move_view_to_new_empty_workspace(self, view_id: int) -> bool:
        """
        Moves the specified view to a new or existing empty workspace named after its PID.

        Args:
            view_id (int): The internal Sway ID of the view to move.

        Returns:
            bool: True if successful, False otherwise.
        """
        # Get the view data
        view = self._sock.get_view(view_id)
        if not view:
            print(f"[ERROR] View {view_id} not found.")
            return False

        # Determine selector based on view type
        if self._sock.is_xwayland_view(view):
            selector = f"[id={view_id}]"
        else:
            selector = f"[con_id={view_id}]"

        # Get the view's PID
        pid = view.get("pid")
        if not pid or not isinstance(pid, int):
            print(
                f"[WARNING] View {view_id} has no valid PID. Using fallback workspace name."
            )
            workspace_name = "unknown"
        else:
            workspace_name = str(pid)

        # Check if the target workspace already exists
        existing_workspaces = self.get_workspaces_from_focused_output()
        workspace_names = [ws["name"] for ws in existing_workspaces]

        if workspace_name not in workspace_names:
            try:
                # Create the new workspace
                self._sock.run_command(f"workspace {workspace_name}")
                print(f"[INFO] Created new workspace '{workspace_name}'")
            except Exception as e:
                print(f"[ERROR] Failed to create workspace '{workspace_name}': {e}")
                return False

        # Move the view to the target workspace
        try:
            success = self.move_view_to_workspace(view_id, workspace_name)
            if success:
                print(
                    f"[INFO] Successfully moved view {view_id} to workspace '{workspace_name}'"
                )
            else:
                print(
                    f"[ERROR] Failed to move view {view_id} to workspace '{workspace_name}'"
                )
            return success
        except Exception as e:
            print(f"[ERROR] Unexpected error while moving view {view_id}: {e}")
            return False

    def bind_input(self, identifier: str, command: str, import_str=None) -> None:
        """
        Bind a key or mouse button to a Sway command at runtime.
        To call a Python function, wrap it in `exec python3 -c ...`.
        """
        if import_str is None:
            import_str = """from pysway.ipc import SwayIPC;\
                            from pysway.extra.utils import SwayUtils;\
                            sock = SwayIPC();\
                            utils = SwayUtils(sock);\
                          """.strip()
        payload = f'{identifier} exec python3 -c "{import_str}{command}"'
        print(payload)
        self._sock._send(BIND_INPUT, payload)

    def go_next_view_in_workspace(self):
        """
        Switch focus to the next view in the current workspace.
        Only considers top-level views (not scratchpad/minimized/etc).
        """
        views = None
        focused_workspace = self.get_focused_workspace()
        if focused_workspace is None:
            return
        views = focused_workspace["nodes"]

        if not views:
            if "floating_nodes" in focused_workspace:
                views = focused_workspace["floating_nodes"]

        if len(views) <= 1:
            return  # No need to switch if there's only one view

        focused_id = self._sock.get_focused_view()["id"]
        try:
            idx = next(i for i, v in enumerate(views) if v["id"] == focused_id)
            next_idx = (idx + 1) % len(views)
            next_view = views[next_idx]
            if self._sock.is_xwayland_view(next_view):
                self._sock.run_command(f"[id={next_view['id']}] focus")
            else:
                self._sock.run_command(f"[con_id={next_view['id']}] focus")
        except StopIteration:
            # Fallback: just focus any view
            if views:
                v = views[0]
                selector = (
                    "[id={}]".format(v["id"])
                    if self._sock.is_xwayland_view(v)
                    else "[con_id={}]".format(v["id"])
                )
                self._sock.run_command(f"{selector} focus")

    def maximize_view(self, view_id: int) -> bool:
        """
        Maximize a view to fill the entire current workspace area.

        Args:
            view_id (int): The internal ID of the view to maximize.

        Returns:
            bool: True if successful, False otherwise.
        """
        # Get the focused workspace's geometry
        workspace = self.get_focused_workspace()
        if not workspace:
            print("[ERROR] Could not find focused workspace.")
            return False

        rect = workspace.get("rect")
        if not rect:
            print("[ERROR] Focused workspace has no 'rect' property.")
            return False

        width = rect.get("width", 1920)
        height = rect.get("height", 1080)

        # Enable floating mode before resizing
        view = self._sock.get_view(view_id)
        if not view:
            print(f"[ERROR] View with ID {view_id} not found.")
            return False

        try:
            if self._sock.is_xwayland_view(view):
                selector = f"[id={view_id}]"
            else:
                selector = f"[con_id={view_id}]"

            self._sock.run_command(f"{selector} floating enable")

            # Resize and reposition the view to fill the workspace
            success = self._sock.configure_view(
                view_id=view_id, x=0, y=0, w=width, h=height
            )

            if success:
                print(f"[INFO] Successfully maximized view {view_id}.")
            else:
                print(f"[ERROR] Failed to maximize view {view_id}.")

            return success

        except Exception as e:
            print(f"[ERROR] Failed to maximize view {view_id}: {e}")
            return False
