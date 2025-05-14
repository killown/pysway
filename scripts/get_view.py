from pysway.ipc import SwayIPC
import json

sway = SwayIPC()
view = sway.get_view(8)  # Replace with real view ID

if view:
    print(json.dumps(view, indent=2))
else:
    print("View not found")
