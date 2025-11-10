import json
from typing import Any, Dict, List, Tuple

import streamlit as st

# --- Optional dependency: streamlit-vis-network (Bubble View)
try:
    from streamlit_vis_network import streamlit_vis_network  # type: ignore
    HAS_SVN = True
except Exception:
    HAS_SVN = False


# ------------------------------
# Helpers
# ------------------------------

def _truncate(s: str, max_len: int = 80) -> str:
    return (s[: max_len - 1] + "…") if len(s) > max_len else s


def _value_preview(v: Any) -> str:
    if isinstance(v, (int, float, bool)) or v is None:
        return json.dumps(v)
    if isinstance(v, str):
        return _truncate(v.replace("\n", " "))
    if isinstance(v, list):
        return f"[{len(v)}]"
    if isinstance(v, dict):
        return "{…}"
    return str(v)


def build_network(
    data: Any,
    *,
    show_values: bool = True,
    max_nodes: int = 1200,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool]:
    """Walk an arbitrary JSON-like structure and return vis-network nodes/edges.

    Returns: nodes, edges, truncated
    - node.id is a stable path (e.g. "root.items[0].name")
    - node.label is user-facing
    """
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    truncated = False

    def add_node(node_id: str, label: str, group: str) -> None:
        nonlocal truncated
        if len(nodes) >= max_nodes:
            truncated = True
            return
        nodes.append({"id": node_id, "label": label, "group": group})

    def walk(obj: Any, path: str, parent_id: str | None) -> None:
        nonlocal truncated
        if truncated:
            return

        # Determine label and group
        if isinstance(obj, dict):
            label = path.split(".")[-1] if path else "root"
            add_node(path or "root", f"{label} {{}}", "object")
            if parent_id:
                edges.append({"from": parent_id, "to": path or "root"})
            for k, v in obj.items():
                child_id = f"{path + '.' if path else ''}{k}"
                child_label = f"{k}: {_value_preview(v) if show_values else type(v).__name__}"
                # For containers, the child node itself will be added during recursion
                if not isinstance(v, (dict, list)):
                    add_node(child_id, child_label, "value")
                    edges.append({"from": path or "root", "to": child_id})
                walk(v, child_id, path or "root")
        elif isinstance(obj, list):
            label = path.split(".")[-1] if path else "root"
            add_node(path or "root", f"{label} [{len(obj)}]", "array")
            if parent_id:
                edges.append({"from": parent_id, "to": path or "root"})
            for i, v in enumerate(obj):
                child_id = f"{path}[{i}]" if path else f"[{i}]"
                child_label = f"[{i}]: {_value_preview(v) if show_values else type(v).__name__}"
                if not isinstance(v, (dict, list)):
                    add_node(child_id, child_label, "value")
                    edges.append({"from": path or "root", "to": child_id})
                walk(v, child_id, path or "root")
        else:
            # Primitive value; only add if it wasn't already added by parent
            if parent_id and path:
                add_node(path, _value_preview(obj) if show_values else type(obj).__name__, "value")
                edges.append({"from": parent_id, "to": path})

    walk(data, path="", parent_id=None)
    return nodes, edges, truncated


# ------------------------------
# UI
# ------------------------------
st.set_page_config(page_title="JSON Structure Viewer", layout="wide")

st.title("🔎 JSON Structure Viewer")

with st.sidebar:
    st.header("Input")
    file = st.file_uploader("Upload a JSON file", type=["json"])  # noqa: F841
    pasted = st.text_area("…or paste JSON here", height=140, placeholder='{"name":"Alice","items":[{"sku":1},{"sku":2}]}')
    show_values = st.toggle("Show value previews", value=True, help="When on, labels include short previews of primitive values.")
    max_nodes = st.slider("Max nodes (safety)", min_value=100, max_value=5000, value=1500, step=100)
    bubble_height = st.slider("Bubble view height (px)", 300, 900, 520)

# Read data
data: Any | None = None
err = None
if file is not None:
    try:
        data = json.load(file)
    except Exception as e:
        err = f"Failed to parse uploaded JSON: {e}"
elif pasted.strip():
    try:
        data = json.loads(pasted)
    except Exception as e:
        err = f"Failed to parse pasted JSON: {e}"

if err:
    st.error(err)

# Example data fallback
if data is None:
    data = {
        "example": True,
        "items": [
            {"id": 1, "name": "Vitamin C", "tags": ["supplement", "immune"]},
            {"id": 2, "name": "Magnesium", "strength": {"amount": 250, "unit": "mg"}},
        ],
        "meta": {"source": "sample", "count": 2},
    }
    st.info("No JSON provided. Using a small example so you can see the views.")

# Views
raw_tab, bubble_tab = st.tabs(["Raw JSON", "Bubble view (graph)"])

with raw_tab:
    st.subheader("Raw JSON")
    st.json(data)

with bubble_tab:
    st.subheader("Interactive graph (vis.js)")
    if not HAS_SVN:
        st.warning(
            "`streamlit-vis-network` is required for the Bubble view. Add it to requirements and reboot your app.")
        st.caption(
            "Tip: pip install streamlit-vis-network | Import name: from streamlit_vis_network import streamlit_vis_network"
        )
    else:
        nodes, edges, truncated = build_network(data, show_values=show_values, max_nodes=max_nodes)
        if truncated:
            st.info("Graph truncated to max nodes to keep things snappy. Increase the slider in the sidebar if needed.")

        # Provide a tiny hint about interaction
        with st.expander("What can I do here?", expanded=False):
            st.markdown(
                "- Drag nodes to rearrange\n- Scroll to zoom\n- Click to select a node/edge (selection shown below)"
            )

        selection = streamlit_vis_network(nodes, edges, height=bubble_height, width=1100)
        if selection:
            selected_nodes, selected_edges, positions = selection
            col1, col2 = st.columns(2)
            with col1:
                st.write("**Selected nodes**", selected_nodes)
                st.write("**Selected edges**", selected_edges)
            with col2:
                if st.toggle("Show node positions"):
                    st.write(positions)
