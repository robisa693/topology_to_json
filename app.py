#!/usr/bin/env python3
"""
Topology JSON Builder
=====================
Install:  pip install fastapi uvicorn
Run:      python app.py
Open:     http://localhost:8080

Architecture
------------
- This file (app.py) owns ALL state and business logic.
- The frontend (static/index.html) owns ALL rendering and interaction.
- They communicate exclusively through the /api/* REST endpoints below.
- You should never need to edit anything below the DEFAULT_CONFIG block
  unless you want to add a new API endpoint.
"""
from __future__ import annotations
import copy, json, uuid
from typing import Any
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn


# ═══════════════════════════════════════════════════════════════════════════
#  DEFAULT CONFIG  ← Edit this block to customise the app before deploying.
#
#  Field types:
#    "text"        — free-text input
#    "number"      — numeric input
#    "select"      — single choice from "options" list
#    "multiselect" — multiple choices from "options" list (stored as array)
#
#  Rules:  parent_type → [list of allowed child types]
# ═══════════════════════════════════════════════════════════════════════════
DEFAULT_CONFIG: dict[str, Any] = {
    "nodeTypes": {
        "network": {
            "label": "Network", "color": "#38bdf8", "icon": "⬡",
            "props": {
                "cidr":    {"type": "text",   "label": "CIDR Block", "default": "10.0.0.0/24"},
                "vlan":    {"type": "number", "label": "VLAN ID",    "default": ""},
                "gateway": {"type": "text",   "label": "Gateway",    "default": ""},
                "zone":    {"type": "select", "label": "Zone",       "default": "private",
                            "options": ["private", "public", "dmz", "management"]},
            },
        },
        "vm": {
            "label": "VM", "color": "#4ade80", "icon": "▣",
            "props": {
                "cpu":   {"type": "select", "label": "CPU",  "default": "2 vCPU",
                          "options": ["1 vCPU","2 vCPU","4 vCPU","8 vCPU","16 vCPU","32 vCPU"]},
                "ram":   {"type": "select", "label": "RAM",  "default": "4 GB",
                          "options": ["512 MB","1 GB","2 GB","4 GB","8 GB","16 GB","32 GB","64 GB"]},
                "os":    {"type": "select", "label": "OS",   "default": "Ubuntu 22.04",
                          "options": ["Ubuntu 24.04","Ubuntu 22.04","Debian 12","Debian 11",
                                      "CentOS Stream 9","Rocky Linux 9","AlmaLinux 9",
                                      "Windows Server 2022","Windows Server 2019"]},
                "ip":    {"type": "text",   "label": "IP Address", "default": ""},
                "roles": {"type": "multiselect", "label": "Ansible Roles", "default": [],
                          "options": ["common","security-baseline","ufw","fail2ban",
                                      "nginx","apache2","caddy","docker","containerd",
                                      "kubernetes-node","postgresql","mysql","mariadb",
                                      "mongodb","redis","elasticsearch","kafka","rabbitmq",
                                      "prometheus-node-exporter","grafana-agent",
                                      "certbot","vault-agent","consul-agent"]},
            },
        },
        "storage": {
            "label": "Storage", "color": "#fbbf24", "icon": "◬",
            "props": {
                "size": {"type": "select", "label": "Size", "default": "100 GB",
                         "options": ["10 GB","50 GB","100 GB","500 GB","1 TB","5 TB"]},
                "type": {"type": "select", "label": "Type", "default": "SSD",
                         "options": ["SSD","NVMe","HDD","Object","NFS"]},
                "replication": {"type": "select", "label": "Replication", "default": "none",
                                "options": ["none","2x","3x","geo-redundant"]},
            },
        },
  
    },
    "rules": {
        "network":   ["vm"],
        "vm":        ["storage"],
    },
}
# ═══════════════════════════════════════════════════════════════════════════


# ── State ────────────────────────────────────────────────────────────────────

class AppState:
    """All mutable application state. Never access .nodes/.edges directly from routes."""

    def __init__(self) -> None:
        self.node_types: dict = copy.deepcopy(DEFAULT_CONFIG["nodeTypes"])
        self.rules: dict      = copy.deepcopy(DEFAULT_CONFIG["rules"])
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self.selected_id: str | None = None
        self._v: int = 0          # version counter – client polls this

    def _bump(self) -> None:
        self._v += 1

    # nodes
    def add_node(self, type_key: str) -> dict:
        td = self.node_types.get(type_key)
        if not td:
            raise ValueError(f"Unknown node type: {type_key!r}")
        idx   = sum(1 for n in self.nodes if n["type"] == type_key) + 1
        props = {
            k: copy.deepcopy(pd.get("default", [] if pd["type"] == "multiselect" else ""))
            for k, pd in td.get("props", {}).items()
        }
        col = len(self.nodes)
        node = {
            "id":    str(uuid.uuid4())[:8],
            "type":  type_key,
            "label": f"{td['label']} {idx}",
            "x":     180 + (col % 5) * 70,
            "y":     100 + (col // 5) * 60,
            "props": props,
        }
        self.nodes.append(node)
        self._bump()
        return node

    def update_node(self, node_id: str, label: str | None, props: dict | None) -> None:
        for n in self.nodes:
            if n["id"] == node_id:
                if label is not None: n["label"] = label
                if props  is not None: n["props"].update(props)
                self._bump()
                return

    def move_node(self, node_id: str, x: float, y: float) -> None:
        for n in self.nodes:
            if n["id"] == node_id:
                n["x"], n["y"] = x, y
                self._bump()
                return

    def delete_node(self, node_id: str) -> None:
        self.nodes = [n for n in self.nodes if n["id"] != node_id]
        self.edges = [e for e in self.edges if e["from"] != node_id and e["to"] != node_id]
        if self.selected_id == node_id:
            self.selected_id = None
        self._bump()

    def get_node(self, node_id: str) -> dict | None:
        return next((n for n in self.nodes if n["id"] == node_id), None)

    # edges
    def add_edge(self, from_id: str, to_id: str) -> tuple[dict | None, str]:
        fn = self.get_node(from_id)
        tn = self.get_node(to_id)
        if not fn or not tn:
            return None, "Node not found"
        if tn["type"] not in self.rules.get(fn["type"], []):
            fl = self.node_types.get(fn["type"], {}).get("label", fn["type"])
            tl = self.node_types.get(tn["type"], {}).get("label", tn["type"])
            return None, f"{tl} cannot be nested inside {fl}"
        if any(e["from"] == from_id and e["to"] == to_id for e in self.edges):
            return None, "Connection already exists"
        edge = {"id": str(uuid.uuid4())[:8], "from": from_id, "to": to_id}
        self.edges.append(edge)
        self._bump()
        return edge, ""

    def delete_edge(self, edge_id: str) -> None:
        self.edges = [e for e in self.edges if e["id"] != edge_id]
        self._bump()

    # JSON export
    def build_json(self) -> dict:
        child_ids = {e["to"] for e in self.edges}
        roots     = [n for n in self.nodes if n["id"] not in child_ids]

        def to_obj(node: dict) -> dict:
            obj: dict[str, Any] = {"type": node["type"]}
            obj.update(node["props"])
            for edge in self.edges:
                if edge["from"] == node["id"]:
                    child = self.get_node(edge["to"])
                    if child:
                        obj[child["label"]] = to_obj(child)
            return obj

        return {n["label"]: to_obj(n) for n in roots}

    # config
    def export_config(self) -> dict:
        return {"nodeTypes": self.node_types, "rules": self.rules}

    def import_config(self, data: dict) -> None:
        if "nodeTypes" in data: self.node_types = data["nodeTypes"]
        if "rules"     in data: self.rules      = data["rules"]
        self._bump()


state = AppState()


# ── API ───────────────────────────────────────────────────────────────────────

api = FastAPI(title="Topology Builder")

api.mount("/static", StaticFiles(directory="static"), name="static")

@api.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(Path("static/index.html").read_text("utf-8"))


# read
@api.get("/api/config")
def get_config():
    return state.export_config()

@api.get("/api/state")
def get_state():
    return {"v": state._v, "nodes": state.nodes, "edges": state.edges, "sel": state.selected_id}

@api.get("/api/json")
def get_json():
    return state.build_json()


# nodes
@api.post("/api/node")
def post_node(body: dict):
    try:
        return state.add_node(body["type"])
    except ValueError as e:
        raise HTTPException(400, str(e))

@api.patch("/api/node/{nid}")
def patch_node(nid: str, body: dict):
    state.update_node(nid, body.get("label"), body.get("props"))
    return {"ok": True}

@api.put("/api/node/{nid}/pos")
def put_node_pos(nid: str, body: dict):
    state.move_node(nid, body["x"], body["y"])
    return {"ok": True}

@api.put("/api/node/{nid}/select")
def put_node_select(nid: str):
    state.selected_id = nid
    state._bump()
    return {"ok": True}

@api.delete("/api/node/deselect")
def delete_select():
    state.selected_id = None
    state._bump()
    return {"ok": True}

@api.delete("/api/node/{nid}")
def delete_node(nid: str):
    state.delete_node(nid)
    return {"ok": True}


# edges
@api.post("/api/edge")
def post_edge(body: dict):
    edge, err = state.add_edge(body["from"], body["to"])
    if edge is None:
        return {"ok": False, "error": err}
    return {"ok": True, "edge": edge}

@api.delete("/api/edge/{eid}")
def delete_edge(eid: str):
    state.delete_edge(eid)
    return {"ok": True}


# settings
@api.get("/api/settings")
def get_settings():
    return state.export_config()

@api.post("/api/settings")
def post_settings(body: dict):
    state.import_config(body)
    return {"ok": True}

@api.put("/api/settings/type/{key}")
def put_type(key: str, body: dict):
    state.node_types[key] = body
    if key not in state.rules:
        state.rules[key] = []
    state._bump()
    return {"ok": True}

@api.delete("/api/settings/type/{key}")
def del_type(key: str):
    state.node_types.pop(key, None)
    state.rules.pop(key, None)
    for k in state.rules:
        state.rules[k] = [x for x in state.rules[k] if x != key]
    state._bump()
    return {"ok": True}

@api.put("/api/settings/rules")
def put_rules(body: dict):
    state.rules = body
    state._bump()
    return {"ok": True}


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Topology Builder running at http://localhost:8080")
    uvicorn.run(api, host="0.0.0.0", port=8080, log_level="warning")
