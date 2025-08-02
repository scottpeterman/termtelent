from importlib import resources
from pathlib import Path
import base64
import json
from dataclasses import dataclass
from typing import List, Dict, Set, Tuple, Optional
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.dom import minidom
import sys
import re
import argparse

from termtel.graphml_layoutmgr import LayoutManager


@dataclass
class Connection:
    local_port: str
    remote_port: str


@dataclass
class NodeDetails:
    name: str
    ip: str
    platform: str


@dataclass
class Edge:
    source: str
    target: str
    connections: List[Connection]


@dataclass
class StyleConfig:
    shape_hints: Dict[str, List[str]]
    color_hints: Dict[str, Tuple[str, Optional[str], bool]]
    default_shape: str = "roundrectangle"
    default_style: Tuple[str, Optional[str], bool] = ("#FFFFFF", None, False)

@dataclass
class FallbackPattern:
    platform_patterns: List[str]
    name_patterns: List[str]
    icon: str

@dataclass
class IconConfig:
    platform_patterns: Dict[str, str]  # Maps platform patterns to icon files
    defaults: Dict[str, str]  # Default icons for device types
    base_path: str  # Base path for icon files
    fallback_patterns: Dict[str, FallbackPattern]  # Fallback pattern matching rules

class NetworkGraphMLExporter:

    def __init__(self, include_endpoints: bool = True, use_icons: bool = False, icons_dir: str = './icons_lib', layout_type: str = 'grid'):
        self.font_size = 12
        self.font_family = "Dialog"
        self.processed_edges: Set[tuple] = set()
        self.processed_connections: Set[tuple] = set()
        self.include_endpoints = include_endpoints
        self.use_icons = use_icons
        self.icons_dir = Path(icons_dir)
        self.mac_pattern = re.compile(r'[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}')
        self.layout_type = layout_type
        self.layout_manager = LayoutManager(layout_type)
        self._reset_icon_state()


        # Icon handling
        self.icons = {}
        self.next_icon_id = 1
        self.platform_patterns = {}
        self.default_icons = {}

        # Initialize style configuration
        self.style_config = StyleConfig(
            shape_hints={
                "hexagon": ["core", "lan", "iosv","eos","spine","leaf"],
                "ellipse": ["isr", "asr", "camera"],
                "rectangle": ["switch", "router"],
            },
            color_hints={
                "core": ("#CCFFFF", "#CCFFFF", False),  # Light blue for core
                "access": ("#FFFFD0", None, False),  # Light yellow for access
                "endpoint": ("#E0FFE0", None, False),  # Light green for endpoints
                "firewall": ("#FFE0E0", None, False),  # Light red for firewalls
                "default": ("#FFFFFF", None, False)  # White for default
            }
        )

        # Initialize layout manager
        self.layout_manager = LayoutManager(layout_type)

        # Load icons if enabled
        if use_icons and icons_dir:
            self.load_icons()

    def _reset_icon_state(self):
        """Reset all icon-related state"""
        self.icons = {}
        self.next_icon_id = 1
        self.platform_patterns = {}
        self.default_icons = {}
        self.processed_edges.clear()
        self.processed_connections.clear()


    def load_icons(self) -> None:
        """Load and configure icons from JSON configuration"""
        try:
            config_path = self.icons_dir / 'platform_icon_map.json'
            with open(config_path, 'r') as f:
                icon_config = json.load(f)

            # Parse fallback patterns
            fallback_patterns = {}
            for device_type, patterns in icon_config.get('fallback_patterns', {}).items():
                fallback_patterns[device_type] = FallbackPattern(
                    platform_patterns=patterns['platform_patterns'],
                    name_patterns=patterns['name_patterns'],
                    icon=patterns['icon']
                )

            # Create IconConfig
            config = IconConfig(
                platform_patterns=icon_config['platform_patterns'],
                defaults=icon_config['defaults'],
                base_path=str(self.icons_dir),  # Use resolved icons_dir path
                fallback_patterns=fallback_patterns
            )

            self.platform_patterns = config.platform_patterns
            self.default_icons = config.defaults
            self.fallback_patterns = config.fallback_patterns

            unique_icons = set(self.platform_patterns.values()) | set(self.default_icons.values())

            for icon_file in unique_icons:
                try:
                    base_name = Path(icon_file).stem
                    jpg_path = self.icons_dir / f"{base_name}.jpg"
                    jpeg_path = self.icons_dir / f"{base_name}.jpeg"

                    if jpg_path.exists():
                        icon_path = jpg_path
                    elif jpeg_path.exists():
                        icon_path = jpeg_path
                    else:
                        print(f"Warning: Icon file not found: {base_name}", file=sys.stderr)
                        continue

                    with open(icon_path, 'rb') as f:
                        base64_data = base64.b64encode(f.read()).decode('utf-8')
                        self.icons[icon_file] = base64_data.strip()

                except Exception as e:
                    print(f"Failed to load icon {icon_file}: {e}", file=sys.stderr)

        except Exception as e:
            print(f"Failed to load icon configuration: {e}", file=sys.stderr)

    def _get_node_icon(self, node_id: str, platform: str) -> Tuple[Optional[str], Optional[int]]:
        """Determine which icon to use based on node properties"""
        if not self.use_icons:
            return None, None

        platform_lower = platform.lower()
        node_id_lower = node_id.lower()

        # First try to match exact platform patterns
        for pattern, icon_file in self.platform_patterns.items():
            if pattern.lower() in platform_lower or pattern.lower() in node_id_lower:
                if icon_file in self.icons:
                    icon_id = self.next_icon_id
                    self.next_icon_id += 1
                    return self.icons[icon_file], icon_id

        # Try fallback patterns
        for fallback in self.fallback_patterns.values():
            if any(p.lower() in platform_lower for p in fallback.platform_patterns) or \
                    any(p.lower() in node_id_lower for p in fallback.name_patterns):
                default_icon = self.default_icons[fallback.icon]
                if default_icon in self.icons:
                    icon_id = self.next_icon_id
                    self.next_icon_id += 1
                    return self.icons[default_icon], icon_id

        # If no match found and it's an endpoint, use endpoint icon
        if self.is_endpoint(node_id, {'node_details': {'platform': platform}}):
            default_icon = self.default_icons['default_endpoint']
        else:
            default_icon = self.default_icons['default_unknown']

        if default_icon in self.icons:
            icon_id = self.next_icon_id
            self.next_icon_id += 1
            return self.icons[default_icon], icon_id

        return None, None

    def _add_resources(self, root: ET.Element, icon_mappings: Dict[int, str]) -> None:
        """Add resources section with icons"""
        if not icon_mappings:
            return

        resources = ET.SubElement(root, "data", key="d7")
        y_resources = ET.SubElement(resources, "y:Resources")

        for icon_id, icon_data in icon_mappings.items():
            resource = ET.SubElement(y_resources, "y:Resource")
            resource.set("id", str(icon_id))
            resource.set("type", "java.awt.image.BufferedImage")
            resource.set("xml:space", "preserve")

            # Clean the Base64 data properly
            clean_data = icon_data.replace('\n', '').replace('\r', '').replace('&#13;', '')

            # Split into 76-char lines
            chunks = [clean_data[i:i + 76] for i in range(0, len(clean_data), 76)]
            # Set text directly without XML escaping
            resource.text = '\n'.join(chunks)

    def is_endpoint(self, node_id: str, node_data: dict) -> bool:
        """Determine if a node is an endpoint device"""
        # Check if it's a MAC address endpoint
        if self.mac_pattern.match(node_id):
            return True

        # Check for common endpoint naming patterns
        endpoint_patterns = [
            'camera', 'wap', 'ap', 'phone', 'printer', 'endpoint',
            'pc-', 'laptop', 'tablet', 'mobile', 'sensor'
        ]

        node_id_lower = node_id.lower()
        for pattern in endpoint_patterns:
            if pattern in node_id_lower:
                return True

        # Check platform for typical endpoint indicators
        platform = node_data.get('node_details', {}).get('platform', '').lower()
        endpoint_keywords = {'endpoint', 'camera', 'wap', 'ap', 'phone', 'printer', 'wireless'}

        if any(keyword in platform for keyword in endpoint_keywords):
            return True

        # Check if node has no peers (leaf endpoint)
        peers = node_data.get('peers', {})
        if not peers:
            return True

        # Check connection patterns - endpoints typically connect via MAC addresses
        for peer_id, peer_data in peers.items():
            connections = peer_data.get('connections', [])
            for connection in connections:
                if len(connection) == 2:
                    # If remote port looks like a MAC address, this might be an endpoint
                    if self.mac_pattern.match(connection[1]):
                        return True

        return False
    def _get_node_style(self, node_id: str, node_data: dict) -> Tuple[str, Tuple[str, Optional[str], bool]]:
        """Determine node shape and style based on configuration"""
        platform = node_data.get('node_details', {}).get('platform', '').lower()

        # Determine shape
        shape = self.style_config.default_shape
        for shape_type, patterns in self.style_config.shape_hints.items():
            if any(pattern in platform or pattern in node_id.lower() for pattern in patterns):
                shape = shape_type
                break

        # Determine color style
        style = self.style_config.default_style
        for style_type, color_style in self.style_config.color_hints.items():
            if style_type in platform or style_type in node_id.lower():
                style = color_style
                break

        return shape, style

    def preprocess_topology(self, network_data: dict) -> dict:
        """Add missing node definitions and handle endpoint filtering"""
        # Create sets of defined and referenced nodes
        defined_nodes = set(network_data.keys())
        referenced_nodes = set()

        # First pass: Find all referenced nodes
        for node_data in network_data.values():
            if 'peers' in node_data:
                referenced_nodes.update(node_data['peers'].keys())

        # Identify endpoints (nodes that are referenced but not defined at top level)
        endpoint_nodes = referenced_nodes - defined_nodes

        print(f"DEBUG: Found {len(endpoint_nodes)} endpoint nodes: {list(endpoint_nodes)[:10]}")
        print(f"DEBUG: Include endpoints is: {self.include_endpoints}")

        # Start with the original topology
        processed_topology = network_data.copy()

        if self.include_endpoints:
            # Add basic definitions for undefined endpoint nodes
            for node_id in endpoint_nodes:
                processed_topology[node_id] = {
                    "node_details": {
                        "ip": "",
                        "platform": "",
                    },
                    "peers": {}
                }
        else:
            # Filter out endpoint references from peers lists
            for node_id, node_data in processed_topology.items():
                if 'peers' in node_data:
                    # Remove endpoint nodes from peers
                    filtered_peers = {
                        peer_id: peer_data
                        for peer_id, peer_data in node_data['peers'].items()
                        if peer_id not in endpoint_nodes
                    }
                    processed_topology[node_id] = {
                        "node_details": node_data.get("node_details", {}),
                        "peers": filtered_peers
                    }

        print(f"DEBUG: Final topology has {len(processed_topology)} nodes")
        return processed_topology
    def _add_node(self, graph: ET.Element, node_id: str, node_data: dict, idx: int, topology: dict) -> Optional[
        Tuple[int, str]]:
        """Add a node to the GraphML graph with single combined label"""
        node = ET.SubElement(graph, "node", id=node_id)
        node_data_elem = ET.SubElement(node, "data", key="d6")

        # Get position from layout manager
        x, y = self.layout_manager.calculate_position(node_id, node_data, topology, idx)

        if self.use_icons:
            icon_data, icon_id = self._get_node_icon(node_id, node_data['node_details']['platform'])
            if icon_data and icon_id:
                image_node = ET.SubElement(node_data_elem, "y:ImageNode")

                # Set geometry
                geometry = ET.SubElement(image_node, "y:Geometry")
                geometry.set("height", "51.0")
                geometry.set("width", "90.0")
                geometry.set("x", str(x))
                geometry.set("y", str(y))

                # Set fill
                fill = ET.SubElement(image_node, "y:Fill")
                fill.set("color", "#CCCCFF")
                fill.set("transparent", "false")

                # Set border
                border = ET.SubElement(image_node, "y:BorderStyle")
                border.set("color", "#000000")
                border.set("type", "line")
                border.set("width", "1.0")

                # Add single label with all information
                label = ET.SubElement(image_node, "y:NodeLabel")
                label.set("alignment", "center")
                label.set("autoSizePolicy", "content")
                label.set("fontFamily", "Dialog")
                label.set("fontSize", "12")
                label.set("fontStyle", "plain")
                label.set("hasBackgroundColor", "false")
                label.set("hasLineColor", "false")
                label.set("height", "18.701171875")
                label.set("horizontalTextPosition", "center")
                label.set("iconTextGap", "4")
                label.set("modelName", "eight_pos")
                label.set("modelPosition", "s")
                label.set("textColor", "#333333")
                label.set("verticalTextPosition", "bottom")
                label.set("visible", "true")
                label.set("width", "74.705078125")
                label.set("x", "7.6474609375")
                label.set("y", "55.0")

                # Combine all information with line breaks
                label_text = [node_id]
                if node_data['node_details']['ip']:
                    label_text.append(node_data['node_details']['ip'])
                if node_data['node_details']['platform']:
                    label_text.append(node_data['node_details']['platform'])
                label.text = '\n'.join(label_text)

                # Add image reference
                image = ET.SubElement(image_node, "y:Image")
                image.set("refid", str(icon_id))

                return icon_id, icon_data

        else:
            # Get node style for shape-based representation
            shape, style = self._get_node_style(node_id, node_data)

            # Create shape node
            shape_node = ET.SubElement(node_data_elem, "y:ShapeNode")

            # Set geometry with calculated position
            geometry = ET.SubElement(shape_node, "y:Geometry")
            geometry.set("height", "60")
            geometry.set("width", "120")
            geometry.set("x", str(x))
            geometry.set("y", str(y))

            # Set appearance
            fill = ET.SubElement(shape_node, "y:Fill")
            fill.set("color", style[0])
            if style[1]:
                fill.set("color2", style[1])
            fill.set("transparent", str(style[2]).lower())

            border = ET.SubElement(shape_node, "y:BorderStyle")
            border.set("color", "#000000")
            border.set("type", "line")
            border.set("width", "1.0")

            # Set shape
            shape_elem = ET.SubElement(shape_node, "y:Shape")
            shape_elem.set("type", shape)

            # Add labels
            name_label = ET.SubElement(shape_node, "y:NodeLabel")
            self._set_label_attributes(name_label, "c")
            platform = node_data['node_details']['platform']
            name_label.text = f"{node_id}\n{platform}"

            ip = node_data['node_details']['ip']
            if ip:
                ip_label = ET.SubElement(shape_node, "y:NodeLabel")
                self._set_label_attributes(ip_label, "b")
                ip_label.text = ip

            return None

    def export_to_graphml(self, network_data: dict, output_path: Path) -> None:
        """Export network topology to GraphML format"""
        # Preprocess the topology
        self._reset_icon_state()
        if self.use_icons:
            self.load_icons()
        # enhanced_topology = self.preprocess_topology(network_data)
        enhanced_topology = self.preprocess_topology(network_data.copy())

        # Create root element
        root = ET.Element("graphml")
        root.set("xmlns", "http://graphml.graphdrawing.org/xmlns")
        root.set("xmlns:java", "http://www.yworks.com/xml/yfiles-common/1.0/java")
        root.set("xmlns:sys", "http://www.yworks.com/xml/yfiles-common/markup/primitives/2.0")
        root.set("xmlns:x", "http://www.yworks.com/xml/yfiles-common/markup/2.0")
        root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
        root.set("xmlns:y", "http://www.yworks.com/xml/graphml")
        root.set("xmlns:yed", "http://www.yworks.com/xml/yed/3")
        root.set("xsi:schemaLocation",
                 "http://graphml.graphdrawing.org/xmlns http://www.yworks.com/xml/schema/graphml/1.1/ygraphml.xsd")

        # Add keys
        self._add_keys(root)

        # Create graph element
        graph = ET.SubElement(root, "graph", id="G", edgedefault="directed")

        # Track icon usage
        icon_mappings = {}

        # Add nodes
        for idx, (node_id, node_data) in enumerate(enhanced_topology.items()):
            icon_result = self._add_node(graph, node_id, node_data, idx, enhanced_topology)
            if icon_result:
                icon_id, icon_data = icon_result
                icon_mappings[icon_id] = icon_data

        # Reset connection tracking before processing edges
        self.processed_connections.clear()

        # Add edges
        for source_id, source_data in enhanced_topology.items():
            if 'peers' in source_data:
                for target_id, peer_data in source_data['peers'].items():
                    connections = []
                    for local_port, remote_port in peer_data.get('connections', []):
                        connections.append(Connection(local_port, remote_port))
                    if connections:
                        edge = Edge(source_id, target_id, connections)
                        self._add_edge(graph, edge)

        # Add resources section with icons if needed
        if icon_mappings:
            self._add_resources(root, icon_mappings)

        # Write to file
        xml_str = ET.tostring(root, encoding='unicode')
        pretty_xml = minidom.parseString(xml_str).toprettyxml(indent="  ")
        print(f"Writing graphml: {output_path}")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)

    def _add_keys(self, root: ET.Element) -> None:
        """Add all necessary yEd GraphML keys"""
        keys = [
            ("graph", "d0", "Description", "string"),
            ("port", "d1", None, None),
            ("port", "d2", None, None),
            ("port", "d3", None, None),
            ("node", "d4", "url", "string"),
            ("node", "d5", "description", "string"),
            ("node", "d6", None, None),
            ("graphml", "d7", None, None),  # Add this key for resources
            ("edge", "d8", "url", "string"),
            ("edge", "d9", "description", "string"),
            ("edge", "d10", None, None),
            # Add metadata keys
            ("node", "d11", "nmetadata", "string"),
            ("edge", "d12", "emetadata", "string"),
            ("graph", "d13", "gmetadata", "string")
        ]

        # Add default values for metadata keys
        metadata_keys = ["d11", "d12", "d13"]

        for target, id, name, attr_type in keys:
            key = ET.SubElement(root, "key")
            key.set("for", target)
            key.set("id", id)
            if name:
                key.set("attr.name", name)
            if attr_type:
                key.set("attr.type", attr_type)
            if id in ["d1", "d2", "d3", "d6", "d10"]:
                key.set("yfiles.type", "portgraphics" if id == "d1" else
                "portgeometry" if id == "d2" else
                "portuserdata" if id == "d3" else
                "nodegraphics" if id == "d6" else
                "edgegraphics")
            elif id == "d7":
                key.set("yfiles.type", "resources")

            # Add default empty value for metadata keys
            if id in metadata_keys:
                default = ET.SubElement(key, "default")
                default.text = ""

    def _set_label_attributes(self, label: ET.Element, position: str) -> None:
        """Set common label attributes"""
        label.set("alignment", "center")
        label.set("autoSizePolicy", "content")
        label.set("fontFamily", self.font_family)
        label.set("fontSize", str(self.font_size))
        label.set("fontStyle", "plain")
        label.set("hasBackgroundColor", "false")
        label.set("hasLineColor", "false")
        label.set("height", "18")
        label.set("horizontalTextPosition", "center")
        label.set("iconTextGap", "4")
        label.set("modelName", "internal")
        label.set("modelPosition", position)
        label.set("textColor", "#000000")
        label.set("verticalTextPosition", "bottom")
        label.set("visible", "true")
        label.set("width", "70")

    def _add_edge(self, graph: ET.Element, edge: Edge) -> None:
        """Add an edge to the GraphML graph with proper connection handling"""
        for conn in edge.connections:
            # Create a unique key for this specific connection
            conn_key = self._create_connection_key(edge.source, edge.target, conn)

            if conn_key not in self.processed_connections:
                edge_elem = self._create_edge_element(graph, edge, conn_key)
                polyline = self._create_edge_polyline(edge_elem)

                # Add port labels with different positions for source and target
                self._add_source_label(polyline, conn.local_port)
                self._add_target_label(polyline, conn.remote_port)

                self.processed_connections.add(conn_key)

    def _create_connection_key(self, source: str, target: str, conn: Connection) -> tuple:
        """Create a unique key for a connection"""
        return tuple(sorted([
            f"{source}:{conn.local_port}",
            f"{target}:{conn.remote_port}"
        ]))

    def _create_edge_element(self, graph: ET.Element, edge: Edge, conn_key: tuple) -> ET.Element:
        """Create the basic edge element"""
        edge_id = f"{hash(str(conn_key)) % 10000000:x}"
        edge_elem = ET.SubElement(graph, "edge",
                                  id=edge_id,
                                  source=edge.source,
                                  target=edge.target)
        return ET.SubElement(edge_elem, "data", key="d10")

    def _create_edge_polyline(self, data_elem: ET.Element) -> ET.Element:
        """Create and configure the polyline element for the edge"""
        polyline = ET.SubElement(data_elem, "y:PolyLineEdge")

        # Add line style
        line = ET.SubElement(polyline, "y:LineStyle")
        line.set("color", "#000000")
        line.set("type", "line")
        line.set("width", "1.0")

        # Add arrows
        arrows = ET.SubElement(polyline, "y:Arrows")
        arrows.set("source", "none")
        arrows.set("target", "none")

        # Add bend style
        bend_style = ET.SubElement(polyline, "y:BendStyle")
        bend_style.set("smoothed", "false")

        return polyline

    def _add_source_label(self, polyline: ET.Element, port: str) -> None:
        """Add source port label to the edge"""
        source_label = ET.SubElement(polyline, "y:EdgeLabel")
        self._set_edge_label_attributes(source_label, is_source=True)
        source_label.text = port

    def _add_target_label(self, polyline: ET.Element, port: str) -> None:
        """Add target port label to the edge"""
        target_label = ET.SubElement(polyline, "y:EdgeLabel")
        self._set_edge_label_attributes(target_label, is_source=False)
        target_label.text = port

    def _set_edge_label_attributes(self, label: ET.Element, is_source: bool) -> None:
        """Set edge label attributes with position-specific settings"""
        # Common attributes
        label.set("alignment", "center")
        label.set("backgroundColor", "#FFFFFF")
        label.set("configuration", "AutoFlippingLabel")
        label.set("fontFamily", self.font_family)
        label.set("fontSize", str(self.font_size))
        label.set("fontStyle", "plain")
        label.set("hasLineColor", "false")
        label.set("height", "18")
        label.set("modelName", "free")
        label.set("modelPosition", "anywhere")
        label.set("textColor", "#000000")
        label.set("visible", "true")
        label.set("width", "40")  # Increased from 32 for better text fitting

        # Position-specific attributes
        if is_source:
            label.set("distance", "10.0")
            label.set("ratio", "0.2")  # Closer to source
        else:
            label.set("distance", "10.0")
            label.set("ratio", "0.8")  # Closer to target

        # Set placement preference based on position
        label.set("preferredPlacement", "source_on_edge" if is_source else "target_on_edge")


def main():
    parser = argparse.ArgumentParser(description='Convert network topology JSON to GraphML')
    parser.add_argument('input', help='Input JSON file')
    parser.add_argument('output', help='Output GraphML file')
    parser.add_argument('--no-endpoints', action='store_true',
                       help='Exclude endpoint devices from the visualization')
    parser.add_argument('--icons', action='store_true',
                       help='Use icons for device visualization (requires icon files)')
    parser.add_argument('--icons-dir', type=str, default='./icons_lib',
                       help='Directory containing icon files (default: ./icons_lib)')
    parser.add_argument('--layout', choices=['grid', 'tree', 'balloon'], default='grid',
                       help='Layout type: grid (default), tree (directed tree), tb (tree/balloon)')

    args = parser.parse_args()

    try:
        # Read JSON topology
        with open(args.input, 'r') as f:
            network_data = json.load(f)

        # Map layout flag to layout type
        layout_mapping = {
            'grid': 'grid',
            'tree': 'directed_tree',
            'balloon': 'balloon'
        }

        layout_type = layout_mapping[args.layout]

        # Create exporter with specified layout
        exporter = NetworkGraphMLExporter(
            include_endpoints=not args.no_endpoints,
            use_icons=args.icons,
            icons_dir=args.icons_dir,
            layout_type=layout_type
        )

        # Export to GraphML
        exporter.export_to_graphml(network_data, Path(args.output))
        print(f"Successfully converted {args.input} to {args.output}")

        # Print summary of options used
        options_used = []
        if not args.no_endpoints:
            options_used.append("including endpoint devices")
        else:
            options_used.append("excluding endpoint devices")
        if args.icons:
            options_used.append("using icon representations")
        options_used.append(f"using {args.layout} layout")

        print(f"Options: {', '.join(options_used)}")

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
