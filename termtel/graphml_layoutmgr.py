from typing import Dict, Tuple, List
import math


class LayoutManager:
    def __init__(self, layout_type: str = "grid"):
        self.layout_type = layout_type
        self.node_positions: Dict[str, Tuple[float, float]] = {}
        self.processed_nodes: List[str] = []

    def calculate_position(self, node_id: str, node_data: dict, topology: dict, idx: int) -> Tuple[float, float]:
        if self.layout_type == "grid":
            return self._grid_layout(idx)
        elif self.layout_type == "directed_tree":
            return self._directed_tree_layout(node_id, node_data, topology)
        elif self.layout_type == "balloon":
            return self._balloon_layout(node_id, node_data, topology, idx)
        else:
            return self._grid_layout(idx)  # Default to grid

    def _grid_layout(self, idx: int) -> Tuple[float, float]:
        """Basic grid layout with fixed spacing"""
        x = 200 + (idx % 3) * 200
        y = 100 + (idx // 3) * 150
        return (x, y)

    def _directed_tree_layout(self, node_id: str, node_data: dict, topology: dict) -> Tuple[float, float]:
        """Hierarchical tree layout from top to bottom"""
        if node_id in self.node_positions:
            return self.node_positions[node_id]

        # Find root nodes (typically core switches)
        is_root = not any(node_id in peer_data['peers']
                          for other_node, peer_data in topology.items()
                          if other_node != node_id and 'peers' in peer_data)

        level = 0
        if not is_root:
            # Calculate level based on distance from root
            level = self._calculate_level(node_id, topology)

        # Calculate horizontal position based on siblings at same level
        siblings = self._get_siblings_at_level(node_id, level, topology)
        position_in_level = siblings.index(node_id)
        total_in_level = len(siblings)

        # Calculate coordinates
        y = level * 150  # Vertical spacing between levels
        x = (position_in_level - (total_in_level - 1) / 2) * 200  # Center nodes horizontally

        self.node_positions[node_id] = (x, y)
        return (x, y)

    def _balloon_layout(self, node_id: str, node_data: dict, topology: dict, idx: int) -> Tuple[float, float]:
        """Balloon/Radial layout with root node in center"""
        if node_id in self.node_positions:
            return self.node_positions[node_id]

        # Find root node (typically core switch)
        if idx == 0 or self._is_root_node(node_id, topology):
            # Place root node at center
            pos = (500, 500)  # Center coordinates
            self.node_positions[node_id] = pos
            return pos

        # Get parent node
        parent = self._find_parent(node_id, topology)
        if not parent:
            # No parent found, use default position
            return self._grid_layout(idx)

        # Calculate position in circular layout around parent
        children = self._get_children(parent, topology)
        child_count = len(children)
        child_idx = children.index(node_id)

        # Calculate radius based on number of children
        radius = 150 + (50 * len(self._get_children(node_id, topology)))  # Larger radius for nodes with more children
        angle = (2 * math.pi * child_idx) / child_count

        parent_x, parent_y = self.node_positions[parent]
        x = parent_x + radius * math.cos(angle)
        y = parent_y + radius * math.sin(angle)

        self.node_positions[node_id] = (x, y)
        return (x, y)

    def _calculate_level(self, node_id: str, topology: dict) -> int:
        """Calculate the level of a node in the hierarchy"""
        level = 0
        current = node_id
        visited = set()

        while current and current not in visited:
            visited.add(current)
            parent = self._find_parent(current, topology)
            if parent:
                level += 1
                current = parent
            else:
                break

        return level

    def _get_siblings_at_level(self, node_id: str, level: int, topology: dict) -> List[str]:
        """Get all nodes at the same level"""
        siblings = []
        for other_id in topology.keys():
            if self._calculate_level(other_id, topology) == level:
                siblings.append(other_id)
        return sorted(siblings)

    def _is_root_node(self, node_id: str, topology: dict) -> bool:
        """Determine if a node is a root node"""
        return 'core' in node_id.lower() or not any(
            node_id in peer_data.get('peers', {})
            for other_node, peer_data in topology.items()
            if other_node != node_id
        )

    def _find_parent(self, node_id: str, topology: dict) -> str:
        """Find the parent node in the topology"""
        for parent_id, parent_data in topology.items():
            if parent_id != node_id and 'peers' in parent_data:
                if node_id in parent_data['peers']:
                    return parent_id
        return None

    def _get_children(self, node_id: str, topology: dict) -> List[str]:
        """Get all child nodes for a given node"""
        children = []
        if node_id in topology and 'peers' in topology[node_id]:
            children.extend(topology[node_id]['peers'].keys())
        return children