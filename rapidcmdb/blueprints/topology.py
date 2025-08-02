#!/usr/bin/env python3
"""
Network Topology Blueprint - LLDP-based topology visualization with interface normalization
Provides API endpoints and web interface for network topology viewing
"""

from flask import Blueprint, jsonify, request, send_file
import sqlite3
import re
from collections import defaultdict
from datetime import datetime
import logging
import json
import os
from pathlib import Path

# Import the enhanced interface normalizer
from .enh_int_normalizer import InterfaceNormalizer, Platform

# Import the new Draw.io exporter libraries
from .drawio_mapper2 import NetworkDrawioExporter
from .drawio_layoutmanager import DrawioLayoutManager

topology_bp = Blueprint('topology', __name__, template_folder='../templates')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Get database connection with row factory"""
    conn = sqlite3.connect('napalm_cmdb.db')
    conn.row_factory = sqlite3.Row
    return conn


# Add this import at the top of your topology.py file, along with other imports
from .json_topology_exporter import JSONTopologyExporter


# Add this new API endpoint function to your topology.py file


@topology_bp.route('/api/topology/export/json/sample')
def api_json_export_sample():
    """Provide a sample of the JSON export format for documentation"""
    try:
        from .json_topology_exporter import create_sample_topology

        sample_topology = create_sample_topology()
        exporter = JSONTopologyExporter(include_metadata=True, pretty_print=True)

        converted_topology = exporter.convert_topology_map(sample_topology)
        final_data = exporter.add_export_metadata(converted_topology)
        final_data = converted_topology
        return jsonify({
            'success': True,
            'sample_topology': final_data,
            'description': 'Sample topology in standard JSON format',
            'usage': {
                'export_endpoint': '/api/topology/export/json',
                'parameters': {
                    'sites': 'List of site codes to include',
                    'network_only': 'Boolean - include only network devices',
                    'include_metadata': 'Boolean - include export metadata',
                    'pretty_print': 'Boolean - format JSON for readability',
                    'download_file': 'Boolean - return as file download'
                },
                'examples': {
                    'json_response': '/api/topology/export/json?sites=FRS&network_only=true',
                    'file_download': '/api/topology/export/json?sites=FRS&download_file=true',
                    'minimal': '/api/topology/export/json?include_metadata=false&pretty_print=false'
                }
            }
        })

    except Exception as e:
        logger.error(f"Error generating sample JSON export: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def execute_query(query, params=None):
    """Execute query and return results with error handling"""
    conn = get_db_connection()
    try:
        if params:
            cursor = conn.execute(query, params)
        else:
            cursor = conn.execute(query)
        results = cursor.fetchall()
        return [dict(row) for row in results]
    except Exception as e:
        logger.error(f"Database error in query '{query[:50]}...': {e}")
        return []
    finally:
        conn.close()


def normalize_hostname(hostname):
    """Clean up hostname - remove domain suffixes, handle empty values"""
    if not hostname or not hostname.strip():
        return ""

    # Remove common domain suffixes (case insensitive)
    name = hostname.strip()

    # Common domain patterns to strip
    domain_patterns = [
        '.local', '.corp', '.lan', '.domain.com', '.company.com',
        '.internal', '.priv', '.private', '.columbia.csc'
    ]

    # First, try specific known patterns
    name_lower = name.lower()
    for suffix in domain_patterns:
        if name_lower.endswith(suffix.lower()):
            name = name[:-len(suffix)]
            break

    # Then try to catch any remaining FQDN pattern (.domain.tld)
    fqdn_pattern = r'\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$'
    name = re.sub(fqdn_pattern, '', name)

    # Also handle single domain suffixes that we might have missed
    if not re.match(r'^\d+\.\d+\.\d+\.\d+$', name):  # Not an IP
        single_domain_pattern = r'\.[a-zA-Z0-9-]+$'
        # Only strip if it looks like a domain (not a numbered interface)
        if re.search(r'\.[a-zA-Z][a-zA-Z0-9-]*$', name):
            name = re.sub(single_domain_pattern, '', name)

    return name


def map_vendor_to_platform(vendor):
    """Map vendor string to Platform enum for interface normalization"""
    if not vendor:
        return None

    vendor_lower = vendor.lower()
    vendor_mapping = {
        'cisco': Platform.CISCO_IOS,
        'cisco systems': Platform.CISCO_IOS,
        'arista': Platform.ARISTA,
        'arista networks': Platform.ARISTA,
    }

    # Check for NX-OS indicators
    if 'nexus' in vendor_lower or 'nx-os' in vendor_lower:
        return Platform.CISCO_NXOS

    return vendor_mapping.get(vendor_lower, Platform.UNKNOWN)


def normalize_interface_pair(local_interface, remote_interface, local_vendor=None, remote_vendor=None):
    """Normalize a pair of interfaces with platform-aware normalization"""
    local_platform = map_vendor_to_platform(local_vendor)
    remote_platform = map_vendor_to_platform(remote_vendor)

    # Normalize both interfaces
    normalized_local = InterfaceNormalizer.normalize(
        local_interface,
        platform=local_platform,
        use_short_name=True
    )

    normalized_remote = InterfaceNormalizer.normalize(
        remote_interface,
        platform=remote_platform,
        use_short_name=True
    )

    return normalized_local, normalized_remote


def build_platform_string(vendor, model):
    """Build platform string from vendor and model"""
    if not vendor and not model:
        return ""
    elif vendor and model:
        return f"{vendor} {model}"
    elif vendor:
        return vendor
    else:
        return model or ""


def get_latest_lldp_data(include_patterns=None, exclude_patterns=None, sites=None, roles=None):
    """Get the latest LLDP data with optional filtering"""
    base_query = """
    SELECT 
        d.device_name,
        d.hostname,
        di.ip_address as device_ip,
        d.vendor,
        d.model,
        d.site_code,
        d.device_role,
        ln.local_interface,
        ln.remote_hostname,
        ln.remote_port,
        ln.remote_mgmt_ip,
        ln.remote_system_description,
        cr.collection_time,
        -- Get remote device vendor for interface normalization
        rd.vendor as remote_vendor,
        rd.model as remote_model
    FROM lldp_neighbors ln
    JOIN devices d ON ln.device_id = d.id
    LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
    -- Join to get remote device info for interface normalization
    LEFT JOIN devices rd ON UPPER(TRIM(rd.device_name)) = UPPER(TRIM(ln.remote_hostname)) 
                         OR UPPER(TRIM(rd.hostname)) = UPPER(TRIM(ln.remote_hostname))
    JOIN (
        -- Get latest collection run per device
        SELECT device_id, MAX(collection_time) as max_time
        FROM collection_runs
        WHERE success = 1
        GROUP BY device_id
    ) latest ON ln.device_id = latest.device_id
    JOIN collection_runs cr ON ln.collection_run_id = cr.id 
        AND cr.collection_time = latest.max_time
    WHERE d.is_active = 1
    """

    conditions = []
    params = []

    # Add include patterns
    if include_patterns:
        include_conditions = []
        for pattern in include_patterns:
            include_conditions.append("(d.device_name LIKE ? OR d.hostname LIKE ?)")
            params.extend([f"%{pattern}%", f"%{pattern}%"])
        conditions.append(f"({' OR '.join(include_conditions)})")

    # Add exclude patterns
    if exclude_patterns:
        for pattern in exclude_patterns:
            conditions.append("(d.device_name NOT LIKE ? AND d.hostname NOT LIKE ?)")
            params.extend([f"%{pattern}%", f"%{pattern}%"])

    # Add site filter
    if sites:
        site_conditions = []
        for site in sites:
            site_conditions.append("UPPER(d.site_code) = UPPER(?)")
            params.append(site)
        conditions.append(f"({' OR '.join(site_conditions)})")

    # Add role filter
    if roles:
        role_conditions = []
        for role in roles:
            role_conditions.append("d.device_role = ?")
            params.append(role)
        conditions.append(f"({' OR '.join(role_conditions)})")

    # Build final query
    if conditions:
        query = base_query + " AND " + " AND ".join(conditions)
    else:
        query = base_query

    query += " ORDER BY d.device_name, ln.local_interface"

    return execute_query(query, params)


def get_device_details(include_patterns=None, exclude_patterns=None, sites=None, roles=None):
    """Get basic device details for node_details section with filtering"""
    base_query = """
    SELECT 
        d.device_name,
        d.hostname,
        di.ip_address,
        d.vendor,
        d.model,
        d.site_code,
        d.device_role
    FROM devices d
    LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
    WHERE d.is_active = 1
    """

    conditions = []
    params = []

    # Add include patterns
    if include_patterns:
        include_conditions = []
        for pattern in include_patterns:
            include_conditions.append("(d.device_name LIKE ? OR d.hostname LIKE ?)")
            params.extend([f"%{pattern}%", f"%{pattern}%"])
        conditions.append(f"({' OR '.join(include_conditions)})")

    # Add exclude patterns
    if exclude_patterns:
        for pattern in exclude_patterns:
            conditions.append("(d.device_name NOT LIKE ? AND d.hostname NOT LIKE ?)")
            params.extend([f"%{pattern}%", f"%{pattern}%"])

    # Add site filter
    if sites:
        site_conditions = []
        for site in sites:
            site_conditions.append("UPPER(d.site_code) = UPPER(?)")
            params.append(site)
        conditions.append(f"({' OR '.join(site_conditions)})")

    # Add role filter
    if roles:
        role_conditions = []
        for role in roles:
            role_conditions.append("d.device_role = ?")
            params.append(role)
        conditions.append(f"({' OR '.join(role_conditions)})")

    # Build final query
    if conditions:
        query = base_query + " AND " + " AND ".join(conditions)
    else:
        query = base_query

    results = execute_query(query, params)
    return {normalize_hostname(row['device_name']): dict(row) for row in results}


def ensure_bidirectional_consistency(topology_map):
    """
    Simple bidirectional consistency fix that maintains the clean topology_map format.

    For every connection A -> B, ensure there's a corresponding B -> A connection.
    This fixes cases where LLDP data is incomplete or asymmetric while keeping
    the simple, readable JSON structure.
    """
    logger.info("Starting simple bidirectional consistency check...")

    # Track connections that need to be added
    connections_to_add = defaultdict(lambda: defaultdict(list))
    missing_devices = {}

    # Step 1: Find all connections and what's missing
    for source_device, source_data in topology_map.items():
        source_peers = source_data.get('peers', {})

        for peer_device, peer_data in source_peers.items():
            connections = peer_data.get('connections', [])

            # Check if peer device exists in topology
            if peer_device not in topology_map:
                # Peer device missing entirely - we'll need to create it
                if peer_device not in missing_devices:
                    missing_devices[peer_device] = {
                        'ip': peer_data.get('ip', ''),
                        'platform': peer_data.get('platform', 'Unknown'),
                        'peers_to_add': {}
                    }

                # Add reverse connections for this missing device
                reverse_connections = []
                for conn in connections:
                    if len(conn) >= 2:
                        reverse_connections.append([conn[1], conn[0]])  # Swap interfaces

                missing_devices[peer_device]['peers_to_add'][source_device] = {
                    'ip': source_data.get('node_details', {}).get('ip', ''),
                    'platform': source_data.get('node_details', {}).get('platform', ''),
                    'connections': reverse_connections
                }
            else:
                # Peer device exists - check if it has reverse connections
                peer_topology_data = topology_map[peer_device]
                peer_reverse_peers = peer_topology_data.get('peers', {})

                if source_device not in peer_reverse_peers:
                    # Missing entire peer relationship
                    reverse_connections = []
                    for conn in connections:
                        if len(conn) >= 2:
                            reverse_connections.append([conn[1], conn[0]])

                    connections_to_add[peer_device][source_device] = {
                        'ip': source_data.get('node_details', {}).get('ip', ''),
                        'platform': source_data.get('node_details', {}).get('platform', ''),
                        'connections': reverse_connections
                    }
                else:
                    # Peer relationship exists - check for missing individual connections
                    existing_reverse_connections = set()
                    for conn in peer_reverse_peers[source_device].get('connections', []):
                        if len(conn) >= 2:
                            existing_reverse_connections.add((conn[0], conn[1]))

                    missing_connections = []
                    for conn in connections:
                        if len(conn) >= 2:
                            reverse_conn = (conn[1], conn[0])
                            if reverse_conn not in existing_reverse_connections:
                                missing_connections.append([conn[1], conn[0]])

                    if missing_connections:
                        # Add missing connections to existing peer
                        connections_to_add[peer_device][source_device] = {
                            'connections_only': missing_connections
                        }

    # Step 2: Apply the fixes
    added_connections = 0
    created_devices = 0

    # Add missing devices
    for device_name, device_info in missing_devices.items():
        logger.info(f"Creating missing device: {device_name}")
        topology_map[device_name] = {
            'node_details': {
                'ip': device_info['ip'],
                'platform': device_info['platform']
            },
            'peers': device_info['peers_to_add']
        }
        created_devices += 1
        added_connections += len(device_info['peers_to_add'])

    # Add missing peer relationships and connections
    for device_name, peers_to_add in connections_to_add.items():
        if device_name in topology_map:
            for peer_name, peer_info in peers_to_add.items():
                if 'connections_only' in peer_info:
                    # Just add missing connections to existing peer
                    existing_connections = topology_map[device_name]['peers'][peer_name]['connections']
                    existing_connections.extend(peer_info['connections_only'])
                    logger.info(
                        f"Added {len(peer_info['connections_only'])} missing connections: {device_name} -> {peer_name}")
                    added_connections += len(peer_info['connections_only'])
                else:
                    # Add entire new peer relationship
                    if 'peers' not in topology_map[device_name]:
                        topology_map[device_name]['peers'] = {}

                    topology_map[device_name]['peers'][peer_name] = {
                        'ip': peer_info['ip'],
                        'platform': peer_info['platform'],
                        'connections': peer_info['connections']
                    }
                    logger.info(f"Added missing peer relationship: {device_name} -> {peer_name}")
                    added_connections += 1

    logger.info(f"Simple bidirectional consistency completed:")
    logger.info(f"  - Created {created_devices} missing devices")
    logger.info(f"  - Added {added_connections} missing connections/relationships")
    logger.info(f"  - Final topology has {len(topology_map)} devices")

    return topology_map


def validate_topology_consistency(topology_map):
    """
    Validate that the topology map has proper bidirectional consistency.
    Returns a report of any inconsistencies found.
    """
    issues = []

    for device_a, device_data in topology_map.items():
        peers = device_data.get('peers', {})

        for device_b, peer_data in peers.items():
            connections = peer_data.get('connections', [])

            # Check if device_b exists and has device_a as a peer
            if device_b not in topology_map:
                issues.append(f"Device {device_b} (peer of {device_a}) not found in topology")
                continue

            reverse_peers = topology_map[device_b].get('peers', {})
            if device_a not in reverse_peers:
                issues.append(f"Missing reverse peer: {device_b} should have {device_a} as peer")
                continue

            # Check connection consistency
            reverse_connections = reverse_peers[device_a].get('connections', [])

            for conn in connections:
                if len(conn) >= 2:
                    local_int, remote_int = conn[0], conn[1]
                    # Look for reverse connection
                    reverse_found = False
                    for rev_conn in reverse_connections:
                        if len(rev_conn) >= 2 and rev_conn[0] == remote_int and rev_conn[1] == local_int:
                            reverse_found = True
                            break

                    if not reverse_found:
                        issues.append(f"Missing reverse connection: {device_b}:{remote_int} -> {device_a}:{local_int}")

    return issues


def build_topology_map(include_patterns=None, exclude_patterns=None, sites=None, roles=None, network_only=False):
    """Build the topology map structure from LLDP data with enhanced interface normalization and bidirectional consistency"""
    try:
        logger.info(
            f"Building topology map with interface normalization - filters: sites={sites}, network_only={network_only}")

        lldp_data = get_latest_lldp_data(include_patterns, exclude_patterns, sites, roles)
        logger.info(f"Retrieved {len(lldp_data)} LLDP entries")

        if not lldp_data:
            logger.warning("No LLDP data found with current filters")
            return {}

        device_details = get_device_details(include_patterns, exclude_patterns, sites, roles)
        logger.info(f"Retrieved details for {len(device_details)} devices")

        # Initialize map structure
        topology_map = {}
        all_source_devices = set()
        all_peer_devices = set()

        # First pass: collect all source and peer devices
        device_lldp = defaultdict(list)
        interface_normalization_stats = {'normalized': 0, 'unchanged': 0}

        for entry in lldp_data:
            device_name = normalize_hostname(entry['device_name'] or entry['hostname'])
            remote_hostname = normalize_hostname(entry['remote_hostname'])

            if device_name:
                device_lldp[device_name].append(entry)
                all_source_devices.add(device_name)

            if remote_hostname:
                all_peer_devices.add(remote_hostname)

        logger.info(f"Found {len(all_source_devices)} source devices and {len(all_peer_devices)} peer devices")

        # If network_only is True, only include devices that appear as both source AND peer
        if network_only:
            network_devices = all_source_devices.intersection(all_peer_devices)
            logger.info(f"Network-only mode: filtering to {len(network_devices)} network devices")
            device_lldp = {device: entries for device, entries in device_lldp.items() if device in network_devices}

        # Build topology map with interface normalization
        for device_name, lldp_entries in device_lldp.items():
            try:
                # Get device details
                device_info = device_details.get(device_name, {})

                # Build platform string from vendor and model
                platform = build_platform_string(device_info.get('vendor'), device_info.get('model'))

                # Initialize device entry
                topology_map[device_name] = {
                    "node_details": {
                        "ip": device_info.get('ip_address', ''),
                        "platform": platform
                    },
                    "peers": {}
                }

                # Group connections by RESOLVED remote device name (not just remote_hostname from LLDP)
                # This is the key fix - we need to resolve the remote device identity properly
                peer_connections = defaultdict(list)
                seen_connections = defaultdict(set)

                for entry in lldp_entries:
                    try:
                        raw_remote_hostname = entry['remote_hostname']
                        if not raw_remote_hostname:
                            continue

                        # Try to resolve the remote hostname to an actual device in our database
                        # Check multiple possible matches since LLDP data can be inconsistent
                        resolved_remote_device = None
                        normalized_remote_hostname = normalize_hostname(raw_remote_hostname)

                        # First, try direct match with normalized hostname
                        if normalized_remote_hostname in device_details:
                            resolved_remote_device = normalized_remote_hostname
                        else:
                            # Try to find a device that matches this remote hostname
                            # Look through all devices to find a match
                            for device_key, device_info in device_details.items():
                                device_hostname = normalize_hostname(device_info.get('hostname', ''))
                                device_name_norm = normalize_hostname(device_info.get('device_name', ''))

                                if (normalized_remote_hostname == device_hostname or
                                        normalized_remote_hostname == device_name_norm or
                                        raw_remote_hostname.lower() == device_info.get('hostname', '').lower() or
                                        raw_remote_hostname.lower() == device_info.get('device_name', '').lower()):
                                    resolved_remote_device = device_key
                                    break

                        # If we still haven't resolved it, use the normalized hostname as-is
                        if not resolved_remote_device:
                            resolved_remote_device = normalized_remote_hostname
                            logger.debug(
                                f"Could not resolve remote device '{raw_remote_hostname}' to known device, using normalized name")

                        # Apply network_only filter using the resolved device name
                        if network_only and resolved_remote_device not in all_source_devices:
                            continue

                        # Get original interface names
                        local_interface = entry['local_interface'] or ''
                        remote_interface = entry['remote_port'] or ''

                        # Normalize interface names using vendor information
                        normalized_local, normalized_remote = normalize_interface_pair(
                            local_interface,
                            remote_interface,
                            local_vendor=entry.get('vendor'),
                            remote_vendor=entry.get('remote_vendor')
                        )

                        # Track normalization statistics
                        if normalized_local != local_interface or normalized_remote != remote_interface:
                            interface_normalization_stats['normalized'] += 1
                            logger.debug(
                                f"Normalized: {local_interface} -> {normalized_local}, {remote_interface} -> {normalized_remote}")
                        else:
                            interface_normalization_stats['unchanged'] += 1

                        # Create a unique connection identifier to avoid duplicates
                        # Use the RESOLVED device name for grouping, not the raw LLDP hostname
                        connection_key = (normalized_local, normalized_remote)

                        # Only add if we haven't seen this exact connection before for this resolved peer
                        if connection_key not in seen_connections[resolved_remote_device]:
                            connection = [normalized_local, normalized_remote]
                            peer_connections[resolved_remote_device].append(connection)
                            seen_connections[resolved_remote_device].add(connection_key)
                            logger.debug(
                                f"Added connection: {device_name}:{normalized_local} -> {resolved_remote_device}:{normalized_remote}")
                        else:
                            logger.debug(
                                f"Skipped duplicate connection: {device_name}:{normalized_local} -> {resolved_remote_device}:{normalized_remote}")

                    except Exception as entry_error:
                        logger.error(f"Error processing LLDP entry for {device_name}: {entry_error}")
                        continue

                # Build peers section using resolved device names
                for resolved_peer_name, connections in peer_connections.items():
                    if resolved_peer_name:  # Skip empty peer names
                        # Try to get peer details from device_details using resolved name
                        peer_info = device_details.get(resolved_peer_name, {})
                        peer_platform = build_platform_string(peer_info.get('vendor'), peer_info.get('model'))

                        topology_map[device_name]["peers"][resolved_peer_name] = {
                            "ip": peer_info.get('ip_address', ''),
                            "platform": peer_platform,
                            "connections": connections
                        }

                logger.debug(f"Device {device_name}: added {len(topology_map[device_name]['peers'])} peers")

            except Exception as device_error:
                logger.error(f"Error processing device {device_name}: {device_error}")
                continue

        logger.info(f"Initial topology map built with {len(topology_map)} devices")
        logger.info(f"Interface normalization stats: {interface_normalization_stats['normalized']} normalized, "
                    f"{interface_normalization_stats['unchanged']} unchanged")

        # APPLY SIMPLE BIDIRECTIONAL CONSISTENCY CHECKING
        logger.info("Applying simple bidirectional consistency check...")
        topology_map = ensure_bidirectional_consistency(topology_map)

        # Validate the result
        issues = validate_topology_consistency(topology_map)
        if issues:
            logger.warning(f"Topology consistency issues found: {len(issues)} issues")
            for issue in issues[:5]:  # Log first 5 issues
                logger.warning(f"  - {issue}")
        else:
            logger.info("Topology passed consistency validation")

        return topology_map

    except Exception as e:
        logger.error(f"Error in build_topology_map: {e}", exc_info=True)
        return {}


def generate_mermaid_diagram(topology_map, layout='TD'):
    """Generate Mermaid diagram code from topology map with normalized interfaces"""
    try:
        if not topology_map:
            logger.warning("Empty topology map provided")
            return "graph TD\nA[No devices found with current filters]"

        logger.info(f"Generating Mermaid diagram with layout={layout} for {len(topology_map)} devices")

        lines = [f"graph {layout}"]
        processed_connections = set()
        node_count = 0
        edge_count = 0

        # Add nodes and connections
        for node, data in topology_map.items():
            try:
                node_id = node.replace("-", "_").replace(".", "_")
                node_count += 1

                # Node info
                node_details = data.get('node_details', {})
                node_info = [
                    node,
                    f"IP: {node_details.get('ip', 'N/A')}",
                    f"Platform: {node_details.get('platform', 'N/A')}"
                ]

                lines.append(f'{node_id}["{("<br>").join(node_info)}"]:::core')
                logger.debug(f"Added node: {node_id}")

                # Add connections to peers
                peers = data.get('peers', {})
                for peer, peer_data in peers.items():
                    try:
                        peer_id = peer.replace("-", "_").replace(".", "_")
                        connection_pair = tuple(sorted([node_id, peer_id]))

                        if connection_pair not in processed_connections:
                            # Add peer node if not already defined
                            peer_info = [
                                peer,
                                f"IP: {peer_data.get('ip', 'N/A')}",
                                f"Platform: {peer_data.get('platform', 'N/A')}"
                            ]

                            # Check if peer is in topology_map (network device) or just a leaf
                            peer_class = 'core' if peer in topology_map else 'edge'
                            lines.append(f'{peer_id}["{("<br>").join(peer_info)}"]:::{peer_class}')

                            # Add connection with all normalized interface labels for multiple connections
                            connections = peer_data.get('connections', [])
                            if connections:
                                if len(connections) == 1:
                                    # Single connection - show interface labels
                                    if len(connections[0]) >= 2:
                                        connection_label = f"{connections[0][0]} - {connections[0][1]}"
                                        lines.append(f'{node_id} <-->|"{connection_label}"| {peer_id}')
                                    else:
                                        lines.append(f'{node_id} <--> {peer_id}')
                                else:
                                    # Multiple connections - show count and first connection as example
                                    first_connection = connections[0]
                                    if len(first_connection) >= 2:
                                        connection_label = f"{first_connection[0]} - {first_connection[1]} (+{len(connections) - 1} more)"
                                        lines.append(f'{node_id} <-->|"{connection_label}"| {peer_id}')
                                    else:
                                        connection_label = f"{len(connections)} connections"
                                        lines.append(f'{node_id} <-->|"{connection_label}"| {peer_id}')
                            else:
                                lines.append(f'{node_id} <--> {peer_id}')

                            processed_connections.add(connection_pair)
                            edge_count += 1
                            logger.debug(f"Added connection: {node_id} <--> {peer_id}")

                    except Exception as peer_error:
                        logger.error(f"Error processing peer {peer} for node {node}: {peer_error}")
                        continue

            except Exception as node_error:
                logger.error(f"Error processing node {node}: {node_error}")
                continue

        final_diagram = "\n".join(lines)
        logger.info(
            f"Generated Mermaid diagram with normalized interfaces: {node_count} nodes, {edge_count} edges, {len(lines)} lines")

        return final_diagram

    except Exception as e:
        logger.error(f"Error in generate_mermaid_diagram: {e}", exc_info=True)
        return f"graph TD\nA[Diagram generation error: {str(e)}]"


# API endpoints remain the same - they automatically use the enhanced topology building functions

@topology_bp.route('/api/topology/data')
def api_topology_data():
    """API endpoint to get topology data with normalized interfaces"""
    try:
        # Get query parameters
        sites = request.args.getlist('site')
        roles = request.args.getlist('role')
        include_patterns = request.args.getlist('include')
        exclude_patterns = request.args.getlist('exclude')
        network_only = request.args.get('network_only', 'false').lower() == 'true'

        # Build topology map with interface normalization
        topology_map = build_topology_map(
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            sites=sites,
            roles=roles,
            network_only=network_only
        )

        return jsonify({
            'success': True,
            'topology': topology_map,
            'device_count': len(topology_map),
            'timestamp': datetime.now().isoformat(),
            'features': ['interface_normalization', 'bidirectional_consistency']
        })

    except Exception as e:
        logger.error(f"Error generating topology data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@topology_bp.route('/api/topology/mermaid')
def api_topology_mermaid():
    """API endpoint to get Mermaid diagram code with normalized interfaces"""
    try:
        # Get query parameters
        sites = request.args.getlist('site')
        roles = request.args.getlist('role')
        include_patterns = request.args.getlist('include')
        exclude_patterns = request.args.getlist('exclude')
        network_only = request.args.get('network_only', 'false').lower() == 'true'
        layout = request.args.get('layout', 'TD')
        layout = "hierarchical"

        logger.info(f"Topology API called with params: sites={sites}, roles={roles}, "
                    f"include={include_patterns}, exclude={exclude_patterns}, "
                    f"network_only={network_only}, layout={layout}")

        # Build topology map with interface normalization
        topology_map = build_topology_map(
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            sites=sites,
            roles=roles,
            network_only=network_only
        )

        logger.info(f"Built topology map with {len(topology_map)} devices")

        # Generate Mermaid diagram with normalized interfaces
        mermaid_code = generate_mermaid_diagram(topology_map, layout)

        logger.info(f"Generated Mermaid code length: {len(mermaid_code)} characters")

        return jsonify({
            'success': True,
            'mermaid': mermaid_code,
            'device_count': len(topology_map),
            'timestamp': datetime.now().isoformat(),
            'features': ['interface_normalization', 'bidirectional_consistency'],
            'debug_info': {
                'topology_devices': list(topology_map.keys())[:5],
                'total_peers': sum(len(data.get('peers', {})) for data in topology_map.values()),
                'filters_applied': {
                    'sites': sites,
                    'network_only': network_only,
                    'include_patterns': include_patterns
                }
            }
        })

    except Exception as e:
        logger.error(f"Error generating Mermaid diagram: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'mermaid': "graph TD\nA[Error loading topology]",
            'debug_info': {
                'error_type': type(e).__name__,
                'error_details': str(e)
            }
        }), 500


@topology_bp.route('/api/topology/debug')
def api_topology_debug():
    """Debug endpoint to write intermediate topology structure to file"""
    try:
        import json
        import os
        from datetime import datetime

        # Get query parameters
        sites = request.args.getlist('site')
        roles = request.args.getlist('role')
        include_patterns = request.args.getlist('include')
        exclude_patterns = request.args.getlist('exclude')
        network_only = request.args.get('network_only', 'false').lower() == 'true'

        logger.info(f"Debug topology API called with params: sites={sites}, roles={roles}, "
                    f"include={include_patterns}, exclude={exclude_patterns}, "
                    f"network_only={network_only}")

        # Build topology map with debugging
        topology_map = build_topology_map(
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            sites=sites,
            roles=roles,
            network_only=network_only
        )

        # Create debug output
        debug_data = {
            "timestamp": datetime.now().isoformat(),
            "parameters": {
                "sites": sites,
                "roles": roles,
                "include_patterns": include_patterns,
                "exclude_patterns": exclude_patterns,
                "network_only": network_only
            },
            "topology_map": topology_map,
            "device_count": len(topology_map),
            "summary": {
                "devices": list(topology_map.keys()),
                "total_connections": sum(
                    len(data.get('peers', {})) for data in topology_map.values()
                ),
                "peer_summary": {
                    device: list(data.get('peers', {}).keys())
                    for device, data in topology_map.items()
                }
            }
        }

        # Write to file
        debug_filename = f"topology_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        debug_filepath = os.path.join('/tmp', debug_filename)
        #
        # with open(debug_filepath, 'w') as f:
        #     json.dump(debug_data, f, indent=2)
        #
        # logger.info(f"Debug data written to {debug_filepath}")

        return jsonify({
            'success': True,
            'debug_file': debug_filepath,
            'topology_map': topology_map,
            'device_count': len(topology_map),
            'summary': debug_data['summary']
        })

    except Exception as e:
        logger.error(f"Error in debug endpoint: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@topology_bp.route('/api/topology/raw_data')
def api_topology_raw_data():
    """Debug endpoint to show raw LLDP data and device details"""
    try:
        import json

        # Get query parameters
        sites = request.args.getlist('site')
        roles = request.args.getlist('role')
        include_patterns = request.args.getlist('include')
        exclude_patterns = request.args.getlist('exclude')

        # Get raw data
        lldp_data = get_latest_lldp_data(include_patterns, exclude_patterns, sites, roles)
        device_details = get_device_details(include_patterns, exclude_patterns, sites, roles)

        # Show first few entries for debugging
        debug_info = {
            "lldp_sample": lldp_data[:5] if lldp_data else [],
            "lldp_count": len(lldp_data),
            "device_details_sample": dict(list(device_details.items())[:5]) if device_details else {},
            "device_count": len(device_details),
            "device_keys": list(device_details.keys())[:10],
            "hostname_examples": [
                {
                    "device_key": k,
                    "hostname": v.get('hostname'),
                    "device_name": v.get('device_name'),
                    "normalized_key": normalize_hostname(k),
                    "normalized_hostname": normalize_hostname(v.get('hostname', '')),
                    "normalized_device_name": normalize_hostname(v.get('device_name', ''))
                }
                for k, v in list(device_details.items())[:5]
            ]
        }

        return jsonify({
            'success': True,
            'debug_info': debug_info
        })

    except Exception as e:
        logger.error(f"Error in raw data endpoint: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500



@topology_bp.route('/api/topology/export/drawio', methods=['GET', 'POST'])
def api_export_drawio_new():
    """Export topology to Draw.io format - supports both GET and POST"""
    try:
        # Handle both GET and POST requests
        if request.method == 'POST':
            config = request.get_json() or {}
            # Get from POST body
            sites = config.get('sites', [])
            layout = config.get('layout', 'tree')
            network_only = config.get('network_only', False)
            use_icons = config.get('use_icons', True)
        else:
            # Handle GET request - get from query parameters
            sites = request.args.getlist('sites')
            layout = request.args.get('layout', 'tree')
            network_only = request.args.get('network_only', 'false').lower() == 'true'
            use_icons = request.args.get('use_icons', 'true').lower() == 'true'

        # Convert layout parameter
        if layout in ['TD', 'TB', 'BT', 'hierarchical']:
            layout = 'tree'
        elif layout in ['LR', 'RL']:
            layout = 'tree'
        elif layout == 'balloon':
            layout = 'balloon'
        else:
            layout = 'tree'

        # Include endpoints setting
        include_endpoints = not network_only

        logger.info(f"Draw.io export ({request.method}): sites={sites}, network_only={network_only}, "
                   f"layout={layout}, include_endpoints={include_endpoints}")

        # Build topology using existing function
        topology_map = build_topology_map(
            sites=sites if sites else None,
            network_only=network_only
        )

        if not topology_map:
            if request.method == 'GET':
                return "No topology data available for the selected filters", 404
            else:
                return jsonify({
                    'success': False,
                    'error': 'No topology data found with current filters'
                }), 400

        # Generate timestamp for consistent naming
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')

        # Create output path
        output_filename = f"rapidcmdb-topology-{timestamp}.drawio"
        output_path = Path(output_filename)

        # Create and configure the exporter
        exporter = NetworkDrawioExporter(
            include_endpoints=include_endpoints,
            use_icons=use_icons,
            layout_type=layout,
            icons_dir='./icons_lib'
        )

        # Export the topology
        exporter.export_to_drawio(topology_map, output_path)

        logger.info(f"Successfully exported {len(topology_map)} devices to Draw.io: {output_path}")

        # Clean up the exporter
        exporter.cleanup()

        # Return the file as download
        return send_file(
            str(output_path.absolute()),
            as_attachment=True,
            download_name=output_filename,
            mimetype='application/xml'
        )

    except Exception as e:
        logger.error(f"Draw.io export error: {e}", exc_info=True)
        if request.method == 'GET':
            return f"Export failed: {str(e)}", 500
        else:
            return jsonify({
                'success': False,
                'error': str(e),
                'message': 'Export failed using Draw.io exporter'
            }), 500


@topology_bp.route('/api/topology/export/json', methods=['GET', 'POST'])
def api_export_json_topology():
    """Export topology to standard JSON format - supports both GET and POST"""
    try:
        # Handle both GET and POST requests
        if request.method == 'POST':
            config = request.get_json() or {}
            # Get parameters from POST body
            sites = config.get('sites', [])
            roles = config.get('roles', [])
            include_patterns = config.get('include_patterns', [])
            exclude_patterns = config.get('exclude_patterns', [])
            network_only = config.get('network_only', False)
            include_metadata = config.get('include_metadata', True)
            pretty_print = config.get('pretty_print', True)
            download_file = config.get('download_file', False)
        else:
            # Handle GET request - get from query parameters
            sites = request.args.getlist('sites')
            roles = request.args.getlist('role')
            include_patterns = request.args.getlist('include')
            exclude_patterns = request.args.getlist('exclude')
            network_only = request.args.get('network_only', 'false').lower() == 'true'
            include_metadata = request.args.get('include_metadata', 'false').lower() == 'true'
            pretty_print = request.args.get('pretty_print', 'true').lower() == 'true'
            download_file = request.args.get('download_file', 'true').lower() == 'true'

        logger.info(f"JSON export ({request.method}): sites={sites}, network_only={network_only}, "
                    f"include_metadata={include_metadata}, download_file={download_file}")

        # IMPORTANT FIX: Pass the sites correctly to build_topology_map
        # The issue is that we need to match the parameter names that build_topology_map expects
        topology_map = build_topology_map(
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            sites=sites,  # This parameter name should match what build_topology_map expects
            roles=roles,
            network_only=network_only
        )

        # DEBUG: Log what was actually passed and what was returned
        logger.info(f"Passed to build_topology_map - sites: {sites}, network_only: {network_only}")
        logger.info(f"Topology map returned {len(topology_map)} devices")

        # If debugging, log the first few device names to verify filtering worked
        if topology_map:
            device_names = list(topology_map.keys())[:5]
            logger.info(f"First few devices in topology: {device_names}")

        if not topology_map:
            if request.method == 'GET':
                return "No topology data available for the selected filters", 404
            else:
                return jsonify({
                    'success': False,
                    'error': 'No topology data found with current filters',
                    'device_count': 0
                }), 400

        # Create exporter and convert topology
        exporter = JSONTopologyExporter(
            include_metadata=include_metadata,
            pretty_print=pretty_print
        )

        if download_file:
            # Export to file and return as download
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            site_filter = '-'.join(sites) if sites else 'all-sites'
            filename = f"network-topology-{site_filter}-{timestamp}.json"
            output_path = Path(filename)

            # Convert topology and remove metadata before saving to file
            converted_topology = exporter.convert_topology_map(topology_map)

            if include_metadata:
                final_data = exporter.add_export_metadata(converted_topology)
            else:
                final_data = converted_topology

            # Remove metadata regardless of include_metadata setting
            final_data.pop('_export_metadata', None)

            # Write clean data to file
            with open(output_path, 'w', encoding='utf-8') as f:
                if pretty_print:
                    json.dump(final_data, f, indent=2, ensure_ascii=False, sort_keys=True)
                else:
                    json.dump(final_data, f, ensure_ascii=False, separators=(',', ':'))

            logger.info(f"Successfully exported {len(converted_topology)} devices to JSON file: {filename}")

            # Return file as download
            return send_file(
                str(output_path.absolute()),
                as_attachment=True,
                download_name=filename,
                mimetype='application/json'
            )
        else:
            # Return JSON response
            converted_topology = exporter.convert_topology_map(topology_map)

            if include_metadata:
                final_data = exporter.add_export_metadata(converted_topology)
            else:
                final_data = converted_topology

            # Remove metadata regardless of include_metadata setting
            final_data.pop('_export_metadata', None)

            return jsonify({
                'success': True,
                'topology': final_data,
                'export_info': {
                    'format': 'standard_json_topology',
                    'device_count': len(converted_topology),
                    'timestamp': datetime.now().isoformat(),
                    'filters_applied': {
                        'sites': sites,
                        'network_only': network_only,
                        'include_patterns': include_patterns,
                        'exclude_patterns': exclude_patterns
                    },
                    'export_options': {
                        'include_metadata': include_metadata,
                        'pretty_print': pretty_print
                    }
                }
            })

    except Exception as e:
        logger.error(f"JSON export error: {e}", exc_info=True)
        if request.method == 'GET':
            return f"Export failed: {str(e)}", 500
        else:
            return jsonify({
                'success': False,
                'error': str(e),
                'message': 'JSON export failed'
            }), 500


@topology_bp.route('/api/topology/data_file')
def api_topology_data_file():
    """API endpoint to get topology data in map.json format"""
    try:
        # Get query parameters
        sites = request.args.getlist('site')
        roles = request.args.getlist('role')
        include_patterns = request.args.getlist('include')
        exclude_patterns = request.args.getlist('exclude')
        network_only = request.args.get('network_only', 'false').lower() == 'true'

        logger.info(f"Topology data API called with params: sites={sites}, "
                    f"network_only={network_only}")

        # Build topology map (same as mermaid endpoint but return raw data)
        topology_map = build_topology_map(
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            sites=sites,
            roles=roles,
            network_only=network_only
        )

        logger.info(f"Built topology map with {len(topology_map)} devices for export")

        return jsonify({
            'success': True,
            'topology': topology_map,
            'device_count': len(topology_map),
            'timestamp': datetime.now().isoformat(),
            'filters_applied': {
                'sites': sites,
                'network_only': network_only,
                'include_patterns': include_patterns,
                'exclude_patterns': exclude_patterns
            },
            'export_info': {
                'format': 'map.json',
                'compatible_with': 'build_topology.py output',
                'generated_by': 'NAPALM CMDB Web Interface'
            }
        })

    except Exception as e:
        logger.error(f"Error generating topology data for export: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'topology': {},
            'device_count': 0
        }), 500


@topology_bp.route('/api/topology/sites')
def api_topology_sites():
    """API endpoint to get available sites"""
    try:
        sites_query = """
        SELECT DISTINCT site_code, COUNT(*) as device_count
        FROM devices 
        WHERE is_active = 1 AND site_code IS NOT NULL AND site_code != ''
        GROUP BY site_code 
        ORDER BY site_code
        """
        sites = execute_query(sites_query)

        return jsonify({
            'success': True,
            'sites': sites
        })
    except Exception as e:
        logger.error(f"Error getting sites: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@topology_bp.route('/api/topology/export/svg', methods=['GET'])
def api_export_svg_get():
    """GET endpoint for SVG export - WebView compatible"""
    try:
        # Get parameters
        sites = request.args.getlist('sites')
        network_only = request.args.get('network_only', 'false').lower() == 'true'

        # Generate placeholder SVG (you can implement actual SVG generation later)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        placeholder_svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="800" height="600" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <style>
      .title {{ font-family: Arial, sans-serif; font-size: 24px; font-weight: bold; fill: #333; }}
      .subtitle {{ font-family: Arial, sans-serif; font-size: 16px; fill: #666; }}
      .info {{ font-family: Arial, sans-serif; font-size: 12px; fill: #999; }}
      .device {{ fill: #4285f4; stroke: #333; stroke-width: 2; }}
      .device-text {{ font-family: Arial, sans-serif; font-size: 10px; fill: white; text-anchor: middle; }}
    </style>
  </defs>

  <!-- Background -->
  <rect width="100%" height="100%" fill="#f8f9fa"/>

  <!-- Title -->
  <text x="400" y="40" class="title" text-anchor="middle">
    RapidCMDB Network Topology
  </text>

  <!-- Subtitle -->
  <text x="400" y="70" class="subtitle" text-anchor="middle">
    Generated: {timestamp}
  </text>

  <!-- Filter Info -->
  <text x="400" y="100" class="info" text-anchor="middle">
    Sites: {', '.join(sites) if sites else 'All'} | Network Only: {network_only}
  </text>

  <!-- Sample devices (placeholder) -->
  <g id="devices">
    <rect x="150" y="200" width="100" height="60" class="device" rx="5"/>
    <text x="200" y="230" class="device-text">Core Switch</text>

    <rect x="350" y="150" width="100" height="60" class="device" rx="5"/>
    <text x="400" y="180" class="device-text">Router A</text>

    <rect x="350" y="250" width="100" height="60" class="device" rx="5"/>
    <text x="400" y="280" class="device-text">Router B</text>

    <rect x="550" y="200" width="100" height="60" class="device" rx="5"/>
    <text x="600" y="230" class="device-text">Access Switch</text>
  </g>

  <!-- Sample connections -->
  <g id="connections">
    <line x1="250" y1="230" x2="350" y2="180" stroke="#666" stroke-width="2"/>
    <line x1="250" y1="230" x2="350" y2="280" stroke="#666" stroke-width="2"/>
    <line x1="450" y1="180" x2="550" y2="220" stroke="#666" stroke-width="2"/>
    <line x1="450" y1="280" x2="550" y2="240" stroke="#666" stroke-width="2"/>
  </g>

  <!-- Footer -->
  <text x="400" y="550" class="info" text-anchor="middle">
    This is a placeholder SVG. Implement actual topology visualization for production use.
  </text>
</svg>'''

        # Create response
        from flask import make_response
        response = make_response(placeholder_svg)
        response.headers['Content-Type'] = 'image/svg+xml'
        response.headers[
            'Content-Disposition'] = f'attachment; filename="topology-diagram-{datetime.now().strftime("%Y-%m-%d")}.svg"'
        response.headers['Cache-Control'] = 'no-cache'

        return response

    except Exception as e:
        logger.error(f"SVG GET export error: {e}")
        return f"Export failed: {str(e)}", 500

@topology_bp.route('/api/topology/export/png', methods=['GET'])
def api_export_png_get():
    """GET endpoint for PNG export - WebView compatible"""
    try:
        return "PNG export not yet implemented. Please use SVG export instead.", 501

    except Exception as e:
        logger.error(f"PNG GET export error: {e}")
        return f"Export failed: {str(e)}", 500