 # Sway IPC Python Library 

pysway
======

A Python library to interact with the [Sway](https://swaywm.org ) window manager via its IPC interface.

📦 Features
-----------

*   Query the current layout tree of Sway.
*   Get information about views (windows), outputs, inputs, and seats.
*   Run Sway commands programmatically.
*   Subscribe to real-time events like workspace changes, view focus, output updates, and more.

🧰 Requirements
---------------

*   Python 3.6+
*   Running inside a **Sway session**


🚀 Installation
---------------
install from source:

    git clone https://github.com/yourusername/pysway.git 
    cd pysway
    pip install -e .

🔌 Usage Examples
-----------------

### 🖥️ Get the Current Layout Tree

    from pysway.ipc import SwayIPC
    
    sway = SwayIPC()
    tree = sway.get_tree()
    print(tree)

### 👁️ Get Focused View

    focused = sway.get_focused_view()
    if focused:
        print(f"Focused View ID: {focused['id']}")
        print(f"Title: {focused.get('name')}")
    

### 📺 List All Views

    views = sway.list_views()
    for v in views:
        print(f"ID: {v['id']}, Title: {v['name']}, App ID: {v.get('app_id', 'N/A')}")

### 🎮 Monitor Real-Time Events

Run the built-in event monitor:

    python -m scripts.event_monitor

Or use it in code:

    from scripts.event_monitor import SwayIPC
    
    ipc = SwayIPC()
    ipc.subscribe(["workspace", "window"])  # or ipc.subscribe() to watch all events
    
    while True:
        event = ipc.read_next_event()
        if event:
            print("Event received:", event)

🛠️ Supported Commands
----------------------

Method

Description

`get_tree()`

Get full layout tree

`get_focused_view()`

Get currently focused window

`list_views()`

List all open views

`run_command(cmd)`

Execute raw Sway command

`list_outputs()`

List connected displays

`focus_output(id)`

Focus an output by ID

`subscribe(events)`

Subscribe to one or more IPC events

📬 Event Types
--------------

You can subscribe to these event types:

*   `workspace`
*   `window`
*   `output`
*   `mode`
*   `barconfig_update`
*   `binding`
*   `shutdown`
*   `tick`
*   `bar_state_update`
*   `input`

🤝 Contributing
---------------

Contributions are welcome! Please read our contribution guidelines before submitting a PR.

📜 License
----------

This project is licensed under the MIT License.
