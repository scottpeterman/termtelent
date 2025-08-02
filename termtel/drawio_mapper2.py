import argparse
import base64
import json
import traceback
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.dom import minidom
import re
import sys
import math
from collections import defaultdict

from .drawio_layoutmanager import DrawioLayoutManager


@dataclass
class Connection:
    """Represents a connection between two network devices"""
    local_port: str
    remote_port: str

@dataclass
class Node:
    """Represents a network device node"""
    id: str
    name: str
    ip: str
    platform: str
    x: int
    y: int

@dataclass
class FallbackPattern:
    """Define pattern matching rules for device types"""
    platform_patterns: List[str]
    name_patterns: List[str]
    icon: str

@dataclass
class IconConfig:
    """Configuration for icon mapping and fallback rules"""
    platform_patterns: Dict[str, str]
    defaults: Dict[str, str]
    base_path: str
    fallback_patterns: Dict[str, FallbackPattern]

class NetworkTopologyFilter:
    """Handles filtering of network topology, especially for endpoints"""
    def __init__(self):
        self.mac_pattern = re.compile(r'[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}')
        self.endpoint_keywords = {
            'endpoint', 'camera', 'wap', 'ap', 'phone', 'printer',
            'laptop', 'desktop', 'workstation', 'terminal', 'scanner'
        }

    def is_endpoint(self, node_id: str, node_data: dict) -> bool:
        """Determine if a node is an endpoint device"""
        if self.mac_pattern.match(node_id):
            return True

        platform = node_data.get('node_details', {}).get('platform', '').lower()
        if any(keyword in platform for keyword in self.endpoint_keywords):
            return True

        if not node_data.get('peers'):
            return True

        return False

    def filter_topology(self, network_data: Dict) -> Dict:
        """Create filtered version of topology excluding endpoints"""
        endpoints = set()
        for node_id, node_data in network_data.items():
            if self.is_endpoint(node_id, node_data):
                endpoints.add(node_id)

        filtered_topology = {}
        for node_id, node_data in network_data.items():
            if node_id not in endpoints:
                filtered_node = {
                    'node_details': node_data['node_details'].copy(),
                    'peers': {}
                }

                if 'peers' in node_data:
                    for peer_id, peer_data in node_data['peers'].items():
                        if peer_id not in endpoints:
                            filtered_node['peers'][peer_id] = peer_data.copy()

                filtered_topology[node_id] = filtered_node

        return filtered_topology



class IconManager:
    def __init__(self, icons_dir: str = './icons_lib'):
        self.icons_dir = Path(icons_dir)
        self.platform_patterns = {}
        self.style_defaults = {}
        self.load_mappings()

    def load_mappings(self) -> None:
        try:
            config_path = 'napalm_platform_icons.json'
            with open(config_path, 'r') as f:
                icon_config = json.load(f)

            self.platform_patterns = icon_config.get('platform_patterns', {})
            self.style_defaults = icon_config.get('style_defaults', {})

        except Exception as e:
            print(f"Warning: Failed to load icon configuration: {e}", file=sys.stderr)
            self.style_defaults = {
                "fillColor": "#036897",
                "strokeColor": "#ffffff",
                "strokeWidth": "2",
                "html": "1",
                "verticalLabelPosition": "bottom",
                "verticalAlign": "top",
                "align": "center"
            }

    def get_node_style(self, node_id: str, platform: str) -> Dict[str, str]:
        """Get complete style dictionary for a node with debug logging"""
        try:
            # Start with default styles
            style = self.style_defaults.copy()

            print(f"\nDebug: Processing node {node_id} with platform {platform}")

            # Look for platform match
            shape = None
            for pattern, shape_value in self.platform_patterns.items():
                if pattern in platform:
                    shape = shape_value
                    print(f"Debug: Found platform match: {pattern} -> {shape}")
                    break
                else:
                    print(f"Debug: No match for pattern: {pattern}")

            if shape:
                # Extract just the shape name from mxgraph format
                if "shape=mxgraph" in shape:
                    style.update({
                        "shape": shape.split('=')[1],
                        "sketch": "0"
                    })
                    print(f"Debug: Applied mxgraph shape: {shape}")
                else:
                    style["shape"] = shape
                    print(f"Debug: Applied regular shape: {shape}")

                # Convert style dict to string for debug
                style_str = ";".join(f"{k}={v}" for k, v in style.items())
                print(f"Debug: Final style string: {style_str}")

            return style

        except Exception as e:
            print(f"Error in style generation for {node_id}: {e}")
            return self.style_defaults

    def cleanup(self):
        pass

class NetworkDrawioExporter:
    """Main class for exporting network topology to Draw.io format"""

    def __init__(self, include_endpoints: bool = True, use_icons: bool = True,
                 layout_type: str = 'grid', icons_dir: str = './icons_lib'):
        self._reset_state()

        self.include_endpoints = include_endpoints
        self.use_icons = use_icons
        self.layout_type = layout_type
        self.next_id = 1

        # Initialize components
        self.topology_filter = NetworkTopologyFilter()
        self.layout_manager = DrawioLayoutManager(layout_type)
        self.icon_manager = IconManager(icons_dir)

    def _reset_state(self):
        """Reset internal state for new export"""
        self.next_id = 1
        if hasattr(self, 'icon_manager'):
            self.icon_manager.cleanup()

    def create_mxfile(self) -> Tuple[ET.Element, ET.Element]:
        """Create the base mxfile structure with proper hierarchy"""
        # Create mxfile root with required attributes
        mxfile = ET.Element("mxfile")
        mxfile.set("host", "app.diagrams.net")
        mxfile.set("modified", "2024-01-18T12:00:00.000Z")
        mxfile.set("agent",
                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) draw.io/21.2.1 Chrome/112.0.5615.87 Electron/24.1.2 Safari/537.36")
        mxfile.set("version", "21.2.1")
        mxfile.set("type", "device")

        # Create diagram element
        diagram = ET.SubElement(mxfile, "diagram")
        diagram.set("id", "network_topology")
        diagram.set("name", "Network Topology")

        # Create mxGraphModel element
        graph_model = ET.SubElement(diagram, "mxGraphModel")
        graph_model.set("dx", "1000")
        graph_model.set("dy", "800")
        graph_model.set("grid", "1")
        graph_model.set("gridSize", "10")
        graph_model.set("guides", "1")
        graph_model.set("tooltips", "1")
        graph_model.set("connect", "1")
        graph_model.set("arrows", "1")
        graph_model.set("fold", "1")
        graph_model.set("page", "1")
        graph_model.set("pageScale", "1")
        graph_model.set("pageWidth", "850")
        graph_model.set("pageHeight", "1100")
        graph_model.set("math", "0")
        graph_model.set("shadow", "0")

        # Create root element that will contain cells
        root_element = ET.SubElement(graph_model, "root")

        # Add mandatory root cells with unique IDs
        parent = ET.SubElement(root_element, "mxCell")
        parent.set("id", "0")

        default_parent = ET.SubElement(root_element, "mxCell")
        default_parent.set("id", "root_1")
        default_parent.set("parent", "0")

        # Initialize the next_id counter after root cells
        self.next_id = 2

        return mxfile, root_element

    def add_node(self, root: ET.Element, node_id: str, node_data: dict, x: int, y: int) -> str:
        """Add a node to the diagram"""
        try:
            cell = ET.SubElement(root, "mxCell")
            cell_id = f"node_{self.next_id}"
            self.next_id += 1

            cell.set("id", cell_id)
            cell.set("vertex", "1")
            cell.set("parent", "root_1")

            # Get style including icon if icons are enabled
            if self.use_icons:
                try:
                    style = self.icon_manager.get_node_style(
                        node_id,
                        node_data.get('node_details', {}).get('platform', 'unknown')
                    )
                except Exception as e:
                    print(f"Warning: Style error for {node_id}, using default style: {e}")
                    style = {
                        "shape": "rectangle",
                        "whiteSpace": "wrap",
                        "html": "1",
                        "aspect": "fixed"
                    }
            else:
                style = {
                    "shape": "rectangle",
                    "whiteSpace": "wrap",
                    "html": "1",
                    "aspect": "fixed"
                }

            # Convert style dict to string
            style_str = ";".join(f"{k}={v}" for k, v in style.items())
            cell.set("style", style_str)

            # Set geometry
            geometry = ET.SubElement(cell, "mxGeometry")
            geometry.set("x", str(x))
            geometry.set("y", str(y))
            geometry.set("width", "80")
            geometry.set("height", "80")
            geometry.set("as", "geometry")

            # Set label with device info
            try:
                platform = node_data.get('node_details', {}).get('platform', 'unknown')
                ip = node_data.get('node_details', {}).get('ip', '')
                label = f"{node_id}\n{ip}\n{platform}"
                cell.set("value", label)
            except Exception as e:
                print(f"Warning: Label error for {node_id}, using node_id only: {e}")
                cell.set("value", node_id)

            return cell_id

        except Exception as e:
            print(f"Error adding node {node_id}: {e}")
            raise

    def add_edge(self, root: ET.Element, source_id: str, target_id: str, connection: Connection) -> None:
        """Add an edge between nodes"""
        cell = ET.SubElement(root, "mxCell")
        cell_id = f"edge_{self.next_id}"
        self.next_id += 1

        # Set basic attributes
        cell.set("id", cell_id)
        cell.set("parent", "root_1")
        cell.set("source", source_id)
        cell.set("target", target_id)

        # Set edge style without arrow tips
        base_style = self.layout_manager.get_edge_style()
        # Add endArrow=none to remove arrow tips
        if "endArrow=" not in base_style:
            style_with_no_arrows = base_style + ";endArrow=none;startArrow=none"
        else:
            # Replace existing arrow settings
            style_with_no_arrows = base_style.replace("endArrow=classic", "endArrow=none")
            if "startArrow=" not in style_with_no_arrows:
                style_with_no_arrows += ";startArrow=none"

        cell.set("style", style_with_no_arrows)

        # Set additional edge attributes
        for key, value in self.layout_manager.get_edge_attributes().items():
            cell.set(key, value)

        # Add port labels
        label = f"{connection.local_port} -> {connection.remote_port}"

        cell.set("value", label)

        # Set geometry
        geometry = ET.SubElement(cell, "mxGeometry")
        geometry.set("relative", "1")
        geometry.set("as", "geometry")

    def export_to_drawio(self, network_data: Dict, output_path: Path) -> None:
        """Export network topology to Draw.io format"""
        try:
            # Get filtered topology if needed
            if not self.include_endpoints:
                network_data = self.topology_filter.filter_topology(network_data.copy())

            # Build edges list for layout calculation
            edges = []
            for source_id, source_data in network_data.items():
                if 'peers' in source_data:
                    for target_id in source_data['peers']:
                        if target_id in network_data:  # Only add edge if target exists
                            edges.append((source_id, target_id))

            # Calculate node positions using appropriate layout
            node_positions = self.layout_manager.get_node_positions(network_data, edges)

            # Create XML structure
            mxfile_root, cell_root = self.create_mxfile()
            node_elements = {}

            # Add nodes
            for node_id, (x, y) in node_positions.items():
                try:
                    node_data = network_data[node_id]
                    cell_id = self.add_node(cell_root, node_id, node_data, x, y)
                    node_elements[node_id] = cell_id
                except Exception as e:
                    print(f"Warning: Failed to add node {node_id}: {e}")

            # Add edges - with deduplication to avoid bidirectional duplicates
            processed_connections = set()

            for source_id, source_data in network_data.items():
                if 'peers' in source_data:
                    for target_id, peer_data in source_data['peers'].items():
                        if source_id in node_elements and target_id in node_elements:
                            # Collect all connections between these two devices
                            connections = peer_data.get('connections', [])

                            # Process each individual connection
                            for local_port, remote_port in connections:
                                # Create a unique key for this specific connection
                                # Use sorted device names and sorted port names to ensure consistency
                                if source_id < target_id:
                                    connection_key = (source_id, target_id, local_port, remote_port)
                                else:
                                    connection_key = (target_id, source_id, remote_port, local_port)

                                # Skip if we've already processed this specific connection
                                if connection_key in processed_connections:
                                    continue

                                processed_connections.add(connection_key)

                                try:
                                    connection = Connection(local_port, remote_port)
                                    self.add_edge(
                                        cell_root,
                                        node_elements[source_id],
                                        node_elements[target_id],
                                        connection
                                    )
                                except Exception as e:
                                    print(
                                        f"Warning: Failed to add edge {source_id} -> {target_id} ({local_port} -> {remote_port}): {e}")

            # Create the XML tree
            tree = ET.ElementTree(mxfile_root)

            # Make the output pretty
            xml_str = ET.tostring(mxfile_root, encoding='unicode')
            pretty_xml = minidom.parseString(xml_str).toprettyxml(indent="  ")

            # Write to file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(pretty_xml)

            print(f"\nSuccessfully exported diagram to {output_path}")

            # Print configuration summary
            print("\nExport Configuration:")
            print(f"Layout: {self.layout_type}")
            print(f"Endpoints: {'included' if self.include_endpoints else 'excluded'}")
            print(f"Icons: {'enabled' if self.use_icons else 'disabled'}")

        except Exception as e:
            print(f"Error during export: {e}")
            raise

    def cleanup(self):
        """Clean up resources"""
        self.icon_manager.cleanup()

def main():
    parser = argparse.ArgumentParser(
        description='Convert network topology JSON to Draw.io format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    # Basic conversion with default settings
    %(prog)s topology.json output.drawio

    # Exclude endpoint devices and use grid layout
    %(prog)s --no-endpoints --layout grid topology.json output.drawio

    # Use custom icon set with tree layout
    %(prog)s --icons --icons-dir ./my_icons --layout tree topology.json output.drawio
        '''
    )

    parser.add_argument('input', help='Input JSON file containing network topology')
    parser.add_argument('output', help='Output Draw.io file')

    parser.add_argument('--no-endpoints', action='store_true',
                        help='Exclude endpoint devices from the visualization')

    parser.add_argument('--layout',
                        choices=['grid', 'tree', 'balloon'],
                        default='grid',
                        help='Layout algorithm to use (default: grid)')

    parser.add_argument('--icons', action='store_true',
                        help='Use icons for device visualization')

    parser.add_argument('--icons-dir', type=str,
                        default='./icons_lib',
                        help='Directory containing icon files and configuration')

    args = parser.parse_args()

    try:
        # Read input topology
        with open(args.input, 'r') as f:
            network_data = json.load(f)

        # Create exporter with specified options
        exporter = NetworkDrawioExporter(
            include_endpoints=not args.no_endpoints,
            use_icons=args.icons,
            layout_type=args.layout,
            icons_dir=args.icons_dir
        )

        # Export the diagram
        exporter.export_to_drawio(network_data, Path(args.output))
        print(f"\nSuccessfully exported to {args.output}")

        # Print configuration summary
        print("\nExport Configuration:")
        print(f"Layout: {args.layout}")
        print(f"Endpoints: {'excluded' if args.no_endpoints else 'included'}")
        print(f"Icons: {'enabled' if args.icons else 'disabled'}")

        # Clean up
        exporter.cleanup()

    except FileNotFoundError as e:
        print(f"Error: File not found - {e.filename}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in input file {args.input}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        traceback.print_exc()
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

