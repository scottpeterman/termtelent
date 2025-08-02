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

class DrawioLayoutManager:
    def __init__(self, layout_type: str = 'tree'):
        self.layout_type = layout_type
        self.vertical_spacing = 150  # Vertical space between levels
        self.horizontal_spacing = 200  # Horizontal space between nodes
        self.start_y = 350  # Center Y coordinate for balloon layout
        self.start_x = 1000  # Center X coordinate for balloon layout
        self.balloon_radius = 300  # Base radius for balloon layout
        self.balloon_ring_spacing = 200  # Spacing between concentric rings

    def get_node_positions(self, network_data: Dict, edges: List[Tuple[str, str]]) -> Dict[str, Tuple[int, int]]:
        """Main entry point for calculating node positions based on layout type"""
        if not network_data:
            return {}

        if self.layout_type == 'tree':
            return self.calculate_tree_layout(network_data, edges)
        elif self.layout_type == 'balloon':
            return self.calculate_balloon_layout(network_data, edges)
        else:
            return self.calculate_tree_layout(network_data, edges)  # Default to tree layout

    def calculate_tree_layout(self, network_data: Dict, edges: List[Tuple[str, str]]) -> Dict[str, Tuple[int, int]]:
        """Calculate node positions using a hierarchical tree layout"""
        positions = {}

        # Build adjacency list representation
        adjacency = defaultdict(list)
        for source, target in edges:
            adjacency[source].append(target)
            adjacency[target].append(source)  # Bidirectional

        # Find root node (node with most connections or specified pattern)
        root = self._find_root_node(network_data, adjacency)

        # Build tree structure using BFS
        tree_levels = self._build_tree_levels(root, adjacency)

        # Calculate positions level by level
        self._assign_tree_positions(tree_levels, positions)

        return positions

    def calculate_balloon_layout(self, network_data: Dict, edges: List[Tuple[str, str]]) -> Dict[str, Tuple[int, int]]:
        """Calculate node positions using a balloon/radial layout"""
        positions = {}

        # Build adjacency list
        adjacency = defaultdict(list)
        for source, target in edges:
            adjacency[source].append(target)
            adjacency[target].append(source)

        # Find central node (prefer core switch or most connected)
        center_node = self._find_root_node(network_data, adjacency)

        # Build rings of nodes using BFS
        rings = self._build_rings(center_node, adjacency)

        # Position the center node
        positions[center_node] = (self.start_x, self.start_y)

        # Position nodes in each ring
        for ring_idx, ring_nodes in enumerate(rings):
            if not ring_nodes:
                continue

            # Calculate radius for this ring
            radius = self.balloon_radius + (ring_idx * self.balloon_ring_spacing)

            # Position nodes around the circle
            for idx, node in enumerate(sorted(ring_nodes)):
                angle = (2 * math.pi * idx) / len(ring_nodes)
                x = self.start_x + int(radius * math.cos(angle))
                y = self.start_y + int(radius * math.sin(angle))
                positions[node] = (x, y)

        return positions

    def _build_tree_levels(self, root: str, adjacency: Dict) -> Dict[int, List[str]]:
        """Build tree levels using BFS with improved ordering"""
        levels = defaultdict(list)
        visited = {root}
        queue = [(root, 0)]
        levels[0].append(root)

        while queue:
            node, level = queue.pop(0)
            # Sort neighbors to ensure consistent ordering
            neighbors = sorted(adjacency[node], key=lambda x: (
                'usa1' in x.lower(),  # USA1 nodes first
                'core' in x.lower(),  # Then core devices
                'access' in x.lower(),  # Then access devices
                'rtr' in x.lower(),  # Then routers
                x.lower()  # Finally alphabetical
            ), reverse=True)

            for neighbor in neighbors:
                if neighbor not in visited:
                    visited.add(neighbor)
                    levels[level + 1].append(neighbor)
                    queue.append((neighbor, level + 1))

        return levels

    def _build_rings(self, center_node: str, adjacency: Dict) -> List[set]:
        """Build concentric rings of nodes around the center"""
        rings = []
        visited = {center_node}
        current_ring = set()
        queue = [(center_node, 0)]
        current_level = 0

        while queue:
            node, level = queue.pop(0)

            # If we've moved to a new level, store the current ring and start a new one
            if level > current_level:
                if current_ring:
                    rings.append(current_ring)
                current_ring = set()
                current_level = level

            # Add neighbors to the next ring
            for neighbor in sorted(adjacency[node]):
                if neighbor not in visited:
                    current_ring.add(neighbor)
                    visited.add(neighbor)
                    queue.append((neighbor, level + 1))

        # Add the last ring if it's not empty
        if current_ring:
            rings.append(current_ring)

        return rings

    def _assign_tree_positions(self, tree_levels: Dict[int, List[str]], positions: Dict[str, Tuple[int, int]]) -> None:
        """Assign x,y coordinates to nodes based on their level in the tree"""
        # Find maximum width needed
        max_width = max(len(nodes) for nodes in tree_levels.values())
        level_adjustments = {  # Fine-tune level spacing
            0: 0,  # Root level
            1: 1.2,  # First level wider spacing
            2: 1.5,  # Second level even wider
            3: 2,  # Third level widest
        }

        for level, nodes in tree_levels.items():
            # Calculate y coordinate for this level
            y = self.start_y + (level * self.vertical_spacing)

            # Calculate x coordinates with level-specific spacing
            adjustment = level_adjustments.get(level, 2)  # Default to 2 for deeper levels
            level_width = (len(nodes) - 1) * (self.horizontal_spacing * adjustment)
            start_x = self.start_x - (level_width / 2)

            for idx, node in enumerate(sorted(nodes)):
                x = start_x + (idx * (self.horizontal_spacing * adjustment))
                positions[node] = (int(x), int(y))

    def _find_root_node(self, network_data: Dict, adjacency: Dict) -> str:
        """Find the root/center node for the layout"""
        # First try to find a core switch
        for node_id in network_data:
            if '-core-01' in node_id.lower() and 'usa1' in node_id.lower():
                return node_id

        # Otherwise, use node with most connections
        return max(adjacency.items(), key=lambda x: len(x[1]))[0]

    def get_edge_style(self) -> str:
        """Get edge style string for diagram edges"""
        return "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;noEdgeStyle=1"

    def get_edge_attributes(self) -> Dict[str, str]:
        """Get additional edge attributes that need to be set on the cell"""
        return {
            "noEdgeStyle": "1",
            "edge": "1"
        }

    def get_label_style(self, is_source: bool = False) -> Dict[str, str]:
        """Get consistent label styling for port labels"""
        return {
            "labelBackgroundColor": "none",
            "labelBorderColor": "none",
            "verticalLabelPosition": "middle",
            "verticalAlign": "middle",
            "align": "center",
            "fontSize": "11",
            "fontFamily": "Helvetica",
            "spacing": "2",
            "spacingLeft": "2",
            "spacingRight": "2",
            "spacingTop": "2",
            "spacingBottom": "2",
            "horizontal": "1",
            "position": "0.5"
        }
