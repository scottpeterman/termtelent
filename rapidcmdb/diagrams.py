import json
import os
import xml.sax.saxutils as saxutils
from N2G import drawio_diagram, yed_diagram

def create_network_diagrams(json_data, output_dir, map_name, layout_algo="kk"):
    """
    Generate network diagrams from a JSON network map with guaranteed unique edges
    and complete node details.
    """
    drawio_filename = f"{map_name}.drawio"
    graphml_filename = f"{map_name}.graphml"

    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Initialize edge tracking set and diagrams
    edges = set()
    yed = yed_diagram()
    drawio = drawio_diagram()
    drawio.add_diagram("Page-1")

    # First pass - Add all nodes with complete details
    for node, info in json_data.items():
        if "unknown" not in node.lower():
            node_details = info.get('node_details', {})
            hostname = node.strip()
            ip_addr = node_details.get('ip', 'Unknown IP').strip()
            platform = node_details.get('platform', '').strip()

            # Format labels to include all relevant information
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
        if n1 < n2:
            return (n1, n2, p1, p2)
        return (n2, n1, p2, p1)

    # Second pass - Add links
    processed_connections = set()

    for node, info in json_data.items():
        if "unknown" not in node.lower():
            for peer_id, peer_info in info.get('peers', {}).items():
                node_pair = tuple(sorted([node, peer_id]))
                if node_pair in processed_connections:
                    continue

                processed_connections.add(node_pair)

                for connection in peer_info.get('connections', []):
                    local_port, remote_port = connection
                    edge_key = get_canonical_edge_key(node, peer_id, local_port, remote_port)

                    if edge_key not in edges:
                        edges.add(edge_key)
                        source, target, src_port, trgt_port = edge_key

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