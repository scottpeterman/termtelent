# blueprints/drawpyo_exporter.py
"""
Draw.io exporter using the drawpyo library with comprehensive JSON icon mapping
Requires: pip install drawpyo networkx
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import tempfile
from datetime import datetime
from collections import defaultdict

try:
    import drawpyo
    import networkx as nx

    DRAWPYO_AVAILABLE = True
except ImportError as e:
    DRAWPYO_AVAILABLE = False
    print(f"Required libraries not available: {e}")
    print("Install with: pip install drawpyo networkx")

# Import interface normalizer if available
try:
    from .enh_int_normalizer import InterfaceNormalizer, Platform

    INTERFACE_NORMALIZER_AVAILABLE = True
except ImportError:
    try:
        from enh_int_normalizer import InterfaceNormalizer, Platform

        INTERFACE_NORMALIZER_AVAILABLE = True
    except ImportError:
        INTERFACE_NORMALIZER_AVAILABLE = False
        print("Interface normalizer not available - using raw interface names")

logger = logging.getLogger(__name__)


def normalize_interface_name(interface_name: str, vendor: str = "", platform: str = "") -> str:
    """Normalize interface name using InterfaceNormalizer if available"""
    if not INTERFACE_NORMALIZER_AVAILABLE:
        return interface_name

    try:
        # Map vendor to platform enum
        platform_mapping = {
            'cisco': Platform.CISCO_IOS,
            'arista': Platform.ARISTA,
            'nexus': Platform.CISCO_NXOS,
        }

        # Check for NX-OS indicators
        if 'nexus' in platform.lower() or 'nx-os' in platform.lower():
            platform_enum = Platform.CISCO_NXOS
        else:
            platform_enum = platform_mapping.get(vendor.lower(), Platform.UNKNOWN)

        # Normalize with short names for labels
        normalized = InterfaceNormalizer.normalize(
            interface_name,
            platform=platform_enum,
            use_short_name=True
        )

        return normalized

    except Exception as e:
        logger.debug(f"Interface normalization failed for {interface_name}: {e}")
        return interface_name


class DrawpyoIconMapper:
    """Maps network devices to Draw.io icons using comprehensive JSON configuration"""

    def __init__(self, config_path: str = 'napalm_platform_icons.json'):
        self.config = self._load_config(config_path)
        self.priority_order = self.config.get('priority_order', [
            'platform_patterns', 'vendor_patterns', 'device_role_patterns',
            'hostname_patterns', 'fallback_patterns', 'defaults'
        ])

    def _load_config(self, config_path: str) -> Dict:
        """Load comprehensive icon configuration"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                logger.info(f"Loaded icon config with {len(config)} sections from {config_path}")
                return config
        except Exception as e:
            logger.warning(f"Could not load {config_path}: {e}")
            return self._get_fallback_config()

    def _get_fallback_config(self) -> Dict:
        """Fallback configuration if JSON file not available"""
        return {
            "platform_patterns": {
                "C9300": "shape=mxgraph.cisco.switches.layer_3_switch",
                "ISR4": "shape=mxgraph.cisco.routers.router",
                "Nexus": "shape=mxgraph.cisco.switches.nexus_7000"
            },
            "defaults": {
                "default_switch": "shape=mxgraph.cisco.switches.layer_3_switch",
                "default_router": "shape=mxgraph.cisco.routers.router",
                "default_unknown": "shape=rectangle"
            },
            "style_defaults": {
                "fillColor": "#036897",
                "strokeColor": "#ffffff",
                "strokeWidth": "2",
                "html": "1",
                "verticalLabelPosition": "bottom",
                "verticalAlign": "top",
                "align": "center",
                "aspect": "fixed"
            }
        }

    def get_device_style_string(self, node_id: str, platform: str = "",
                                vendor: str = "", device_role: str = "") -> str:
        """Get complete Draw.io style string using priority-based matching"""

        # Convert to lowercase for matching
        platform_lower = platform.lower() if platform else ""
        vendor_lower = vendor.lower() if vendor else ""
        node_id_lower = node_id.lower() if node_id else ""
        device_role_lower = device_role.lower() if device_role else ""

        # Find shape using priority order
        shape = None
        matched_section = None

        for section_name in self.priority_order:
            shape = self._check_section(section_name, node_id_lower, platform_lower,
                                        vendor_lower, device_role_lower)
            if shape:
                matched_section = section_name
                logger.debug(f"Icon match: {node_id} -> {shape} (from {section_name})")
                break

        if not shape:
            shape = "shape=rectangle"  # Ultimate fallback
            matched_section = "fallback"

        # Build complete style string
        style_defaults = self.config.get('style_defaults', {})
        style_parts = [shape]

        for key, value in style_defaults.items():
            style_parts.append(f"{key}={value}")

        return ";".join(style_parts)

    def _check_section(self, section_name: str, node_id: str, platform: str,
                       vendor: str, device_role: str) -> Optional[str]:
        """Check specific configuration section for matches"""
        section = self.config.get(section_name, {})

        if section_name == 'platform_patterns':
            return self._check_platform_patterns(section, platform)
        elif section_name == 'vendor_patterns':
            return self._check_vendor_patterns(section, vendor, platform)
        elif section_name == 'device_role_patterns':
            return self._check_device_role_patterns(section, device_role)
        elif section_name == 'hostname_patterns':
            return self._check_hostname_patterns(section, node_id)
        elif section_name == 'fallback_patterns':
            return self._check_fallback_patterns(section, node_id, platform, vendor)
        elif section_name == 'defaults':
            return self._check_defaults(section, platform, node_id)

        return None

    def _check_platform_patterns(self, patterns: Dict, platform: str) -> Optional[str]:
        """Check platform patterns for direct matches"""
        for pattern, shape in patterns.items():
            if pattern.lower() in platform:
                return shape
        return None

    def _check_vendor_patterns(self, patterns: Dict, vendor: str, platform: str) -> Optional[str]:
        """Check vendor-specific patterns"""
        for vendor_name, vendor_config in patterns.items():
            if vendor_name.lower() in vendor:
                if isinstance(vendor_config, dict):
                    # Check platform-specific mappings within vendor
                    for platform_key, shape in vendor_config.items():
                        if platform_key.lower() in platform:
                            return shape
                else:
                    return vendor_config
        return None

    def _check_device_role_patterns(self, patterns: Dict, device_role: str) -> Optional[str]:
        """Check device role patterns"""
        for role_pattern, shape in patterns.items():
            if role_pattern.lower() in device_role:
                return shape
        return None

    def _check_hostname_patterns(self, patterns: Dict, node_id: str) -> Optional[str]:
        """Check hostname patterns using configurable patterns"""
        for category, config in patterns.items():
            patterns_list = config.get('patterns', [])
            for pattern in patterns_list:
                if pattern.lower() in node_id:
                    return config.get('shape')
        return None

    def _check_fallback_patterns(self, patterns: Dict, node_id: str,
                                 platform: str, vendor: str) -> Optional[str]:
        """Check fallback patterns with multiple criteria"""
        for category, config in patterns.items():
            # Check platform patterns
            for pattern in config.get('platform_patterns', []):
                if pattern.lower() in platform:
                    return config.get('shape')

            # Check name patterns
            for pattern in config.get('name_patterns', []):
                if pattern.lower() in node_id:
                    return config.get('shape')

            # Check vendor patterns
            for pattern in config.get('vendor_patterns', []):
                if pattern.lower() in vendor:
                    return config.get('shape')

        return None

    def _check_defaults(self, defaults: Dict, platform: str, node_id: str) -> Optional[str]:
        """Apply defaults with educated guessing"""
        # Try platform-based guessing
        if any(term in platform for term in ['switch', 'nexus', 'catalyst']):
            return defaults.get('default_switch')
        elif any(term in platform for term in ['router', 'isr', 'asr']):
            return defaults.get('default_router')
        elif any(term in platform for term in ['firewall', 'asa', 'ftd']):
            return defaults.get('default_firewall')
        elif any(term in platform for term in ['phone', 'voip']):
            return defaults.get('default_phone')
        elif any(term in platform for term in ['server', 'virtual']):
            return defaults.get('default_server')
        else:
            return defaults.get('default_unknown')


class DrawpyoLayoutManager:
    """Layout manager using NetworkX algorithms for optimal positioning"""

    def __init__(self):
        # MAIN DISTANCE CONTROLS:
        self.scale_factor = 200  # ← OVERALL SCALE MULTIPLIER
        self.center_x = 500  # ← CENTER X COORDINATE
        self.center_y = 400  # ← CENTER Y COORDINATE

    def calculate_positions(self, topology_data: Dict, layout_type: str = 'hierarchical') -> Dict[str, Tuple[int, int]]:
        """Calculate node positions using NetworkX algorithms"""
        if not topology_data:
            return {}

        # Build NetworkX graph
        G = self._build_networkx_graph(topology_data)

        # Calculate positions based on layout type
        if layout_type == 'spring':
            positions = nx.spring_layout(G, k=self.scale_factor / 100, iterations=50)
        elif layout_type == 'circular':
            positions = nx.circular_layout(G)
        elif layout_type == 'shell':
            positions = nx.shell_layout(G)
        elif layout_type == 'kamada':
            positions = nx.kamada_kawai_layout(G)
        elif layout_type == 'star':
            positions = self._star_layout(G, topology_data)
        else:  # hierarchical (default)
            positions = self._hierarchical_layout(G, topology_data)

        # Scale and center positions
        return self._scale_positions(positions)

    def _build_networkx_graph(self, topology_data: Dict) -> nx.Graph:
        """Build NetworkX graph from topology data"""
        G = nx.Graph()

        # Add nodes with attributes
        for node_id, node_data in topology_data.items():
            node_details = node_data.get('node_details', {})
            G.add_node(node_id, **node_details)

        # Add edges
        for source_id, source_data in topology_data.items():
            for target_id in source_data.get('peers', {}):
                if target_id in topology_data:
                    G.add_edge(source_id, target_id)

        logger.info(f"Built NetworkX graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        return G

    def _hierarchical_layout(self, G: nx.Graph, topology_data: Dict) -> Dict:
        """Create hierarchical layout optimized for network topologies with proper spacing"""

        # Find root using multiple centrality measures
        centrality_scores = {}

        # Degree centrality (number of connections)
        degree_centrality = nx.degree_centrality(G)

        # Betweenness centrality (how often node appears on shortest paths)
        try:
            betweenness_centrality = nx.betweenness_centrality(G)
        except:
            betweenness_centrality = degree_centrality

        # Combine centrality measures with naming heuristics
        for node in G.nodes():
            score = 0

            # Centrality measures (weighted)
            score += degree_centrality.get(node, 0) * 100
            score += betweenness_centrality.get(node, 0) * 50

            # Naming heuristics (configurable boost)
            node_lower = node.lower()
            if 'core' in node_lower:
                score += 1000
            elif any(term in node_lower for term in ['spine', 'agg', 'main']):
                score += 500
            elif '01' in node:  # Primary device indicator
                score += 100

            centrality_scores[node] = score

        # Select root
        root = max(centrality_scores.items(), key=lambda x: x[1])[0]
        logger.info(f"Selected hierarchical root: {root} (score: {centrality_scores[root]:.2f})")

        # Create hierarchical layout using BFS tree with much better spacing
        try:
            positions = {}
            levels = {}

            # BFS to assign levels
            queue = [(root, 0)]
            visited = {root}

            while queue:
                node, level = queue.pop(0)
                if level not in levels:
                    levels[level] = []
                levels[level].append(node)

                # Sort neighbors for consistent ordering
                neighbors = sorted(G.neighbors(node), key=lambda x: (
                    'core' not in x.lower(),  # Core devices first
                    'swl' not in x.lower(),  # Then access switches
                    x.lower()  # Then alphabetical
                ))

                for neighbor in neighbors:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, level + 1))

            # Calculate positions with proper spacing for network topology
            max_nodes_in_level = max(len(nodes) for nodes in levels.values())

            # Adaptive spacing based on network size
            # NODE SPACING CONTROLS FOR HIERARCHICAL LAYOUT:
            if max_nodes_in_level <= 4:
                horizontal_spacing = 1.0  # ← HORIZONTAL GAP (SMALL NETWORKS)
                vertical_spacing = 0.8  # ← VERTICAL GAP (SMALL NETWORKS)
            elif max_nodes_in_level <= 8:
                horizontal_spacing = 0.7  # ← HORIZONTAL GAP (MEDIUM NETWORKS)
                vertical_spacing = 0.6  # ← VERTICAL GAP (MEDIUM NETWORKS)
            else:
                horizontal_spacing = 0.5  # ← HORIZONTAL GAP (LARGE NETWORKS)
                vertical_spacing = 0.5  # ← VERTICAL GAP (LARGE NETWORKS)

            for level, nodes in levels.items():
                y = level * vertical_spacing

                if len(nodes) == 1:
                    # Single node - center it
                    positions[nodes[0]] = (0, y)
                elif len(nodes) == 2:
                    # Two nodes - simple split
                    positions[nodes[0]] = (-horizontal_spacing / 2, y)
                    positions[nodes[1]] = (horizontal_spacing / 2, y)
                else:
                    # Multiple nodes - distribute evenly with extra spacing
                    total_width = (len(nodes) - 1) * horizontal_spacing
                    start_x = -total_width / 2

                    # Sort nodes for consistent positioning
                    sorted_nodes = sorted(nodes, key=lambda x: (
                        'core' not in x.lower(),
                        'swl' not in x.lower(),
                        x.lower()
                    ))

                    for i, node in enumerate(sorted_nodes):
                        x = start_x + (i * horizontal_spacing)
                        positions[node] = (x, y)

            return positions

        except Exception as e:
            logger.warning(f"Hierarchical layout failed: {e}, falling back to spring layout")
            return nx.spring_layout(G, k=0.8, iterations=50)

    def _star_layout(self, G: nx.Graph, topology_data: Dict) -> Dict:
        """Create star layout optimized for core-access topologies"""
        import math

        positions = {}

        # Find core switches (highly connected nodes)
        degree_dict = dict(G.degree())
        max_degree = max(degree_dict.values()) if degree_dict else 0

        # Identify core switches
        core_switches = []
        access_switches = []

        for node in G.nodes():
            node_lower = node.lower()
            degree = degree_dict[node]

            # Core if named "core" or has high connectivity
            if 'core' in node_lower or degree >= max_degree * 0.7:
                core_switches.append(node)
            else:
                access_switches.append(node)

        logger.info(f"Star layout: {len(core_switches)} core, {len(access_switches)} access switches")

        # Position core switches in center
        if len(core_switches) == 1:
            positions[core_switches[0]] = (0, 0)
        elif len(core_switches) == 2:
            positions[core_switches[0]] = (-0.3, 0)
            positions[core_switches[1]] = (0.3, 0)
        else:
            # Multiple cores in small circle
            for i, core in enumerate(core_switches):
                angle = 2 * math.pi * i / len(core_switches)
                x = 0.2 * math.cos(angle)
                y = 0.2 * math.sin(angle)
                positions[core] = (x, y)

        # Position access switches in arc/circle around cores
        if access_switches:
            radius = 1.0  # ← DISTANCE FROM CENTER TO ACCESS SWITCHES

            # Arrange in semicircle or full circle
            if len(access_switches) <= 6:
                # Semicircle for small numbers
                start_angle = -math.pi / 2
                end_angle = math.pi / 2
            else:
                # Full circle for many switches
                start_angle = 0
                end_angle = 2 * math.pi

            angle_step = (end_angle - start_angle) / max(len(access_switches) - 1, 1)

            for i, switch in enumerate(sorted(access_switches)):
                angle = start_angle + (i * angle_step)
                x = radius * math.cos(angle)
                y = radius * math.sin(angle)
                positions[switch] = (x, y)

        return positions

    def _scale_positions(self, positions: Dict) -> Dict[str, Tuple[int, int]]:
        """Scale NetworkX positions to Draw.io coordinates with generous spacing"""
        if not positions:
            return {}

        # Get coordinate bounds
        x_coords = [pos[0] for pos in positions.values()]
        y_coords = [pos[1] for pos in positions.values()]

        min_x, max_x = min(x_coords), max(x_coords)
        min_y, max_y = min(y_coords), max(y_coords)

        # Calculate scale to fit in much larger space (prevent overlap)
        x_range = max_x - min_x if max_x != min_x else 1
        y_range = max_y - min_y if max_y != min_y else 1

        # FINAL SCALING TO DRAW.IO COORDINATES:
        # Use much larger target area to prevent overlap
        target_width = 1600  # ← TOTAL DIAGRAM WIDTH (PIXELS)
        target_height = 1200  # ← TOTAL DIAGRAM HEIGHT (PIXELS)

        x_scale = target_width / x_range
        y_scale = target_height / y_range
        scale = min(x_scale, y_scale) * 0.9  # Use 90% to add margins

        # Ensure minimum spacing between nodes
        min_spacing = 150  # ← MINIMUM PIXELS BETWEEN ANY TWO NODES
        if scale < min_spacing:
            scale = min_spacing

        # Scale and center positions
        scaled_positions = {}
        for node, (x, y) in positions.items():
            scaled_x = int(self.center_x + (x - min_x - x_range / 2) * scale)
            scaled_y = int(self.center_y + (y - min_y - y_range / 2) * scale)
            scaled_positions[node] = (scaled_x, scaled_y)

        return scaled_positions


class DrawpyoNetworkExporter:
    """Main exporter class using drawpyo library with JSON icon mapping"""

    def __init__(self, config_path: str = 'napalm_platform_icons.json'):
        if not DRAWPYO_AVAILABLE:
            raise ImportError("drawpyo library not available. Install with: pip install drawpyo networkx")

        self.icon_mapper = DrawpyoIconMapper(config_path)
        self.layout_manager = DrawpyoLayoutManager()

    def export_topology(self, topology_data: Dict,
                        layout_type: str = 'hierarchical',
                        include_endpoints: bool = True,
                        output_path: Optional[str] = None) -> Path:
        """Export network topology to Draw.io format using drawpyo"""

        try:
            logger.info(f"Starting drawpyo export: {len(topology_data)} devices, layout={layout_type}")

            # Validate and filter topology
            filtered_topology = self._filter_topology(topology_data, include_endpoints)
            logger.info(f"After filtering: {len(filtered_topology)} devices")

            if not filtered_topology:
                raise ValueError("No devices to export after filtering")

            # Calculate positions
            positions = self.layout_manager.calculate_positions(filtered_topology, layout_type)
            logger.info(f"Calculated positions for {len(positions)} devices")

            # Create drawpyo file
            return self._create_drawpyo_diagram(filtered_topology, positions, output_path)

        except Exception as e:
            logger.error(f"Export failed: {e}", exc_info=True)
            raise

    def _filter_topology(self, topology_data: Dict, include_endpoints: bool) -> Dict:
        """Filter topology data if requested"""
        if include_endpoints:
            return topology_data

        # Network devices appear as both sources and peers
        all_sources = set(topology_data.keys())
        all_peers = set()

        for device_data in topology_data.values():
            all_peers.update(device_data.get('peers', {}).keys())

        network_devices = all_sources.intersection(all_peers)
        logger.info(f"Network-only filter: {len(network_devices)} of {len(all_sources)} devices")

        # Keep only network devices
        filtered = {}
        for device_id in network_devices:
            if device_id in topology_data:
                device_data = topology_data[device_id].copy()
                # Only keep peer connections to other network devices
                device_data['peers'] = {
                    peer_id: peer_data
                    for peer_id, peer_data in device_data.get('peers', {}).items()
                    if peer_id in network_devices
                }
                filtered[device_id] = device_data

        return filtered

    def _create_drawpyo_diagram(self, topology_data: Dict,
                                positions: Dict[str, Tuple[int, int]],
                                output_path: Optional[str] = None) -> Path:
        """Create the actual Draw.io diagram using drawpyo"""

        # Create file and page
        file = drawpyo.File()

        if output_path:
            output_path = Path(output_path)
            file.file_path = str(output_path.parent)
            file.file_name = output_path.name
        else:
            # Generate timestamp-based filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_dir = Path(tempfile.gettempdir()) / 'rapidcmdb_exports'
            temp_dir.mkdir(exist_ok=True)

            file.file_path = str(temp_dir)
            file.file_name = f"network_topology_{timestamp}.drawio"

        # Create page
        page = drawpyo.Page(file=file)
        page.page_name = "Network Topology"

        # Add nodes
        drawpyo_objects = {}

        for node_id, (x, y) in positions.items():
            if node_id in topology_data:
                node_data = topology_data[node_id]

                # Create node label
                label = self._create_node_label(node_id, node_data)

                # Get style using JSON mapping
                node_details = node_data.get('node_details', {})
                style_string = self.icon_mapper.get_device_style_string(
                    node_id,
                    platform=node_details.get('platform', ''),
                    vendor=node_details.get('vendor', ''),
                    device_role=node_details.get('device_role', '')
                )

                # Create drawpyo object
                obj = drawpyo.diagram.Object(page=page, value=label)
                obj.position = (x, y)
                obj.size = (80, 80)

                # Apply style from JSON mapping
                obj.apply_style_string(style_string)

                drawpyo_objects[node_id] = obj

                logger.debug(f"Added node: {node_id} at ({x}, {y}) with style: {style_string[:50]}...")

        # Add edges with comprehensive connection handling (like manual exporter)
        added_edges = set()

        for source_id, source_data in topology_data.items():
            if source_id not in drawpyo_objects:
                continue

            peers = source_data.get('peers', {})
            for target_id, peer_data in peers.items():
                if target_id not in drawpyo_objects:
                    continue

                # Get all connections for this peer relationship
                connections = peer_data.get('connections', [])

                # Process each connection individually (like manual exporter)
                for connection in connections:
                    # Create unique edge identifier per connection
                    if len(connection) >= 2:
                        edge_key = (source_id, target_id, connection[0], connection[1])
                    else:
                        edge_key = (source_id, target_id, "unknown", "unknown")

                    # Skip if we've already added this exact connection
                    if edge_key in added_edges:
                        continue
                    added_edges.add(edge_key)

                    # Create normalized edge label
                    if len(connection) >= 2:
                        # Get vendor/platform info for normalization
                        source_details = topology_data[source_id].get('node_details', {})
                        target_details = peer_data

                        source_vendor = source_details.get('vendor', '')
                        source_platform = source_details.get('platform', '')
                        target_vendor = target_details.get('vendor', '')
                        target_platform = target_details.get('platform', '')

                        # Normalize interface names
                        norm_source_int = normalize_interface_name(
                            connection[0], source_vendor, source_platform
                        )
                        norm_target_int = normalize_interface_name(
                            connection[1], target_vendor, target_platform
                        )

                        edge_label = f"{norm_source_int} - {norm_target_int}"
                    else:
                        edge_label = ""

                    # Create drawpyo edge with straight line style
                    edge = drawpyo.diagram.Edge(
                        page=page,
                        source=drawpyo_objects[source_id],
                        target=drawpyo_objects[target_id],
                        value=edge_label
                    )

                    # Apply completely straight line style (FORCE no orthogonal routing)
                    edge.apply_style_string(
                        "strokeWidth=2;"  # Line thickness
                        "strokeColor=#666666;"  # Line color  
                        "fontColor=#333333;"  # Label color
                        "fontSize=10;"  # Label size
                        "html=1;"  # HTML rendering
                        "labelBackgroundColor=none;"  # Transparent label background
                        "endArrow=none;"  # No arrows
                        "startArrow=none;"  # No arrows
                        "exitX=0.5;exitY=0.5;"  # Exit from center of source
                        "entryX=0.5;entryY=0.5;"  # Enter at center of target
                        "edge=1;"  # Mark as edge
                    )

                    logger.debug(
                        f"Added edge: {source_id}:{connection[0] if len(connection) >= 1 else 'unknown'} -> {target_id}:{connection[1] if len(connection) >= 2 else 'unknown'}")

        logger.info(f"Added {len(added_edges)} total connections to diagram")

        # Write file
        file.write()

        output_file_path = Path(file.file_path) / file.file_name
        logger.info(f"Successfully created Draw.io file: {output_file_path}")

        return output_file_path

    def _create_node_label(self, node_id: str, node_data: Dict) -> str:
        """Create informative node label"""
        node_details = node_data.get('node_details', {})

        parts = [node_id]

        # Add IP if available
        ip = node_details.get('ip', '')
        if ip:
            parts.append(ip)

        # Add platform (truncated if too long)
        platform = node_details.get('platform', '')
        if platform:
            if len(platform) > 25:
                platform = platform[:22] + "..."
            parts.append(platform)

        return "\n".join(parts)


# Factory function for easy integration
def create_drawpyo_exporter(config_path: str = 'napalm_platform_icons.json') -> DrawpyoNetworkExporter:
    """Factory function to create drawpyo-based exporter"""
    return DrawpyoNetworkExporter(config_path)


# Example usage and integration helper
def integrate_with_existing_api(topology_data: Dict, config: Dict) -> Path:
    """
    Helper function to integrate with existing RapidCMDB API

    Args:
        topology_data: The topology map from build_topology_map()
        config: Configuration dict with layout, network_only, etc.

    Returns:
        Path to generated Draw.io file
    """
    try:
        exporter = create_drawpyo_exporter()

        layout_mapping = {
            'tree': 'hierarchical',
            'TD': 'hierarchical',
            'LR': 'hierarchical',
            'spring': 'spring',
            'circular': 'circular',
            'grid': 'spring'  # Grid maps to spring for better distribution
        }

        layout_type = layout_mapping.get(config.get('layout', 'tree'), 'hierarchical')
        include_endpoints = not config.get('network_only', False)

        return exporter.export_topology(
            topology_data,
            layout_type=layout_type,
            include_endpoints=include_endpoints
        )

    except ImportError:
        logger.error("drawpyo not available, falling back to manual XML export")
        # Could fall back to your existing exporter here
        raise