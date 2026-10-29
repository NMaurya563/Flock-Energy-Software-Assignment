"""Build hierarchy nodes while preserving ancestry and source-data conflicts."""

from datetime import datetime

from app.schemas.meter import Meter
from app.schemas.network import Network, NetworkNode


def build_network(meters: list[Meter], fetched_at: datetime) -> Network:
    nodes: dict[str, NetworkNode] = {}
    warnings: set[str] = set()
    parents: dict[tuple[str, str], str | None] = {}
    for meter in meters:
        parent = None
        for entry in meter.hierarchy:
            if not entry.code:
                warnings.add(f"Missing {entry.level} code for {meter.meter_id}.")
                continue
            # Full ancestry prevents merging reused codes under different parents.
            node_id = f"{parent + '/' if parent else ''}{entry.level}:{entry.code}"
            identity = (entry.level, entry.code)
            if identity in parents and parents[identity] != parent:
                warnings.add(f"{entry.level}:{entry.code} appears under multiple parents.")
            parents[identity] = parent
            if node_id not in nodes:
                nodes[node_id] = NetworkNode(
                    id=node_id,
                    level=entry.level,
                    code=entry.code,
                    name=entry.name,
                    parent_id=parent,
                    meter_count=0,
                )
            elif nodes[node_id].name != entry.name:
                warnings.add(f"Conflicting names for {entry.level}:{entry.code}.")
            nodes[node_id].meter_count += 1
            parent = node_id
    return Network(data=list(nodes.values()), warnings=sorted(warnings), fetched_at=fetched_at)
