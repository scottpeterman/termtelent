"""
Focused network topology exporter for traditional directed trees
Uses napalm_platform_icons.json for proper Cisco icon mapping
"""
import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from typing import Dict, List, Tuple, Set
from collections import defaultdict, deque
import re


class CiscoIconManager:
    """Manages Cisco icon mapping using napalm_platform_icons.json"""

    def __init__(self, config_path: str = 'napalm_platform_icons.json'):
        self.config = self._load_config(config_path)

    def _load_config(self, config_path: str) -> Dict:
        """Load the Cisco icon configuration"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load {config_path}: {e}")
            return self._get_minimal_config()

    def _get_minimal_config(self) -> Dict:
        """Minimal fallback configuration"""
        return {
            "style_defaults": {
                "fillColor": "#036897",
                "strokeColor": "#ffffff",
                "strokeWidth": "2",
                "html": "1",
                "verticalLabelPosition": "bottom",
                "verticalAlign": "top",
                "align": "center",
                "aspect": "fixed",
                "sketch": "0"
            },
            "defaults": {
                "default_switch": "shape=mxgraph.cisco.switches.layer_3_switch",
                "default_router": "shape=mxgraph.cisco.routers.router",
                "default_unknown": "shape=rectangle"
            }
        }

    def get_device_shape(self, node_id: str, platform: str, vendor: str = "",
                         device_role: str = "") -> str:
        """
        Get the appropriate Cisco shape for a device using priority order
        from napalm_platform_icons.json
        """
        platform_lower = platform.lower()
        node_id_lower = node_id.lower()
        vendor_lower = vendor.lower()
        role_lower = device_role.lower()

        # Follow priority order from config
        priority_order = self.config.get('priority_order', [
            'platform_patterns', 'vendor_patterns', 'device_role_patterns',
            'hostname_patterns', 'fallback_patterns', 'defaults'
        ])

        for pattern_type in priority_order:
            shape = self._check_pattern_type(pattern_type, node_id_lower,
                                             platform_lower, vendor_lower, role_lower)
            if shape:
                return shape

        # Final fallback
        return "shape=rectangle"

    def _check_pattern_type(self, pattern_type: str, node_id: str, platform: str,
                            vendor: str, role: str) -> str:
        """Check a specific pattern type for matches"""
        patterns = self.config.get(pattern_type, {})

        if pattern_type == 'platform_patterns':
            for pattern, shape in patterns.items():
                if pattern.lower() in platform:
                    return shape

        elif pattern_type == 'vendor_patterns':
            vendor_config = patterns.get(vendor.title(), {})
            for pattern, shape in vendor_config.items():
                if pattern.lower() in platform:
                    return shape

        elif pattern_type == 'device_role_patterns':
            for pattern, shape in patterns.items():
                if pattern.lower() in role or pattern.lower() in node_id:
                    return shape

        elif pattern_type == 'hostname_patterns':
            for category, config in patterns.items():
                for pattern in config.get('patterns', []):
                    if pattern.lower() in node_id:
                        return config.get('shape', '')

        elif pattern_type == 'fallback_patterns':
            for category, config in patterns.items():
                # Check platform patterns
                for pattern in config.get('platform_patterns', []):
                    if pattern.lower() in platform:
                        return config.get('shape', '')
                # Check name patterns
                for pattern in config.get('name_patterns', []):
                    if pattern.lower() in node_id:
                        return config.get('shape', '')
                # Check vendor patterns
                for pattern in config.get('vendor_patterns', []):
                    if pattern.lower() in vendor:
                        return config.get('shape', '')

        elif pattern_type == 'defaults':
            # Use default_switch as the final fallback
            return patterns.get('default_switch', 'shape=rectangle')

        return None

    def get_style_string(self, node_id: str, platform: str, vendor: str = "",
                         device_role: str = "") -> str:
        """Get complete style string for Draw.io"""
        # Get the shape
        shape = self.get_device_shape(node_id, platform, vendor, device_role)

        # Get style defaults
        style_defaults = self.config.get('style_defaults', {})

        # Build style string
        style_parts = [shape]
        for key, value in style_defaults.items():
            style_parts.append(f"{key}={value}")

        return ";".join(style_parts)


class TraditionalTreeLayoutManager:
    """Traditional top-down tree layout with straight edges"""

    def __init__(self):
        self.vertical_spacing = 150
        self.horizontal_spacing = 200
        self.start_x = 1000
        self.start_y = 100
        self.min_node_spacing = 120

    def calculate_positions(self, network_data: Dict) -> Dict[str, Tuple[int, int]]:
        """Calculate node positions for traditional directed tree"""
        if not network_data:
            return {}

        # Build tree structure
        tree_info = self._build_tree_structure(network_data)

        # Calculate positions using traditional algorithm
        return self._assign_tree_positions(tree_info)

    def _build_tree_structure(self, network_data: Dict) -> Dict:
        """Build hierarchical tree structure"""
        # Build adjacency list
        adjacency = defaultdict(set)
        for source, source_data in network_data.items():
            for peer in source_data.get('peers', {}):
                if peer in network_data:
                    adjacency[source].add(peer)
                    adjacency[peer].add(source)

        # Find root (prefer core devices)
        root = self._find_root_node(network_data, adjacency)

        # Build levels using BFS
        levels = {0: [root]}
        parent_map = {}
        children_map = defaultdict(list)
        visited = {root}
        queue = deque([(root, 0)])

        while queue:
            node, level = queue.popleft()

            # Get children sorted by priority
            children = sorted(
                adjacency[node] - visited,
                key=lambda x: self._get_node_priority(x, network_data)
            )

            if children:
                child_level = level + 1
                if child_level not in levels:
                    levels[child_level] = []

                for child in children:
                    levels[child_level].append(child)
                    parent_map[child] = node
                    children_map[node].append(child)
                    visited.add(child)
                    queue.append((child, child_level))

        return {
            'levels': levels,
            'parent_map': parent_map,
            'children_map': dict(children_map),
            'root': root
        }

    def _find_root_node(self, network_data: Dict, adjacency: Dict) -> str:
        """Find best root node (prefer core devices, then most connected)"""
        candidates = []

        for node_id in network_data:
            score = 0

            # Heavily prefer core devices
            if any(keyword in node_id.lower() for keyword in ['core', '-c-']):
                score += 1000
            elif any(keyword in node_id.lower() for keyword in ['spine', 'agg', 'distribution']):
                score += 500
            elif any(keyword in node_id.lower() for keyword in ['border', 'edge']):
                score += 300

            # Connection count
            score += len(adjacency[node_id]) * 10

            # Shorter names often indicate infrastructure devices
            score += max(0, 50 - len(node_id))

            candidates.append((score, node_id))

        return max(candidates)[1] if candidates else list(network_data.keys())[0]

    def _get_node_priority(self, node_id: str, network_data: Dict) -> str:
        """Get sorting priority for nodes (for consistent layout)"""
        # Infrastructure first, then alphabetical
        priority_prefixes = ['core', 'spine', 'agg', 'dist', 'access', 'border']

        for i, prefix in enumerate(priority_prefixes):
            if prefix in node_id.lower():
                return f"{i:02d}_{node_id.lower()}"

        return f"99_{node_id.lower()}"

    def _assign_tree_positions(self, tree_info: Dict) -> Dict[str, Tuple[int, int]]:
        """Assign x,y coordinates for traditional tree layout"""
        positions = {}
        levels = tree_info['levels']
        children_map = tree_info['children_map']

        # Calculate subtree widths for proper centering
        subtree_widths = {}

        # Bottom-up calculation of subtree widths
        for level in sorted(levels.keys(), reverse=True):
            for node in levels[level]:
                children = children_map.get(node, [])
                if not children:
                    subtree_widths[node] = 1
                else:
                    subtree_widths[node] = sum(subtree_widths[child] for child in children)

        # Top-down position assignment
        def assign_positions(node: str, level: int, x_start: float, x_end: float):
            # Center node in its allocated space
            x = (x_start + x_end) / 2
            y = self.start_y + (level * self.vertical_spacing)
            positions[node] = (int(x), int(y))

            # Position children
            children = children_map.get(node, [])
            if children:
                total_width = x_end - x_start
                current_x = x_start

                for child in children:
                    child_width_ratio = subtree_widths[child] / subtree_widths[node]
                    child_width = total_width * child_width_ratio
                    assign_positions(child, level + 1, current_x, current_x + child_width)
                    current_x += child_width

        # Start positioning from root
        root = tree_info['root']
        total_width = subtree_widths[root] * self.horizontal_spacing
        assign_positions(root, 0, self.start_x - total_width / 2, self.start_x + total_width / 2)

        return positions


class FocusedDrawioExporter:
    """Focused Draw.io exporter for traditional trees with Cisco icons"""

    def __init__(self, icons_config_path: str = 'napalm_platform_icons.json'):
        self.icon_manager = CiscoIconManager(icons_config_path)
        self.layout_manager = TraditionalTreeLayoutManager()
        self.next_id = 1

    def export_topology(self, network_data: Dict, output_path: str,
                        include_endpoints: bool = False) -> Path:
        """
        Export network topology as traditional directed tree

        Args:
            network_data: Network topology data
            output_path: Output file path (without .drawio extension)
            include_endpoints: Whether to include endpoint devices
        """
        # Filter endpoints if requested
        if not include_endpoints:
            network_data = self._filter_endpoints(network_data)

        if not network_data:
            raise ValueError("No network devices found after filtering")

        # Calculate positions
        positions = self.layout_manager.calculate_positions(network_data)

        # Create Draw.io XML
        mxfile_root, cell_root = self._create_mxfile_structure()

        # Add nodes and edges
        node_elements = self._add_nodes(cell_root, network_data, positions)
        self._add_edges(cell_root, network_data, node_elements)

        # Write file
        output_file = Path(f"{output_path}.drawio")
        self._write_drawio_file(mxfile_root, output_file)

        print(f"Exported {len(network_data)} devices to {output_file}")
        return output_file

    def _filter_endpoints(self, network_data: Dict) -> Dict:
        """Remove endpoint devices, keep only network infrastructure"""
        all_sources = set(network_data.keys())
        all_peers = set()

        for device_data in network_data.values():
            all_peers.update(device_data.get('peers', {}).keys())

        # Network devices appear as both source and peer
        network_devices = all_sources.intersection(all_peers)

        filtered = {}
        for device_id in network_devices:
            if device_id in network_data:
                device_data = network_data[device_id].copy()
                # Filter peers to only other network devices
                device_data['peers'] = {
                    peer_id: peer_data
                    for peer_id, peer_data in device_data.get('peers', {}).items()
                    if peer_id in network_devices
                }
                filtered[device_id] = device_data

        return filtered

    def _create_mxfile_structure(self) -> Tuple[ET.Element, ET.Element]:
        """Create base Draw.io XML structure"""
        mxfile = ET.Element("mxfile")
        mxfile.set("host", "app.diagrams.net")
        mxfile.set("modified", "2024-01-20T12:00:00.000Z")

        diagram = ET.SubElement(mxfile, "diagram")
        diagram.set("id", "network_topology")
        diagram.set("name", "Network Topology - Tree Layout")

        graph_model = ET.SubElement(diagram, "mxGraphModel")
        graph_model.set("dx", "1000")
        graph_model.set("dy", "800")
        graph_model.set("grid", "1")
        graph_model.set("gridSize", "10")

        root_element = ET.SubElement(graph_model, "root")

        # Mandatory root cells
        parent = ET.SubElement(root_element, "mxCell")
        parent.set("id", "0")

        default_parent = ET.SubElement(root_element, "mxCell")
        default_parent.set("id", "1")
        default_parent.set("parent", "0")

        self.next_id = 2
        return mxfile, root_element

    def _add_nodes(self, root: ET.Element, network_data: Dict,
                   positions: Dict[str, Tuple[int, int]]) -> Dict[str, str]:
        """Add nodes to the diagram with proper Cisco icons"""
        node_elements = {}

        for node_id, (x, y) in positions.items():
            if node_id not in network_data:
                continue

            cell = ET.SubElement(root, "mxCell")
            cell_id = f"node_{self.next_id}"
            self.next_id += 1

            cell.set("id", cell_id)
            cell.set("vertex", "1")
            cell.set("parent", "1")

            # Get node details
            node_data = network_data[node_id]
            node_details = node_data.get('node_details', {})
            platform = node_details.get('platform', '')
            ip = node_details.get('ip', '')

            # Get Cisco icon style using napalm_platform_icons.json
            style = self.icon_manager.get_style_string(
                node_id, platform, vendor="", device_role=""
            )
            cell.set("style", style)

            # Set geometry
            geometry = ET.SubElement(cell, "mxGeometry")
            geometry.set("x", str(x))
            geometry.set("y", str(y))
            geometry.set("width", "80")
            geometry.set("height", "80")
            geometry.set("as", "geometry")

            # Set label
            label_parts = [node_id]
            if ip:
                label_parts.append(ip)
            if platform:
                # Truncate long platform names
                platform_short = platform[:25] + "..." if len(platform) > 25 else platform
                label_parts.append(platform_short)

            cell.set("value", "\\n".join(label_parts))
            node_elements[node_id] = cell_id

        return node_elements

    def _add_edges(self, root: ET.Element, network_data: Dict,
                   node_elements: Dict[str, str]):
        """Add straight line edges between connected nodes"""
        added_edges = set()

        for source_id, source_data in network_data.items():
            if source_id not in node_elements:
                continue

            for peer_id, peer_data in source_data.get('peers', {}).items():
                if peer_id not in node_elements:
                    continue

                # Avoid duplicate edges
                edge_key = tuple(sorted([source_id, peer_id]))
                if edge_key in added_edges:
                    continue
                added_edges.add(edge_key)

                cell = ET.SubElement(root, "mxCell")
                cell_id = f"edge_{self.next_id}"
                self.next_id += 1

                cell.set("id", cell_id)
                cell.set("edge", "1")
                cell.set("parent", "1")
                cell.set("source", node_elements[source_id])
                cell.set("target", node_elements[peer_id])

                # Straight line style (no curves)
                cell.set("style", "edgeStyle=none;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;")

                # Add connection label if available
                connections = peer_data.get('connections', [])
                if connections and len(connections[0]) >= 2:
                    label = f"{connections[0][0]} - {connections[0][1]}"
                    cell.set("value", label)

                # Geometry
                geometry = ET.SubElement(cell, "mxGeometry")
                geometry.set("relative", "1")
                geometry.set("as", "geometry")

    def _write_drawio_file(self, mxfile_root: ET.Element, output_path: Path):
        """Write XML to Draw.io file"""
        xml_str = ET.tostring(mxfile_root, encoding='unicode')
        pretty_xml = minidom.parseString(xml_str).toprettyxml(indent="  ")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)


# Example usage
def main():
    """Example usage of the focused tree exporter"""
    # Load network topology
    with open('network_topology.json', 'r') as f:
        network_data = json.load(f)

    # Create exporter
    exporter = FocusedDrawioExporter('napalm_platform_icons.json')

    # Export as traditional directed tree
    output_path = exporter.export_topology(
        network_data,
        'network_tree_focused',
        include_endpoints=False  # Network infrastructure only
    )

    print(f"Traditional directed tree exported to: {output_path}")


if __name__ == '__main__':
    main()