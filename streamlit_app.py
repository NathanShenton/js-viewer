import streamlit as st
import json
from collections import deque
from streamlit_vis_network import streamlit_vis_network

# Safe optional imports
HAS_JSON_VIEW = False
HAS_VIS = False

try:
    from streamlit_json_view import json_view
    HAS_JSON_VIEW = True
except Exception as e:
    st.sidebar.warning(f"streamlit-json-view not available: {e}")

try:
    from streamlit_vis_network import vis_network
    HAS_VIS = True
except Exception as e:
    st.sidebar.warning(f"streamlit-vis-network not available: {e}")


# ------------------------ Helpers ------------------------

TYPE_COLOURS = {
    "object": "#4C78FF",     # blue
    "array":  "#00B894",     # green
    "string": "#FFCA3A",     # yellow
    "number": "#FF595E",     # red
    "boolean":"#9B5DE5",     # purple
    "null":   "#6C757D",     # grey
    "key":    "#2EC4B6"      # teal (for key-only helper nodes)
}

def node_type(value):
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"

def short(s, n=36):
    s = str(s)
    return s if len(s) <= n else s[: n-1] + "…"

def path_join(parent, key):
    if parent == "":
        return str(key)
    # arrays use [i], objects use .key
    if isinstance(key, int):
        return f"{parent}[{key}]"
    return f"{parent}.{key}"

def stringify(value):
    try:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)
    except Exception:
        return str(value)


# ---------------- Graph building (bubble view) ----------------

def build_graph(data, max_nodes=2500, max_depth=8):
    """
    Breadth-first traversal to prevent explosion on huge JSON.
    Creates a Vis Network node/edge list.
    """
    nodes, edges = [], []
    q = deque()
    q.append(("", data, 0))  # (path, value, depth)

    seen = set()

    while q and len(nodes) < max_nodes:
        path, value, depth = q.popleft()
        if path in seen:
            continue
        seen.add(path)

        t = node_type(value)
        label = "root" if path == "" else short(path.split(".")[-1].split("[")[0] or "[]")
        nodes.append({
            "id": path or "root",
            "label": label,
            "title": f"{path or 'root'}\n({t})",
            "shape": "dot",
            "color": TYPE_COLOURS[t],
            "size": 18 if t in ("object", "array") else 12
        })

        # create children
        if depth < max_depth:
            if isinstance(value, dict):
                for k, v in value.items():
                    child_path = path_join(path, k)
                    edges.append({"from": path or "root", "to": child_path})
                    q.append((child_path, v, depth + 1))
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    child_path = path_join(path, i)
                    edges.append({"from": path or "root", "to": child_path})
                    q.append((child_path, v, depth + 1))
            else:
                # leaf value node (show the value as a child bubble)
                val_id = f"{(path or 'root')}.__val__"
                nodes.append({
                    "id": val_id,
                    "label": short(value),
                    "title": f"value: {stringify(value)}",
                    "shape": "dot",
                    "color": TYPE_COLOURS[t],
                    "size": 10
                })
                edges.append({"from": path or "root", "to": val_id})

    return nodes, edges


def index_paths(data):
    """
    Returns a dict mapping each path -> (type, value preview)
    and also a simple string index for searching.
    """
    idx = {}

    def rec(path, value):
        t = node_type(value)
        preview = stringify(value)[:200]
        idx[path or "root"] = {"type": t, "preview": preview}

        if isinstance(value, dict):
            for k, v in value.items():
                rec(path_join(path, k), v)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                rec(path_join(path, i), v)

    rec("", data)
    return idx


def search_paths(idx, query):
    q = (query or "").strip().lower()
    if not q:
        return set()
    hits = set()
    for p, meta in idx.items():
        # match path or preview
        if q in p.lower() or q in (meta.get("preview") or "").lower():
            hits.add(p)
    return hits


def prune_to_matches(nodes, edges, matches):
    """
    Keep only nodes that are: a match, an ancestor, or a direct child of a match.
    """
    node_ids = {n["id"] for n in nodes}
    parent_of = {}
    for e in edges:
        parent_of.setdefault(e["to"], set()).add(e["from"])

    # Collect ancestors
    keep = set(matches)
    for m in list(matches):
        current = m
        while True:
            parents = parent_of.get(current, set())
            if not parents:
                break
            for p in parents:
                if p not in keep:
                    keep.add(p)
                    current = p

    # Keep direct children for context
    children_of = {}
    for e in edges:
        children_of.setdefault(e["from"], set()).add(e["to"])
    for m in list(matches):
        for c in children_of.get(m, []):
            keep.add(c)

    keep = keep & node_ids  # safety
    nodes_f = [n for n in nodes if n["id"] in keep]
    edges_f = [e for e in edges if e["from"] in keep and e["to"] in keep]
    return nodes_f, edges_f


def highlight_nodes(nodes, matches):
    for n in nodes:
        if n["id"] in matches or any(n["id"].startswith(m + ".") for m in matches):
            n["borderWidth"] = 3
            n["color"] = {"background": n["color"], "border": "#FFFFFF"}
        else:
            # dim non-matches a little
            n["opacity"] = 0.55
    return nodes


# ------------------------ UI ------------------------

st.set_page_config(page_title="Beautiful JSON Explorer", page_icon="🫧", layout="wide")

st.markdown("""
<style>
/* Polished dark surface */
.main > div { padding-top: 0.8rem; }
.block-container { padding-top: 1rem; }
h1, h2, h3 { letter-spacing: 0.2px; }
div[data-testid="stSidebar"] { background: #0f1116; }
.stTextInput > div > div > input, textarea {
    font-family: "Inter", ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
}
</style>
""", unsafe_allow_html=True)

st.title("🫧 JSON Visual Explorer")
st.caption("Upload or paste JSON. Explore as a collapsible tree or as a bubble graph with search and highlighting.")

with st.sidebar:
    st.header("Input")
    up = st.file_uploader("Upload JSON", type=["json"])
    raw = st.text_area("Or paste JSON here", height=180, placeholder='{"example": ["paste", "json", 123]}')

    st.header("Graph Options")
    max_depth = st.slider("Max depth (graph)", 2, 15, 8, help="Limit depth to avoid rendering huge graphs")
    max_nodes = st.slider("Max nodes (graph)", 200, 8000, 2500, step=100)

    st.header("Search")
    q = st.text_input("Search path or value (case-insensitive)", placeholder="e.g. product_code, 12345, ingredients")
    show_only_matches = st.checkbox("Show only matched branches", value=False)

# Load data (upload > paste > sample)
data = None
if up:
    data = json.load(up)
elif raw.strip():
    try:
        data = json.loads(raw)
    except Exception as e:
        st.error(f"Invalid JSON: {e}")
else:
    # Small built-in sample so the UI always demonstrates
    data = {
        "product": "SiSú Barista Oat Drink",
        "sku": "OAT-001",
        "nutrition": {
            "calories": 42,
            "fat": {"total": 1.5, "saturated": 0.2},
            "carbs": {"total": 6.7, "sugars": 0.3}
        },
        "ingredients": ["water", "oats", "sea salt"],
        "certs": [{"name": "Vegan", "id": 17}, {"name": "Non-GMO", "id": 9}],
        "available": True
    }

tabs = st.tabs(["🌳 Tree View", "🫧 Graph View", "ℹ️ Details"])

# ---------------- Tree View ----------------
with tabs[0]:
    st.subheader("Collapsible Tree")
    st.json(data)

# ---------------- Graph View ----------------
with tabs[1]:
    st.subheader("Bubble Graph")

    if not HAS_VIS:
        st.warning("`streamlit-vis-network` is required for the bubble view. Install with `pip install streamlit-vis-network`.")
    else:
        nodes, edges = build_graph(data, max_nodes=max_nodes, max_depth=max_depth)
        idx = index_paths(data)
        matches = search_paths(idx, q)

        if q:
            st.write(f"Matches: **{len(matches)}**")
        if show_only_matches and matches:
            nodes, edges = prune_to_matches(nodes, edges, matches)
        nodes = highlight_nodes(nodes, matches)

        # network options (hierarchical + smooth edges)
        options = {
            "nodes": {"font": {"face": "Inter", "size": 12}, "shadow": False},
            "edges": {"smooth": {"type": "dynamic"}, "color": {"opacity": 0.5}},
            "interaction": {"hover": True, "multiselect": False, "dragNodes": True, "dragView": True, "zoomView": True},
            "physics": {"enabled": True, "stabilization": {"iterations": 250}},
            "layout": {"hierarchical": {"enabled": True, "direction": "LR", "sortMethod": "directed"}}
        }

        vis_network(nodes, edges, height="760px", options=options)

        with st.expander("Legend / Colours"):
            c = TYPE_COLOURS
            st.write(
                f"**object** {c['object']} • **array** {c['array']} • **string** {c['string']} • "
                f"**number** {c['number']} • **boolean** {c['boolean']} • **null** {c['null']}"
            )

# ---------------- Details / Debug ----------------
with tabs[2]:
    st.subheader("Index & Search Debug")
    st.write("Use this to confirm what the search is matching against (paths and previews).")
    idx = index_paths(data)
    if q:
        matches = sorted(search_paths(idx, q))
        st.write("**Matched Paths**")
        for m in matches[:500]:
            st.write(f"- `{m}`")
    st.write("**All Paths (first 300)**")
    for i, (p, meta) in enumerate(idx.items()):
        if i >= 300:
            st.write("…truncated")
            break
        st.write(f"- `{p}` — *{meta['type']}* — preview: {short(meta['preview'], 80)}")
