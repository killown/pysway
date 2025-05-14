from pysway.ipc import SwayIPC

sway = SwayIPC()
focused = sway.get_focused_view()

if focused:
    print("Focused View:")
    print(f"ID: {focused['id']}")
    print(f"Title: {focused.get('name')}")
    print(f"App ID: {focused.get('app_id', 'N/A')}")
    print(f"PID: {focused.get('pid', 'Unknown')}")
else:
    print("No focused view found.")
