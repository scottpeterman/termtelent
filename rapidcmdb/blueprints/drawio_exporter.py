# Create these files in your project:

# exporters/__init__.py
"""
Export functionality for RapidCMDB
"""

# exporters/drawio_exporter.py
import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import tempfile
import uuid
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class RapidCMDBDrawioExporter:
    """Draw.io exporter adapted for RapidCMDB topology data"""

    def __init__(self, config_path: str = 'config/napalm_platform_icons.json'):
        self.config_path = Path(config_path)
        self.load_icon_config()
        self.next_id = 1

    def load_icon_config(self):
        """Load icon configuration"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    self.icon_config = json.load(f)
            else:
                logger.warning(f"Icon config not found at {self.config_path}, using defaults")
                self.icon_config = self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading icon config: {e}")
            self.icon_config = self._get_default_config()

    def _get_default_config(self):
        """Default icon configuration"""
        return {
            "platform_patterns": {
                "C9300": "shape=mxgraph.cisco.switches.layer_3_switch",
                "ISR4": "shape=mxgraph.cisco.routers.router",
                "Nexus": "shape=mxgraph.cisco.switches.nexus_7000"
            },
            "style_defaults": {
                "fillColor": "#036897",
                "strokeColor": "#ffffff",
                "strokeWidth": "2",
                "html": "1",
                "verticalLabelPosition": "bottom",
                "verticalAlign": "top",
                "align": "center"
            }
        }

    def export_topology(self, topology_data: Dict,
                        layout: str = 'tree',
                        include_endpoints: bool = True) -> Path:
        """
        Export RapidCMDB topology to Draw.io format

        Args:
            topology_data: Network topology from build_topology_map()
            layout: Layout type ('tree', 'grid', 'balloon')
            include_endpoints: Whether to include endpoint devices

        Returns:
            Path to generated .drawio file
        """
        try:
            # Filter endpoints if requested
            if not include_endpoints:
                topology_data = self._filter_endpoints(topology_data)

            # Calculate node positions
            positions = self._calculate_positions(topology_data, layout)

            # Create XML structure
            mxfile_root, cell_root = self._create_mxfile_structure()

            # Add nodes and edges
            node_elements = {}

            # Add all nodes first
            for node_id, (x, y) in positions.items():
                if node_id in topology_data:
                    cell_id = self._add_node(cell_root, node_id, topology_data[node_id], x, y)
                    node_elements[node_id] = cell_id

            # Add edges between nodes
            for source_id, source_data in topology_data.items():
                if source_id in node_elements:
                    peers = source_data.get('peers', {})
                    for target_id, peer_data in peers.items():
                        if target_id in node_elements:
                            connections = peer_data.get('connections', [])
                            for connection in connections:
                                self._add_edge(cell_root,
                                               node_elements[source_id],
                                               node_elements[target_id],
                                               connection)

            # Generate output file
            output_path = self._write_drawio_file(mxfile_root)
            logger.info(f"Successfully exported topology to {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Error exporting topology: {e}")
            raise

    def _filter_endpoints(self, topology_data: Dict) -> Dict:
        """Remove endpoint devices from topology"""
        filtered = {}

        # Identify network devices (devices that appear as both source and peer)
        all_sources = set(topology_data.keys())
        all_peers = set()

        for device_data in topology_data.values():
            all_peers.update(device_data.get('peers', {}).keys())

        network_devices = all_sources.intersection(all_peers)

        # Keep only network devices and their connections to other network devices
        for device_id in network_devices:
            if device_id in topology_data:
                device_data = topology_data[device_id].copy()

                # Filter peers to only include network devices
                filtered_peers = {
                    peer_id: peer_data
                    for peer_id, peer_data in device_data.get('peers', {}).items()
                    if peer_id in network_devices
                }
                device_data['peers'] = filtered_peers
                filtered[device_id] = device_data

        return filtered

    def _calculate_positions(self, topology_data: Dict, layout: str) -> Dict[str, Tuple[int, int]]:
        """Calculate node positions based on layout type"""
        nodes = list(topology_data.keys())
        positions = {}

        if layout == 'grid':
            # Simple grid layout
            cols = int(len(nodes) ** 0.5) + 1
            for i, node in enumerate(nodes):
                x = (i % cols) * 200 + 100
                y = (i // cols) * 150 + 100
                positions[node] = (x, y)

        elif layout == 'tree':
            # Tree layout - find root and arrange hierarchically
            positions = self._calculate_tree_layout(topology_data)

        else:  # Default to simple layout
            for i, node in enumerate(nodes):
                positions[node] = (i * 150 + 100, 100)

        return positions

    def _calculate_tree_layout(self, topology_data: Dict) -> Dict[str, Tuple[int, int]]:
        """Calculate hierarchical tree layout"""
        # Find root node (most connected or contains 'core')
        root_node = self._find_root_node(topology_data)

        # Build tree levels using BFS
        levels = {0: [root_node]}
        visited = {root_node}
        queue = [(root_node, 0)]

        while queue:
            node, level = queue.pop(0)
            peers = topology_data.get(node, {}).get('peers', {})

            for peer in peers:
                if peer not in visited and peer in topology_data:
                    visited.add(peer)
                    if level + 1 not in levels:
                        levels[level + 1] = []
                    levels[level + 1].append(peer)
                    queue.append((peer, level + 1))

        # Calculate positions
        positions = {}
        for level, nodes in levels.items():
            y = level * 150 + 100
            start_x = 100
            spacing = max(200, 800 // max(len(nodes), 1))

            for i, node in enumerate(nodes):
                x = start_x + i * spacing
                positions[node] = (x, y)

        return positions

    def _find_root_node(self, topology_data: Dict) -> str:
        """Find the best root node for tree layout"""
        # Prefer nodes with 'core' in name
        for node_id in topology_data:
            if 'core' in node_id.lower():
                return node_id

        # Otherwise, use most connected node
        max_connections = 0
        root_node = list(topology_data.keys())[0]

        for node_id, node_data in topology_data.items():
            connections = len(node_data.get('peers', {}))
            if connections > max_connections:
                max_connections = connections
                root_node = node_id

        return root_node

    def _create_mxfile_structure(self):
        """Create the base Draw.io XML structure"""
        mxfile = ET.Element("mxfile")
        mxfile.set("host", "app.diagrams.net")
        mxfile.set("modified", datetime.now().isoformat())

        diagram = ET.SubElement(mxfile, "diagram")
        diagram.set("id", "network_topology")
        diagram.set("name", "Network Topology")

        graph_model = ET.SubElement(diagram, "mxGraphModel")
        graph_model.set("dx", "1000")
        graph_model.set("dy", "800")
        graph_model.set("grid", "1")
        graph_model.set("gridSize", "10")

        root_element = ET.SubElement(graph_model, "root")

        # Add mandatory root cells
        parent = ET.SubElement(root_element, "mxCell")
        parent.set("id", "0")

        default_parent = ET.SubElement(root_element, "mxCell")
        default_parent.set("id", "1")
        default_parent.set("parent", "0")

        self.next_id = 2
        return mxfile, root_element

    def _add_node(self, root: ET.Element, node_id: str, node_data: dict, x: int, y: int) -> str:
        """Add a node to the diagram"""
        cell = ET.SubElement(root, "mxCell")
        cell_id = f"node_{self.next_id}"
        self.next_id += 1

        cell.set("id", cell_id)
        cell.set("vertex", "1")
        cell.set("parent", "1")

        # Get node style based on platform
        style = self._get_node_style(node_id, node_data)
        cell.set("style", style)

        # Set geometry
        geometry = ET.SubElement(cell, "mxGeometry")
        geometry.set("x", str(x))
        geometry.set("y", str(y))
        geometry.set("width", "80")
        geometry.set("height", "80")
        geometry.set("as", "geometry")

        # Set label
        node_details = node_data.get('node_details', {})
        platform = node_details.get('platform', 'Unknown')
        ip = node_details.get('ip', '')
        label = f"{node_id}\\n{ip}\\n{platform}"
        cell.set("value", label)

        return cell_id

    def _get_node_style(self, node_id: str, node_data: dict) -> str:
        """Get Draw.io style string for a node"""
        style_defaults = self.icon_config.get('style_defaults', {})
        platform_patterns = self.icon_config.get('platform_patterns', {})

        platform = node_data.get('node_details', {}).get('platform', '')

        # Find matching icon
        shape = None
        for pattern, icon_shape in platform_patterns.items():
            if pattern.lower() in platform.lower():
                shape = icon_shape
                break

        # Build style string
        style_parts = []
        for key, value in style_defaults.items():
            style_parts.append(f"{key}={value}")

        if shape:
            style_parts.append(shape)
        else:
            style_parts.append("shape=rectangle")

        return ";".join(style_parts)

    def _add_edge(self, root: ET.Element, source_id: str, target_id: str, connection: List):
        """Add an edge between two nodes"""
        cell = ET.SubElement(root, "mxCell")
        cell_id = f"edge_{self.next_id}"
        self.next_id += 1

        cell.set("id", cell_id)
        cell.set("edge", "1")
        cell.set("parent", "1")
        cell.set("source", source_id)
        cell.set("target", target_id)

        # Edge style
        cell.set("style", "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;")

        # Connection label
        if len(connection) >= 2:
            label = f"{connection[0]} - {connection[1]}"
            cell.set("value", label)

        # Geometry
        geometry = ET.SubElement(cell, "mxGeometry")
        geometry.set("relative", "1")
        geometry.set("as", "geometry")

    def _write_drawio_file(self, mxfile_root: ET.Element) -> Path:
        """Write the XML to a .drawio file"""
        # Create temporary file
        temp_dir = Path(tempfile.gettempdir()) / 'rapidcmdb_exports'
        temp_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = temp_dir / f"rapidcmdb_topology_{timestamp}.drawio"

        # Pretty print XML
        xml_str = ET.tostring(mxfile_root, encoding='unicode')
        pretty_xml = minidom.parseString(xml_str).toprettyxml(indent="  ")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)

        return output_path


# blueprints/drawio.py
from flask import Blueprint, request, jsonify, send_file
import tempfile
from pathlib import Path
from datetime import datetime
import logging

from .topology import build_topology_map  # Import your existing function

logger = logging.getLogger(__name__)

drawio_bp = Blueprint('drawio', __name__, url_prefix='/api/drawio')


@drawio_bp.route('/export', methods=['POST'])
def export_topology():
    """Export topology to Draw.io format"""
    try:
        config = request.get_json() or {}

        # Build topology using existing RapidCMDB function
        topology_data = build_topology_map(
            include_patterns=config.get('include_patterns'),
            exclude_patterns=config.get('exclude_patterns'),
            sites=config.get('sites'),
            roles=config.get('roles'),
            network_only=config.get('network_only', False)
        )

        if not topology_data:
            return jsonify({
                'success': False,
                'error': 'No topology data found with current filters'
            }), 400

        # Create exporter and export
        exporter = RapidCMDBDrawioExporter()
        output_path = exporter.export_topology(
            topology_data,
            layout=config.get('layout', 'tree'),
            include_endpoints=not config.get('network_only', False)
        )

        # Return file
        return send_file(
            output_path,
            as_attachment=True,
            download_name=f"rapidcmdb-topology-{datetime.now().strftime('%Y%m%d')}.drawio",
            mimetype='application/xml'
        )

    except Exception as e:
        logger.error(f"Draw.io export error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@drawio_bp.route('/preview', methods=['POST'])
def preview_export():
    """Get preview information about the export"""
    try:
        config = request.get_json() or {}

        topology_data = build_topology_map(
            include_patterns=config.get('include_patterns'),
            exclude_patterns=config.get('exclude_patterns'),
            sites=config.get('sites'),
            roles=config.get('roles'),
            network_only=config.get('network_only', False)
        )

        device_count = len(topology_data)
        connection_count = sum(
            len(device_data.get('peers', {}))
            for device_data in topology_data.values()
        )

        return jsonify({
            'success': True,
            'preview': {
                'device_count': device_count,
                'connection_count': connection_count,
                'layout_options': ['tree', 'grid', 'balloon'],
                'filters_applied': {
                    'sites': config.get('sites', []),
                    'network_only': config.get('network_only', False)
                }
            }
        })

    except Exception as e:
        logger.error(f"Preview error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
