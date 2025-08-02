import argparse
import json
import os
import xml.sax.saxutils as saxutils
from N2G import drawio_diagram, yed_diagram
import logging

logger = logging.getLogger(__name__)


def strip_domain(node_id):
    """Utility to strip the domain part of the node identifier."""
    return node_id.split('.')[0]


def preprocess_data(data):
    """Process the network data to enrich node_details using discovered CDP data from peers."""
    node_details_map = {}

    # First pass: Collect detailed info from peers
    for node, info in data.items():
        node_details = info.get('node_details', {})
        if node_details.get('ip') == 'Unknown':
            # Check all nodes to find matching peer details
            for check_node, check_info in data.items():
                for peer_id, peer_info in check_info.get('peers', {}).items():
                    if peer_id == node:
                        node_details_map[node] = {
                            'ip': peer_info.get('ip'),
                            'platform': peer_info.get('platform')
                        }

    # Second pass: Update top-level nodes with enhanced details from peers if they're more informative
    for node, info in data.items():
        node_details = info.get('node_details', {})
        if node in node_details_map:
            better_details = node_details_map[node]
            if better_details.get('ip') != 'Unknown':
                node_details['ip'] = "-\n" + better_details['ip']
            if better_details.get('platform') != 'Unknown Platform':
                node_details['platform'] = "-\n" +better_details['platform']
        data[node]['node_details'] = node_details

    return data


def create_network_diagrams(json_file, output_dir, map_name, layout_algo="kk"):
    """
    Generate network diagrams from a JSON network map with guaranteed unique edges
    and complete node details.

    :param json_file: Path to the JSON file containing the network data
    :param output_dir: Directory to save the generated diagrams
    :param map_name: Name of the output map
    :param layout_algo: Graph layout algorithm to apply
    """
    drawio_filename = f"{map_name}.drawio"
    graphml_filename = f"{map_name}.graphml"

    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Load and preprocess JSON data
    with open(json_file, 'r') as file:
        data = json.load(file)
        data = preprocess_data(data)

    # Save the processed data for inspection (optional)
    processed_json_path = os.path.join(output_dir, f"{map_name}_processed.json")
    with open(processed_json_path, "w") as fh:
        json.dump(data, fh, indent=2)

    # Initialize edge tracking set and diagrams
    edges = set()
    yed = yed_diagram()
    drawio = drawio_diagram()
    drawio.add_diagram("Page-1")

    # First pass - Add all nodes with complete details
    for node, info in data.items():
        if "unknown" not in node.lower():
            node_details = info.get('node_details', {})
            hostname = node.strip()
            ip_addr = node_details.get('ip', 'Unknown IP').strip()
            platform = node_details.get('platform', '').strip()

            # Format labels to include all relevant information
            top_label = hostname
            if platform:
                main_label = f"{hostname}\n{platform}"
            else:
                main_label = hostname

            # Add nodes to yEd with complete formatting
            yed.add_node(
                id=node,
                label=main_label,
                bottom_label=ip_addr,
                bottom_label_style="fill: #0000FF;color: #FFFFFF",
                margin_bottom=20
            )

            # Add nodes to DrawIO with complete formatting
            drawio.add_node(
                id=node,
                label=main_label,
                bottom_label=ip_addr,
                bottom_label_style="fillColor=#0000FF;fontColor=#FFFFFF;spacingTop=20"
            )

    def get_canonical_edge_key(n1, n2, p1, p2):
        """
        Create a canonical edge key that's consistent regardless of direction.
        Sort node names and their corresponding ports together.
        """
        if n1 < n2:
            return (n1, n2, p1, p2)
        return (n2, n1, p2, p1)

    # Second pass - Add links with robust duplicate detection
    processed_connections = set()

    for node, info in data.items():
        if "unknown" not in node.lower():
            for peer_id, peer_info in info.get('peers', {}).items():
                # Skip if we've already processed this node pair
                node_pair = tuple(sorted([node, peer_id]))
                if node_pair in processed_connections:
                    continue

                # Mark this node pair as processed
                processed_connections.add(node_pair)

                # Process all connections between these nodes
                for connection in peer_info.get('connections', []):
                    local_port, remote_port = connection

                    # Create canonical edge key
                    edge_key = get_canonical_edge_key(node, peer_id, local_port, remote_port)

                    # Only add if we haven't seen this exact edge before
                    if edge_key not in edges:
                        edges.add(edge_key)

                        # Get canonical source, target, and port labels
                        source, target, src_port, trgt_port = edge_key

                        # Add links to both diagrams with complete port information
                        yed.add_link(
                            source=source,
                            target=target,
                            src_label=saxutils.escape(src_port),
                            trgt_label=saxutils.escape(trgt_port)
                        )

                        drawio.add_link(
                            source=source,
                            target=target,
                            src_label=saxutils.escape(src_port),
                            trgt_label=saxutils.escape(trgt_port)
                        )

    # Apply layout and save diagrams
    yed.layout(algo=layout_algo)
    yed.dump_file(filename=graphml_filename, folder=output_dir)

    drawio.layout(algo=layout_algo)
    drawio.dump_file(filename=drawio_filename, folder=output_dir)

    logger.info(f"Created network diagrams: {graphml_filename} and {drawio_filename}")

def main():
    parser = argparse.ArgumentParser(description="Generate network diagrams from a JSON file.")
    parser.add_argument('-json', '--json-file', required=True, help='Path to the input JSON file')
    parser.add_argument('-o', '--output-dir', required=True, help='Directory to write output files')
    parser.add_argument('-n', '--map-name', required=True, help='Name for the generated map (used for file names)')

    args = parser.parse_args()

    create_network_diagrams(
        json_file=args.json_file,
        output_dir=args.output_dir,
        map_name=args.map_name
    )


if __name__ == "__main__":
    main()