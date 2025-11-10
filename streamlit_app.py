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

    Uses **sequential integer ids** for nodes (safer for some wrappers).

    Returns: nodes, edges, truncated
    """
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    truncated = False

    path_to_id: Dict[str, int] = {}
    next_id = 1

    def add_node(path: str, label: str, group: str) -> int | None:
        nonlocal next_id, truncated
        if path in path_to_id:
            return path_to_id[path]
        if len(nodes) >= max_nodes:
            truncated = True
            return None
        nid = next_id
        next_id += 1
        path_to_id[path] = nid
        node: Dict[str, Any] = {"id": nid, "label": label}
        node["group"] = group
        nodes.append(node)
        return nid

    def walk(obj: Any, path: str, parent_nid: int | None) -> None:
        nonlocal truncated
        if truncated:
            return
        if isinstance(obj, dict):
            label = (path.split(".")[-1] if path else "root") + " {}"
            nid = add_node(path or "root", label, "object")
            if nid is None:
                return
            if parent_nid is not None:
                edges.append({"from": parent_nid, "to": nid})
            for k, v in obj.items():
                child_path = f"{path + '.' if path else ''}{k}"
                walk(v, child_path, nid)
        elif isinstance(obj, list):
            label = (path.split(".")[-1] if path else "root") + f" [{len(obj)}]"
            nid = add_node(path or "root", label, "array")
            if nid is None:
                return
            if parent_nid is not None:
                edges.append({"from": parent_nid, "to": nid})
            for i, v in enumerate(obj):
                child_path = f"{path}[{i}]" if path else f"[{i}]"
                walk(v, child_path, nid)
        else:
            label = _value_preview(obj) if show_values else type(obj).__name__
            nid = add_node(path, label, "value")
            if nid is None:
                return
            if parent_nid is not None:
                edges.append({"from": parent_nid, "to": nid})

    walk(data, path="", parent_nid=None)
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
    bubble_width = st.slider("Bubble view width (px)", 400, 1400, 900)
    st.caption("If the graph doesn't render, try reducing width or nodes, or use the Test graph below.")

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
        # Quick sanity test button to isolate component issues
        with st.expander("Test the component", expanded=False):
            if st.button("Render tiny test graph"):
                test_nodes = [{"id": 1, "label": "A"}, {"id": 2, "label": "B"}]
                test_edges = [{"from": 1, "to": 2, "label": "A→B"}]
                _ = streamlit_vis_network(test_nodes, test_edges, height=320, width=600)
                st.success("If you can see A—B above, the component is working.")

        nodes, edges, truncated = build_network(data, show_values=show_values, max_nodes=max_nodes)

        st.caption(f"Nodes: {len(nodes)} | Edges: {len(edges)}" + (" | Truncated" if truncated else ""))

        if not nodes:
            st.error("No nodes to render. Paste/upload some JSON in the sidebar, or lower the max nodes limit.")
        else:
            # Hint about interaction
            with st.expander("What can I do here?", expanded=False):
                st.markdown("""
- Drag nodes to rearrange
- Scroll to zoom
- Click to select a node/edge (selection shown below)
""")

            selection = streamlit_vis_network(nodes, edges, height=bubble_height, width=bubble_width)
            if selection:
                selected_nodes, selected_edges, positions = selection
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**Selected nodes**", selected_nodes)
                    st.write("**Selected edges**", selected_edges)
                with col2:
                    if st.toggle("Show node positions"):
                        st.write(positions)
