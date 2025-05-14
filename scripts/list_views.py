from pysway.ipc import SwayIPC

ipc = SwayIPC()
tree = ipc.get_tree()
views = ipc.list_views(tree)

print("Open Views:")
print("-" * 60)
if not views:
    print("No open views found.")
else:
    for v in views:
        print(v)
        print(f"ID: {v['id']}")
        print(f"Title: {v['name']}")
        print(f"App ID: {v['app_id'] or 'Unknown'}")
        print(f"PID: {v['pid']}")
        print("-" * 60)
