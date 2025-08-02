# blueprints/network.py
"""
Network Blueprint - Topology and network analysis
"""

from flask import Blueprint, render_template, jsonify, request
import sqlite3
from datetime import datetime
from collections import defaultdict
import logging

# Create the blueprint
network_bp = Blueprint('network', __name__, template_folder='../templates')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Get database connection with row factory"""
    conn = sqlite3.connect('napalm_cmdb.db')
    conn.row_factory = sqlite3.Row
    return conn


def execute_query(query, params=None):
    """Execute query and return results"""
    conn = get_db_connection()
    try:
        if params:
            cursor = conn.execute(query, params)
        else:
            cursor = conn.execute(query)
        results = cursor.fetchall()
        return [dict(row) for row in results]
    except Exception as e:
        logger.error(f"Database error: {e}")
        return []
    finally:
        conn.close()


def get_devices_with_topology_info(sites=None, roles=None):
    """Get devices with topology-related information for the enhanced topology view"""
    base_query = """
    SELECT 
        d.id,
        d.device_name,
        d.hostname,
        d.site_code,
        d.device_role,
        d.vendor,
        d.model,
        di.ip_address as primary_ip,
        COUNT(DISTINCT ln.remote_hostname) as peer_count
    FROM devices d
    LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
    LEFT JOIN lldp_neighbors ln ON d.id = ln.device_id
    WHERE d.is_active = 1
    """

    conditions = []
    params = []

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

    query += " GROUP BY d.id, d.device_name, d.hostname, d.site_code, d.device_role, d.vendor, d.model, di.ip_address"
    query += " ORDER BY d.device_name"

    devices = execute_query(query, params)

    # Determine device role based on peer count if not set
    for device in devices:
        if not device.get('device_role') or device['device_role'] == 'unknown':
            peer_count = device.get('peer_count', 0)
            if peer_count > 3:
                device['role'] = 'core'
            elif peer_count > 1:
                device['role'] = 'gateway'
            else:
                device['role'] = 'edge'
        else:
            device['role'] = device['device_role']

    return devices


def get_available_sites():
    """Get all available sites with device counts"""
    query = """
    SELECT 
        site_code,
        COUNT(*) as device_count
    FROM devices 
    WHERE is_active = 1 
        AND site_code IS NOT NULL 
        AND site_code != ''
    GROUP BY site_code 
    ORDER BY site_code
    """
    return execute_query(query)


def calculate_topology_stats(devices=None, sites=None):
    """Calculate topology statistics"""
    if devices is None:
        devices = get_devices_with_topology_info(sites=sites)

    total_devices = len(devices)
    total_connections = sum(device.get('peer_count', 0) for device in devices)
    # Since each connection is counted twice (once per device), divide by 2
    unique_connections = total_connections // 2 if total_connections > 0 else 0

    # Get unique sites and vendors
    sites = set(device.get('site_code') for device in devices if device.get('site_code'))
    vendors = set(device.get('vendor') for device in devices if device.get('vendor'))

    return {
        'total_devices': total_devices,
        'total_connections': unique_connections,
        'total_sites': len(sites),
        'total_vendors': len(vendors)
    }


def get_device_types(devices):
    """Get device type distribution"""
    if not devices:
        return []

    type_counts = defaultdict(int)
    for device in devices:
        vendor = device.get('vendor', 'Unknown')
        model = device.get('model', '')

        if vendor and model:
            device_type = f"{vendor} {model}"
        elif vendor:
            device_type = vendor
        else:
            device_type = 'Unknown'

        type_counts[device_type] += 1

    # Return top 5 device types
    return sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:5]


def get_topology_summary(devices):
    """Calculate topology summary statistics"""
    if not devices:
        return None

    total_devices = len(devices)
    total_connections = sum(device.get('peer_count', 0) for device in devices)
    avg_connections = total_connections / total_devices if total_devices > 0 else 0

    return {
        'total_devices': total_devices,
        'total_connections': total_connections // 2,  # Each connection counted twice
        'avg_connections': avg_connections
    }


@network_bp.route('/topology')
def topology():
    """Network topology visualization"""
    try:
        # Get topology data
        topology_query = """
            SELECT 
                nt.*,
                d1.device_name as source_device_name,
                d1.site_code as source_site,
                d1.vendor as source_vendor,
                d2.device_name as dest_device_name,
                d2.site_code as dest_site,
                d2.vendor as dest_vendor
            FROM network_topology nt
            JOIN devices d1 ON nt.source_device_id = d1.id
            JOIN devices d2 ON nt.destination_device_id = d2.id
            WHERE nt.is_active = 1
            ORDER BY nt.confidence_score DESC
        """
        topology_links = execute_query(topology_query)

        # Get devices for nodes
        devices_query = """
            SELECT 
                d.id,
                d.device_name,
                d.site_code,
                d.device_role,
                d.vendor,
                di.ip_address as primary_ip
            FROM devices d
            LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
            WHERE d.is_active = 1
        """
        devices = execute_query(devices_query)

        return render_template('network/topology.html',
                               topology_links=topology_links,
                               devices=devices)
    except Exception as e:
        logger.error(f"Network topology error: {e}")
        return render_template('network/topology.html', topology_links=[], devices=[])


@network_bp.route('/enhanced')
def enhanced_topology():
    """Enhanced network topology visualization with LLDP data integration"""
    try:
        # Get filter parameters
        sites = request.args.getlist('sites')
        layout = request.args.get('layout', 'TD')
        network_only = request.args.get('network_only') == 'on'

        # Get devices with topology information
        devices = get_devices_with_topology_info(sites=sites if sites else None)

        # Get available sites
        available_sites = get_available_sites()

        # Calculate statistics
        stats = calculate_topology_stats(devices, sites)

        # Get current filters
        current_filters = {
            'sites': sites,
            'layout': layout,
            'network_only': network_only
        }

        # Initialize default values
        mermaid_code = ""
        topology_data = {}

        # Only try to build topology if sites are selected
        # This prevents the massive processing loop when no filters are applied
        if sites:
            try:
                from .topology import build_topology_map, generate_mermaid_diagram

                # Build topology map with current filters
                topology_data = build_topology_map(
                    sites=sites,  # Pass the actual sites list, not None
                    network_only=network_only
                )

                # Generate mermaid diagram
                if topology_data:
                    mermaid_code = generate_mermaid_diagram(topology_data, layout)
                else:
                    logger.warning("No topology data returned for selected sites")
                    mermaid_code = "graph TD\n    A[No connections found for selected sites]"

            except ImportError:
                logger.warning("Topology blueprint not available, using placeholder data")
                mermaid_code = "graph TD\n    A[Topology blueprint not available]"
            except Exception as e:
                logger.error(f"Error getting topology data: {e}")
                mermaid_code = "graph TD\n    A[Error loading topology data]"
        else:
            # No sites selected - show instruction message
            mermaid_code = ""  # This will trigger the "select sites" message in the template

        # Calculate topology summary
        topology_summary = get_topology_summary(devices)

        # Get device types
        device_types = get_device_types(devices)

        # Get last updated time
        last_updated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        return render_template('network/enhanced_topology.html',
                               devices=devices,
                               stats=stats,
                               available_sites=available_sites,
                               current_filters=current_filters,
                               mermaid_code=mermaid_code,
                               topology_data=topology_data,
                               topology_summary=topology_summary,
                               device_types=device_types,
                               last_updated=last_updated)

    except Exception as e:
        logger.error(f"Enhanced topology error: {e}", exc_info=True)
        # Return template with minimal data to prevent crashes
        return render_template('network/enhanced_topology.html',
                               devices=[],
                               stats={'total_devices': 0, 'total_connections': 0, 'total_sites': 0, 'total_vendors': 0},
                               available_sites=[],
                               current_filters={'sites': [], 'layout': 'TD', 'network_only': False},
                               mermaid_code="",
                               topology_data={},
                               topology_summary=None,
                               device_types=[],
                               last_updated="Never")


@network_bp.route('/mac-search')
def mac_search():
    """MAC address search and tracking"""
    search_mac = request.args.get('mac', '').strip()
    results = []

    if search_mac:
        # Search in MAC address table
        mac_query = """
            SELECT 
                d.device_name,
                d.site_code,
                mat.mac_address,
                mat.interface_name,
                mat.vlan_id,
                mat.entry_type,
                cr.collection_time,
                'CAM Table' as source_table
            FROM mac_address_table mat
            JOIN devices d ON mat.device_id = d.id
            JOIN collection_runs cr ON mat.collection_run_id = cr.id
            WHERE mat.mac_address LIKE ?

            UNION ALL

            SELECT 
                d.device_name,
                d.site_code,
                ae.mac_address,
                ae.interface_name,
                NULL as vlan_id,
                ae.entry_type,
                cr.collection_time,
                'ARP Table' as source_table
            FROM arp_entries ae
            JOIN devices d ON ae.device_id = d.id
            JOIN collection_runs cr ON ae.collection_run_id = cr.id
            WHERE ae.mac_address LIKE ?

            ORDER BY collection_time DESC
        """

        search_param = f"%{search_mac.upper()}%"
        results = execute_query(mac_query, [search_param, search_param])

    return render_template('network/mac_search.html',
                           search_mac=search_mac,
                           results=results)


@network_bp.route('/api/topology-data')
def api_topology_data():
    """API endpoint for topology data"""
    try:
        # Get nodes (devices)
        nodes_query = """
            SELECT 
                d.id,
                d.device_name as label,
                d.site_code,
                d.device_role as group,
                d.vendor
            FROM devices d
            WHERE d.is_active = 1
            AND d.id IN (
                SELECT DISTINCT source_device_id FROM network_topology WHERE is_active = 1
                UNION
                SELECT DISTINCT destination_device_id FROM network_topology WHERE is_active = 1
            )
        """
        nodes = execute_query(nodes_query)

        # Get edges (connections)
        edges_query = """
            SELECT 
                source_device_id as from_node,
                destination_device_id as to_node,
                connection_type,
                confidence_score,
                source_interface || ' - ' || destination_interface as label
            FROM network_topology
            WHERE is_active = 1
        """
        edges = execute_query(edges_query)

        return jsonify({
            'nodes': nodes,
            'edges': edges
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@network_bp.route('/test_connection')
def test_connection():
    """Test database connection and return basic stats"""
    try:
        # Test basic connectivity
        devices_count = execute_query("SELECT COUNT(*) as count FROM devices WHERE is_active = 1")[0]['count']
        lldp_count = execute_query("SELECT COUNT(*) as count FROM lldp_neighbors")[0]['count']

        return jsonify({
            'success': True,
            'message': 'Database connection successful',
            'stats': {
                'active_devices': devices_count,
                'lldp_entries': lldp_count
            },
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500