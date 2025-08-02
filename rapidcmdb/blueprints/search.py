# blueprints/search.py
"""
Enhanced Search Blueprint - Comprehensive search across all NAPALM collected data
Replaces the config blueprint with unified search functionality
"""

from flask import Blueprint, render_template, jsonify, request, url_for
import sqlite3
from datetime import datetime, timedelta
import re
import json
import logging

search_bp = Blueprint('search', __name__, template_folder='../templates')


def get_db_connection():
    conn = sqlite3.connect('napalm_cmdb.db')
    conn.row_factory = sqlite3.Row
    return conn


def execute_query(query, params=None):
    conn = get_db_connection()
    try:
        if params:
            cursor = conn.execute(query, params)
        else:
            cursor = conn.execute(query)
        results = cursor.fetchall()
        return [dict(row) for row in results]
    except Exception as e:
        logging.error(f"Database error: {e}")
        return []
    finally:
        conn.close()


# Add these routes to your search.py blueprint

@search_bp.route('/view/<data_type>/<device_name>')
@search_bp.route('/view/<data_type>')
def view_table(data_type, device_name=None):
    """Generic table viewer for different data types"""
    try:
        # Define table configurations for different data types
        table_configs = {
            'arp': {
                'title': f'ARP Table{f" - {device_name}" if device_name else ""}',
                'subtitle': 'Address Resolution Protocol entries',
                'icon_class': 'bi-network',
                'query': get_arp_query(),
                'columns': [
                    {'key': 'device_name', 'label': 'Device', 'type': 'device_link', 'sortable': True},
                    {'key': 'ip_address', 'label': 'IP Address', 'type': 'code', 'sortable': True},
                    {'key': 'mac_address', 'label': 'MAC Address', 'type': 'code', 'sortable': True},
                    {'key': 'interface_name', 'label': 'Interface', 'sortable': True},
                    {'key': 'created_at', 'label': 'Last Seen', 'type': 'datetime', 'sortable': True}
                ],
                'filters': [
                    {'id': 'searchIp', 'name': 'ip_search', 'type': 'search', 'label': 'IP Address',
                     'placeholder': 'Search IPs...'},
                    {'id': 'searchMac', 'name': 'mac_search', 'type': 'search', 'label': 'MAC Address',
                     'placeholder': 'Search MACs...'},
                    {'id': 'interfaceFilter', 'name': 'interface', 'type': 'search', 'label': 'Interface',
                     'placeholder': 'Interface name...'}
                ]
            },

            'mac_table': {
                'title': f'MAC Address Table{f" - {device_name}" if device_name else ""}',
                'subtitle': 'Layer 2 MAC address forwarding table',
                'icon_class': 'bi-ethernet',
                'query': get_mac_table_query(),
                'columns': [
                    {'key': 'device_name', 'label': 'Device', 'type': 'device_link', 'sortable': True},
                    {'key': 'mac_address', 'label': 'MAC Address', 'type': 'code', 'sortable': True},
                    {'key': 'vlan_id', 'label': 'VLAN', 'type': 'badge', 'badge_class': 'bg-info', 'sortable': True},
                    {'key': 'interface_name', 'label': 'Interface', 'sortable': True},
                    {'key': 'entry_type', 'label': 'Type', 'type': 'badge', 'sortable': True},
                    {'key': 'created_at', 'label': 'Last Seen', 'type': 'datetime', 'sortable': True}
                ],
                'filters': [
                    {'id': 'searchMac', 'name': 'mac_search', 'type': 'search', 'label': 'MAC Address'},
                    {'id': 'vlanFilter', 'name': 'vlan_id', 'type': 'search', 'label': 'VLAN ID'},
                    {'id': 'interfaceFilter', 'name': 'interface', 'type': 'search', 'label': 'Interface'}
                ]
            },

            'lldp': {
                'title': f'LLDP Neighbors{f" - {device_name}" if device_name else ""}',
                'subtitle': 'Link Layer Discovery Protocol topology',
                'icon_class': 'bi-diagram-3',
                'query': get_lldp_query(),
                'columns': [
                    {'key': 'local_device', 'label': 'Local Device', 'type': 'device_link', 'sortable': True},
                    {'key': 'local_interface', 'label': 'Local Interface', 'type': 'code', 'sortable': True},
                    {'key': 'remote_device', 'label': 'Remote Device', 'sortable': True},
                    {'key': 'remote_interface', 'label': 'Remote Interface', 'type': 'code', 'sortable': True},
                    {'key': 'remote_system_description', 'label': 'Remote Description', 'type': 'truncate',
                     'max_length': 40},
                    {'key': 'last_seen', 'label': 'Last Seen', 'type': 'datetime', 'sortable': True}
                ],
                'filters': [
                    {'id': 'searchDevice', 'name': 'device_search', 'type': 'search', 'label': 'Device Name'},
                    {'id': 'searchInterface', 'name': 'interface_search', 'type': 'search', 'label': 'Interface'}
                ]
            },

            'hardware': {
                'title': f'Hardware Inventory{f" - {device_name}" if device_name else ""}',
                'subtitle': 'Physical components and optics',
                'icon_class': 'bi-cpu',
                'query': get_hardware_query(),
                'columns': [
                    {'key': 'device_name', 'label': 'Device', 'type': 'device_link', 'sortable': True},
                    {'key': 'component_type', 'label': 'Type', 'type': 'badge', 'sortable': True},
                    {'key': 'slot_position', 'label': 'Slot/Position', 'sortable': True},
                    {'key': 'part_number', 'label': 'Part Number', 'type': 'code'},
                    {'key': 'serial_number', 'label': 'Serial Number', 'type': 'code'},
                    {'key': 'description', 'label': 'Description', 'type': 'truncate', 'max_length': 30},
                    {'key': 'status', 'label': 'Status', 'type': 'status', 'sortable': True},
                    {'key': 'last_seen', 'label': 'Last Seen', 'type': 'datetime', 'sortable': True}
                ],
                'filters': [
                    {'id': 'componentFilter', 'name': 'component_type', 'type': 'select', 'label': 'Component Type',
                     'options': [
                         {'value': 'transceiver', 'label': 'Transceivers'},
                         {'value': 'module', 'label': 'Modules'},
                         {'value': 'power_supply', 'label': 'Power Supplies'},
                         {'value': 'fan', 'label': 'Fans'},
                         {'value': 'card', 'label': 'Cards'}
                     ]},
                    {'id': 'statusFilter', 'name': 'status', 'type': 'select', 'label': 'Status',
                     'options': [
                         {'value': 'operational', 'label': 'Operational'},
                         {'value': 'failed', 'label': 'Failed'},
                         {'value': 'missing', 'label': 'Missing'}
                     ]}
                ]
            },

            'routes': {
                'title': f'Routing Table{f" - {device_name}" if device_name else ""}',
                'subtitle': 'IP routing information',
                'icon_class': 'bi-signpost',
                'query': get_routes_query(),
                'columns': [
                    {'key': 'device_name', 'label': 'Device', 'type': 'device_link', 'sortable': True},
                    {'key': 'destination_network', 'label': 'Destination', 'type': 'code', 'sortable': True},
                    {'key': 'prefix_length', 'label': 'Prefix', 'sortable': True},
                    {'key': 'next_hop', 'label': 'Next Hop', 'type': 'code', 'sortable': True},
                    {'key': 'interface_name', 'label': 'Interface', 'sortable': True},
                    {'key': 'protocol', 'label': 'Protocol', 'type': 'badge', 'sortable': True},
                    {'key': 'metric', 'label': 'Metric', 'type': 'metric', 'sortable': True},
                    {'key': 'last_seen', 'label': 'Last Seen', 'type': 'datetime', 'sortable': True}
                ],
                'filters': [
                    {'id': 'searchNetwork', 'name': 'network_search', 'type': 'search', 'label': 'Network/IP'},
                    {'id': 'protocolFilter', 'name': 'protocol', 'type': 'select', 'label': 'Protocol',
                     'options': [
                         {'value': 'static', 'label': 'Static'},
                         {'value': 'connected', 'label': 'Connected'},
                         {'value': 'ospf', 'label': 'OSPF'},
                         {'value': 'bgp', 'label': 'BGP'},
                         {'value': 'rip', 'label': 'RIP'}
                     ]}
                ]
            },

            'bgp': {
                'title': f'BGP Peers{f" - {device_name}" if device_name else ""}',
                'subtitle': 'Border Gateway Protocol neighbors',
                'icon_class': 'bi-globe',
                'query': get_bgp_query(),
                'columns': [
                    {'key': 'device_name', 'label': 'Device', 'type': 'device_link', 'sortable': True},
                    {'key': 'peer_ip', 'label': 'Peer IP', 'type': 'code', 'sortable': True},
                    {'key': 'peer_as', 'label': 'Peer AS', 'type': 'badge', 'badge_class': 'bg-info', 'sortable': True},
                    {'key': 'local_as', 'label': 'Local AS', 'type': 'badge', 'badge_class': 'bg-secondary',
                     'sortable': True},
                    {'key': 'session_state', 'label': 'State', 'type': 'status', 'sortable': True},
                    {'key': 'received_prefixes', 'label': 'Rx Prefixes', 'type': 'metric', 'sortable': True},
                    {'key': 'sent_prefixes', 'label': 'Tx Prefixes', 'type': 'metric', 'sortable': True},
                    {'key': 'last_seen', 'label': 'Last Seen', 'type': 'datetime', 'sortable': True}
                ],
                'filters': [
                    {'id': 'searchPeer', 'name': 'peer_search', 'type': 'search', 'label': 'Peer IP/AS'},
                    {'id': 'stateFilter', 'name': 'session_state', 'type': 'select', 'label': 'State',
                     'options': [
                         {'value': 'established', 'label': 'Established'},
                         {'value': 'idle', 'label': 'Idle'},
                         {'value': 'active', 'label': 'Active'},
                         {'value': 'connect', 'label': 'Connect'}
                     ]}
                ]
            },

            'vlans': {
                'title': f'VLANs{f" - {device_name}" if device_name else ""}',
                'subtitle': 'Virtual LAN configuration',
                'icon_class': 'bi-hdd-network',
                'query': get_vlans_query(),
                'columns': [
                    {'key': 'device_name', 'label': 'Device', 'type': 'device_link', 'sortable': True},
                    {'key': 'vlan_id', 'label': 'VLAN ID', 'type': 'badge', 'badge_class': 'bg-info', 'sortable': True},
                    {'key': 'vlan_name', 'label': 'Name', 'sortable': True},
                    {'key': 'status', 'label': 'Status', 'type': 'status', 'sortable': True},
                    {'key': 'ports', 'label': 'Ports', 'type': 'truncate', 'max_length': 40},
                    {'key': 'last_seen', 'label': 'Last Seen', 'type': 'datetime', 'sortable': True}
                ],
                'filters': [
                    {'id': 'vlanIdFilter', 'name': 'vlan_id', 'type': 'search', 'label': 'VLAN ID'},
                    {'id': 'vlanNameFilter', 'name': 'vlan_name', 'type': 'search', 'label': 'VLAN Name'}
                ]
            }
        }

        if data_type not in table_configs:
            return render_template('search/error.html',
                                   error="Invalid Data Type",
                                   message=f"Data type '{data_type}' is not supported."), 404

        config = table_configs[data_type]

        # Execute query with device filter if specified
        query_func = config['query']
        data = query_func(device_name) if device_name else query_func()

        # Calculate statistics
        stats = []
        if data:
            stats.append({'label': 'Total Records', 'value': len(data), 'color': 'primary'})

            # Add type-specific stats
            if data_type == 'hardware':
                operational = len([d for d in data if d.get('status') == 'operational'])
                stats.append({'label': 'Operational', 'value': operational, 'color': 'success'})
                failed = len([d for d in data if d.get('status') == 'failed'])
                if failed > 0:
                    stats.append({'label': 'Failed', 'value': failed, 'color': 'danger'})

            elif data_type == 'bgp':
                established = len([d for d in data if d.get('session_state') == 'established'])
                stats.append({'label': 'Established', 'value': established, 'color': 'success'})

            elif data_type in ['arp', 'mac_table']:
                unique_devices = len(set(d['device_name'] for d in data))
                stats.append({'label': 'Devices', 'value': unique_devices, 'color': 'info'})

        # Prepare template context
        context = {
            'title': config['title'],
            'subtitle': config.get('subtitle'),
            'icon_class': config.get('icon_class'),
            'data': data,
            'columns': config['columns'],
            'filters': config.get('filters', []),
            'stats': stats,
            'device_name': device_name,
            'back_url': url_for('devices.device_detail', device_name=device_name) if device_name else url_for(
                'search.index'),
            'show_actions': False,  # Can be enabled per data type
            'show_pagination': True,
            'empty_title': f'No {config["title"]} Found',
            'empty_message': f'No {data_type.replace("_", " ")} data is available.',
            'table_title': config['title']
        }

        return render_template('search/table_viewer.html', **context)

    except Exception as e:
        logging.error(f"Error loading {data_type} table: {e}")
        return render_template('search/error.html',
                               error="Error Loading Data",
                               message=str(e)), 500


# Query functions for different data types
def get_arp_query():
    """Get ARP table query function"""

    def query_arp(device_name=None):
        base_query = """
            SELECT 
                d.device_name,
                d.site_code,
                ae.ip_address,
                ae.mac_address,
                ae.interface_name,
                ae.created_at,
                cr.collection_time as last_seen
            FROM arp_entries ae
            JOIN devices d ON ae.device_id = d.id
            JOIN collection_runs cr ON ae.collection_run_id = cr.id
            WHERE cr.id IN (
                SELECT id FROM collection_runs cr2 
                WHERE cr2.device_id = ae.device_id 
                ORDER BY cr2.collection_time DESC 
                LIMIT 1
            )
        """

        params = []
        if device_name:
            base_query += " AND d.device_name = ?"
            params.append(device_name)

        base_query += " ORDER BY d.device_name, ae.ip_address"
        return execute_query(base_query, params)

    return query_arp


def get_mac_table_query():
    """Get MAC address table query function"""

    def query_mac_table(device_name=None):
        base_query = """
            SELECT 
                d.device_name,
                d.site_code,
                mat.mac_address,
                mat.vlan_id,
                mat.interface_name,
                mat.entry_type,
                mat.created_at,
                cr.collection_time as last_seen
            FROM mac_address_table mat
            JOIN devices d ON mat.device_id = d.id
            JOIN collection_runs cr ON mat.collection_run_id = cr.id
            WHERE cr.id IN (
                SELECT id FROM collection_runs cr2 
                WHERE cr2.device_id = mat.device_id 
                ORDER BY cr2.collection_time DESC 
                LIMIT 1
            )
        """

        params = []
        if device_name:
            base_query += " AND d.device_name = ?"
            params.append(device_name)

        base_query += " ORDER BY d.device_name, mat.vlan_id, mat.mac_address"
        return execute_query(base_query, params)

    return query_mac_table


def get_lldp_query():
    """Get LLDP neighbors query function"""

    def query_lldp(device_name=None):
        base_query = """
            SELECT 
                d.device_name as local_device,
                d.site_code as local_site,
                ln.local_interface,
                ln.remote_hostname as remote_device,
                ln.remote_port as remote_interface,
                ln.remote_system_description,
                ln.remote_mgmt_ip,
                cr.collection_time as last_seen
            FROM lldp_neighbors ln
            JOIN devices d ON ln.device_id = d.id
            JOIN collection_runs cr ON ln.collection_run_id = cr.id
            WHERE cr.id IN (
                SELECT id FROM collection_runs cr2 
                WHERE cr2.device_id = ln.device_id 
                ORDER BY cr2.collection_time DESC 
                LIMIT 1
            )
        """

        params = []
        if device_name:
            base_query += " AND d.device_name = ?"
            params.append(device_name)

        base_query += " ORDER BY d.device_name, ln.local_interface"
        return execute_query(base_query, params)

    return query_lldp


def get_hardware_query():
    """Get hardware inventory query function"""

    def query_hardware(device_name=None):
        base_query = """
            SELECT 
                d.device_name,
                d.site_code,
                hi.component_type,
                hi.slot_position,
                hi.part_number,
                hi.serial_number,
                hi.description,
                hi.vendor,
                hi.model,
                hi.status,
                hi.additional_data,
                cr.collection_time as last_seen
            FROM hardware_inventory hi
            JOIN devices d ON hi.device_id = d.id
            JOIN collection_runs cr ON hi.collection_run_id = cr.id
            WHERE cr.id IN (
                SELECT id FROM collection_runs cr2 
                WHERE cr2.device_id = hi.device_id 
                ORDER BY cr2.collection_time DESC 
                LIMIT 1
            )
        """

        params = []
        if device_name:
            base_query += " AND d.device_name = ?"
            params.append(device_name)

        base_query += " ORDER BY d.device_name, hi.component_type, hi.slot_position"
        return execute_query(base_query, params)

    return query_hardware


def get_routes_query():
    """Get routing table query function"""

    def query_routes(device_name=None):
        base_query = """
            SELECT 
                d.device_name,
                d.site_code,
                r.destination_network,
                r.prefix_length,
                r.next_hop,
                r.interface_name,
                r.protocol,
                r.metric,
                r.administrative_distance,
                cr.collection_time as last_seen
            FROM routes r
            JOIN devices d ON r.device_id = d.id
            JOIN collection_runs cr ON r.collection_run_id = cr.id
            WHERE cr.id IN (
                SELECT id FROM collection_runs cr2 
                WHERE cr2.device_id = r.device_id 
                ORDER BY cr2.collection_time DESC 
                LIMIT 1
            )
        """

        params = []
        if device_name:
            base_query += " AND d.device_name = ?"
            params.append(device_name)

        base_query += " ORDER BY d.device_name, r.destination_network"
        return execute_query(base_query, params)

    return query_routes


def get_bgp_query():
    """Get BGP peers query function"""

    def query_bgp(device_name=None):
        base_query = """
            SELECT 
                d.device_name,
                d.site_code,
                bp.peer_ip,
                bp.peer_as,
                bp.local_as,
                bp.peer_state,
                bp.session_state,
                bp.received_prefixes,
                bp.sent_prefixes,
                bp.peer_description,
                cr.collection_time as last_seen
            FROM bgp_peers bp
            JOIN devices d ON bp.device_id = d.id
            JOIN collection_runs cr ON bp.collection_run_id = cr.id
            WHERE cr.id IN (
                SELECT id FROM collection_runs cr2 
                WHERE cr2.device_id = bp.device_id 
                ORDER BY cr2.collection_time DESC 
                LIMIT 1
            )
        """

        params = []
        if device_name:
            base_query += " AND d.device_name = ?"
            params.append(device_name)

        base_query += " ORDER BY d.device_name, bp.peer_ip"
        return execute_query(base_query, params)

    return query_bgp


def get_vlans_query():
    """Get VLANs query function"""

    def query_vlans(device_name=None):
        base_query = """
            SELECT 
                d.device_name,
                d.site_code,
                v.vlan_id,
                v.vlan_name,
                v.status,
                v.ports,
                cr.collection_time as last_seen
            FROM vlans v
            JOIN devices d ON v.device_id = d.id
            JOIN collection_runs cr ON v.collection_run_id = cr.id
            WHERE cr.id IN (
                SELECT id FROM collection_runs cr2 
                WHERE cr2.device_id = v.device_id 
                ORDER BY cr2.collection_time DESC 
                LIMIT 1
            )
        """

        params = []
        if device_name:
            base_query += " AND d.device_name = ?"
            params.append(device_name)

        base_query += " ORDER BY d.device_name, v.vlan_id"
        return execute_query(base_query, params)

    return query_vlans

@search_bp.route('/')
def index():
    """Main search interface"""
    return render_template('search/index.html')


@search_bp.route('/api/comprehensive')
def api_comprehensive_search():
    """Comprehensive search API across all data types"""
    try:
        search_term = request.args.get('search', '').strip()
        category = request.args.get('category', 'all')
        device_filter = request.args.get('device', '')
        site_filter = request.args.get('site', '')
        search_mode = request.args.get('mode', 'smart')
        time_range = request.args.get('time_range', '')
        vendor_filter = request.args.get('vendor', '')
        status_filter = request.args.get('status', '')
        include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'

        if not search_term:
            return jsonify({'error': 'Search term is required'}), 400

        # Determine search strategy based on term and mode
        search_strategy = determine_search_strategy(search_term, search_mode)

        results = {
            'search_term': search_term,
            'search_strategy': search_strategy,
            'total_results': 0,
            'device_count': 0,
            'data_types_found': 0,
            'configurations': [],
            'network_data': [],
            'interfaces': [],
            'topology': [],
            'hardware': [],
            'routing': [],
            'environment': []
        }

        # Build base filters
        base_filters = build_base_filters(device_filter, site_filter, vendor_filter,
                                          status_filter, time_range, include_inactive)

        # Search based on category
        if category in ['all', 'config']:
            results['configurations'] = search_configurations(search_term, search_strategy, base_filters)

        if category in ['all', 'network']:
            results['network_data'] = search_network_data(search_term, search_strategy, base_filters)

        if category in ['all', 'interfaces']:
            results['interfaces'] = search_interfaces(search_term, search_strategy, base_filters)

        if category in ['all', 'topology']:
            results['topology'] = search_topology(search_term, search_strategy, base_filters)

        if category in ['all', 'hardware']:
            results['hardware'] = search_hardware(search_term, search_strategy, base_filters)

        if category in ['all', 'routing']:
            results['routing'] = search_routing(search_term, search_strategy, base_filters)

        if category in ['all', 'environment']:
            results['environment'] = search_environment(search_term, search_strategy, base_filters)

        # Calculate summary statistics
        results['total_results'] = (len(results['configurations']) + len(results['network_data']) +
                                    len(results['interfaces']) + len(results['topology']) +
                                    len(results['hardware']) + len(results['routing']) +
                                    len(results['environment']))

        # Count unique devices
        all_devices = set()
        for data_type in ['configurations', 'network_data', 'interfaces', 'topology', 'hardware', 'routing',
                          'environment']:
            for item in results[data_type]:
                if 'device_name' in item:
                    all_devices.add(item['device_name'])
        results['device_count'] = len(all_devices)

        # Count data types with results
        results['data_types_found'] = sum(1 for key in ['configurations', 'network_data', 'interfaces',
                                                        'topology', 'hardware', 'routing', 'environment']
                                          if len(results[key]) > 0)

        return jsonify(results)

    except Exception as e:
        logging.error(f"Search error: {e}")
        return jsonify({'error': str(e)}), 500


def determine_search_strategy(search_term, search_mode):
    """Determine the best search strategy based on the search term"""
    if search_mode == 'exact':
        return 'exact'
    elif search_mode == 'regex':
        return 'regex'
    elif search_mode == 'contains':
        return 'contains'
    elif search_mode == 'smart':
        # Auto-detect based on pattern
        if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', search_term):
            return 'ip_address'
        elif re.match(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$', search_term):
            return 'mac_address'
        elif re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$', search_term):
            return 'subnet'
        elif re.match(r'^vlan\s*\d+$', search_term, re.IGNORECASE):
            return 'vlan'
        elif re.match(r'^(Gi|Te|Eth|Fa|Lo|Tu|Po)', search_term, re.IGNORECASE):
            return 'interface'
        elif search_term.lower() in ['up', 'down', 'enabled', 'disabled']:
            return 'status'
        else:
            return 'contains'

    return 'contains'


def build_base_filters(device_filter, site_filter, vendor_filter, status_filter, time_range, include_inactive):
    """Build common filters for all search queries"""
    filters = {
        'device_conditions': [],
        'device_params': [],
        'time_conditions': [],
        'time_params': []
    }

    # Device filters
    if device_filter:
        filters['device_conditions'].append("d.device_name = ?")
        filters['device_params'].append(device_filter)

    if site_filter:
        filters['device_conditions'].append("d.site_code = ?")
        filters['device_params'].append(site_filter)

    if vendor_filter:
        filters['device_conditions'].append("LOWER(d.vendor) = LOWER(?)")
        filters['device_params'].append(vendor_filter)

    if not include_inactive:
        filters['device_conditions'].append("d.is_active = 1")

    # Time range filters
    if time_range:
        time_condition, time_param = build_time_filter(time_range)
        if time_condition:
            filters['time_conditions'].append(time_condition)
            if time_param:
                filters['time_params'].append(time_param)

    return filters


def build_time_filter(time_range):
    """Build time filter condition"""
    if time_range == '1h':
        return "created_at >= datetime('now', '-1 hour')", None
    elif time_range == '24h':
        return "created_at >= datetime('now', '-24 hours')", None
    elif time_range == '7d':
        return "created_at >= datetime('now', '-7 days')", None
    elif time_range == '30d':
        return "created_at >= datetime('now', '-30 days')", None
    return None, None


def search_configurations(search_term, search_strategy, base_filters):
    """Search device configurations"""
    try:
        # Build search condition based on strategy
        if search_strategy == 'exact':
            search_condition = "dc.config_content = ?"
            search_params = [search_term]
        elif search_strategy == 'regex':
            # SQLite doesn't have full regex, use LIKE with wildcards
            search_condition = "dc.config_content LIKE ?"
            search_params = [f"%{search_term}%"]
        else:
            search_condition = "dc.config_content LIKE ?"
            search_params = [f"%{search_term}%"]

        # Get latest configs only
        query = f"""
            WITH latest_configs AS (
                SELECT device_id, config_type, MAX(created_at) as latest_time
                FROM device_configs
                GROUP BY device_id, config_type
            )
            SELECT DISTINCT
                dc.id as config_id,
                dc.config_type,
                dc.size_bytes as config_size,
                dc.created_at,
                d.device_name,
                d.vendor,
                d.model,
                d.site_code,
                1 as match_count
            FROM device_configs dc
            INNER JOIN devices d ON dc.device_id = d.id
            INNER JOIN latest_configs lc ON 
                dc.device_id = lc.device_id 
                AND dc.config_type = lc.config_type 
                AND dc.created_at = lc.latest_time
            WHERE {search_condition}
        """

        params = search_params.copy()

        # Add device filters
        if base_filters['device_conditions']:
            query += " AND " + " AND ".join(base_filters['device_conditions'])
            params.extend(base_filters['device_params'])

        query += " ORDER BY d.device_name, dc.config_type LIMIT 100"

        results = execute_query(query, params)

        # Count actual matches for each config
        for result in results:
            try:
                result['match_count'] = count_matches_in_config(result['config_id'], search_term, search_strategy)
            except:
                result['match_count'] = 1

        return results

    except Exception as e:
        logging.error(f"Error searching configurations: {e}")
        return []


def count_matches_in_config(config_id, search_term, search_strategy):
    """Count actual matches in a configuration"""
    try:
        config_query = "SELECT config_content FROM device_configs WHERE id = ?"
        config_result = execute_query(config_query, [config_id])

        if not config_result:
            return 0

        content = config_result[0]['config_content'].lower()
        search_lower = search_term.lower()

        if search_strategy == 'exact':
            return content.count(search_lower)
        else:
            return content.count(search_lower)

    except Exception as e:
        logging.error(f"Error counting matches: {e}")
        return 0


def search_network_data(search_term, search_strategy, base_filters):
    """Search network-related data with enhanced MAC/IP correlation"""
    results = []

    try:
        # Normalize search term for MAC addresses
        normalized_mac = normalize_mac_for_search(search_term)

        # Search IP addresses
        if search_strategy in ['ip_address', 'subnet', 'contains']:
            # Device IPs
            ip_query = """
                SELECT 'device_ip' as data_type, d.device_name, d.site_code,
                       di.ip_address as search_match, di.ip_type, di.interface_name, di.vlan_id,
                       di.updated_at as last_seen, NULL as mac_address, NULL as entry_type,
                       'Device IP Assignment' as description
                FROM device_ips di
                JOIN devices d ON di.device_id = d.id
                WHERE di.ip_address LIKE ?
            """

            params = [f"%{search_term}%"]
            if base_filters['device_conditions']:
                ip_query += " AND " + " AND ".join(base_filters['device_conditions'])
                params.extend(base_filters['device_params'])

            ip_results = execute_query(ip_query, params)
            results.extend(ip_results)

            # For each IP found, look for corresponding ARP entries across all devices
            for ip_result in ip_results:
                ip_address = ip_result['search_match']
                arp_correlation_query = """
                    SELECT 'arp_correlation' as data_type, d.device_name, d.site_code,
                           ae.ip_address as search_match, 'ARP' as ip_type, ae.interface_name, NULL as vlan_id,
                           ae.created_at as last_seen, ae.mac_address, ae.entry_type,
                           'ARP Entry for ' || ? as description
                    FROM arp_entries ae
                    JOIN devices d ON ae.device_id = d.id
                    JOIN collection_runs cr ON ae.collection_run_id = cr.id
                    WHERE ae.ip_address = ?
                    AND cr.id IN (
                        SELECT id FROM collection_runs cr2 
                        WHERE cr2.device_id = ae.device_id 
                        ORDER BY cr2.collection_time DESC 
                        LIMIT 1
                    )
                """

                arp_params = [ip_address, ip_address]
                if base_filters['device_conditions']:
                    arp_correlation_query += " AND " + " AND ".join(base_filters['device_conditions'])
                    arp_params.extend(base_filters['device_params'])

                arp_correlations = execute_query(arp_correlation_query, arp_params)
                results.extend(arp_correlations)

            # ARP table IPs (standalone)
            arp_ip_query = """
                SELECT 'arp_ip' as data_type, d.device_name, d.site_code,
                       ae.ip_address as search_match, 'ARP' as ip_type, ae.interface_name, NULL as vlan_id,
                       ae.created_at as last_seen, ae.mac_address, ae.entry_type,
                       'ARP Table Entry' as description
                FROM arp_entries ae
                JOIN devices d ON ae.device_id = d.id
                JOIN collection_runs cr ON ae.collection_run_id = cr.id
                WHERE ae.ip_address LIKE ?
                AND cr.id IN (
                    SELECT id FROM collection_runs cr2 
                    WHERE cr2.device_id = ae.device_id 
                    ORDER BY cr2.collection_time DESC 
                    LIMIT 1
                )
            """

            params = [f"%{search_term}%"]
            if base_filters['device_conditions']:
                arp_ip_query += " AND " + " AND ".join(base_filters['device_conditions'])
                params.extend(base_filters['device_params'])

            results.extend(execute_query(arp_ip_query, params))

        # Search MAC addresses with enhanced correlation
        if search_strategy in ['mac_address', 'contains'] or normalized_mac:
            # MAC address table
            mac_query = """
                SELECT 'mac_table' as data_type, d.device_name, d.site_code,
                       mat.mac_address as search_match, 'L2 Table' as ip_type, mat.interface_name, mat.vlan_id,
                       mat.created_at as last_seen, mat.mac_address, mat.entry_type,
                       'MAC Table Entry (VLAN ' || COALESCE(CAST(mat.vlan_id AS TEXT), 'N/A') || ')' as description
                FROM mac_address_table mat
                JOIN devices d ON mat.device_id = d.id
                JOIN collection_runs cr ON mat.collection_run_id = cr.id
                WHERE mat.mac_address LIKE ?
                AND cr.id IN (
                    SELECT id FROM collection_runs cr2 
                    WHERE cr2.device_id = mat.device_id 
                    ORDER BY cr2.collection_time DESC 
                    LIMIT 1
                )
            """

            mac_search_terms = [normalized_mac, search_term.upper(), search_term.lower()]
            mac_results = []

            for mac_term in mac_search_terms:
                if mac_term:
                    params = [f"%{mac_term}%"]
                    if base_filters['device_conditions']:
                        temp_query = mac_query + " AND " + " AND ".join(base_filters['device_conditions'])
                        params.extend(base_filters['device_params'])
                    else:
                        temp_query = mac_query

                    temp_results = execute_query(temp_query, params)
                    mac_results.extend(temp_results)

            # Remove duplicates
            seen = set()
            unique_mac_results = []
            for result in mac_results:
                key = (result['device_name'], result['search_match'], result['interface_name'])
                if key not in seen:
                    seen.add(key)
                    unique_mac_results.append(result)

            results.extend(unique_mac_results)

            # For each MAC found, look for corresponding ARP entries (MAC→IP mapping)
            for mac_result in unique_mac_results:
                mac_address = mac_result['search_match']
                arp_correlation_query = """
                    SELECT 'arp_for_mac' as data_type, d.device_name, d.site_code,
                           ae.ip_address as search_match, 'ARP→IP' as ip_type, ae.interface_name, NULL as vlan_id,
                           ae.created_at as last_seen, ae.mac_address, ae.entry_type,
                           'IP Address for MAC ' || ae.mac_address as description
                    FROM arp_entries ae
                    JOIN devices d ON ae.device_id = d.id
                    JOIN collection_runs cr ON ae.collection_run_id = cr.id
                    WHERE ae.mac_address = ?
                    AND cr.id IN (
                        SELECT id FROM collection_runs cr2 
                        WHERE cr2.device_id = ae.device_id 
                        ORDER BY cr2.collection_time DESC 
                        LIMIT 1
                    )
                """

                arp_params = [mac_address]
                if base_filters['device_conditions']:
                    arp_correlation_query += " AND " + " AND ".join(base_filters['device_conditions'])
                    arp_params.extend(base_filters['device_params'])

                arp_correlations = execute_query(arp_correlation_query, arp_params)

                # Mark these as correlated results
                for arp_corr in arp_correlations:
                    arp_corr['is_correlation'] = True
                    arp_corr['correlation_source'] = f"MAC {mac_address}"

                results.extend(arp_correlations)

            # ARP table MACs (standalone)
            arp_mac_query = """
                SELECT 'arp_mac' as data_type, d.device_name, d.site_code,
                       ae.mac_address as search_match, 'ARP' as ip_type, ae.interface_name, NULL as vlan_id,
                       ae.created_at as last_seen, ae.mac_address, ae.entry_type,
                       'ARP Table MAC Entry (IP: ' || ae.ip_address || ')' as description
                FROM arp_entries ae
                JOIN devices d ON ae.device_id = d.id
                JOIN collection_runs cr ON ae.collection_run_id = cr.id
                WHERE ae.mac_address LIKE ?
                AND cr.id IN (
                    SELECT id FROM collection_runs cr2 
                    WHERE cr2.device_id = ae.device_id 
                    ORDER BY cr2.collection_time DESC 
                    LIMIT 1
                )
            """

            for mac_term in mac_search_terms:
                if mac_term:
                    params = [f"%{mac_term}%"]
                    if base_filters['device_conditions']:
                        temp_query = arp_mac_query + " AND " + " AND ".join(base_filters['device_conditions'])
                        params.extend(base_filters['device_params'])
                    else:
                        temp_query = arp_mac_query

                    results.extend(execute_query(temp_query, params))

        # Search VLANs
        if search_strategy in ['vlan', 'contains']:
            # Extract VLAN ID if format is "vlan 100"
            vlan_match = re.search(r'vlan\s*(\d+)', search_term, re.IGNORECASE)
            if vlan_match:
                vlan_id = vlan_match.group(1)
                vlan_condition = "v.vlan_id = ?"
                vlan_params = [int(vlan_id)]
            else:
                vlan_condition = "v.vlan_name LIKE ? OR CAST(v.vlan_id AS TEXT) LIKE ?"
                vlan_params = [f"%{search_term}%", f"%{search_term}%"]

            vlan_query = f"""
                SELECT 'vlan' as data_type, d.device_name, d.site_code,
                       'VLAN ' || CAST(v.vlan_id AS TEXT) || ': ' || COALESCE(v.vlan_name, 'Unnamed') as search_match, 
                       'VLAN' as ip_type, NULL as interface_name, v.vlan_id,
                       v.created_at as last_seen, NULL as mac_address, v.status as entry_type,
                       'VLAN Configuration' as description
                FROM vlans v
                JOIN devices d ON v.device_id = d.id
                JOIN collection_runs cr ON v.collection_run_id = cr.id
                WHERE {vlan_condition}
                AND cr.id IN (
                    SELECT id FROM collection_runs cr2 
                    WHERE cr2.device_id = v.device_id 
                    ORDER BY cr2.collection_time DESC 
                    LIMIT 1
                )
            """

            params = vlan_params.copy()
            if base_filters['device_conditions']:
                vlan_query += " AND " + " AND ".join(base_filters['device_conditions'])
                params.extend(base_filters['device_params'])

            results.extend(execute_query(vlan_query, params))

        # ENHANCED: Add interface IP correlation
        if search_strategy in ['ip_address', 'contains']:
            # Find interfaces with matching IPs
            interface_ip_query = """
                SELECT 'interface_ip' as data_type, d.device_name, d.site_code,
                       iip.ip_address || '/' || iip.prefix_length as search_match, 
                       'Interface IP' as ip_type, i.interface_name, i.vlan_id,
                       i.created_at as last_seen, NULL as mac_address, 
                       CASE WHEN iip.is_secondary = 1 THEN 'secondary' ELSE 'primary' END as entry_type,
                       'Interface IP Assignment' as description
                FROM interface_ips iip
                JOIN interfaces i ON iip.interface_id = i.id
                JOIN devices d ON i.device_id = d.id
                JOIN collection_runs cr ON i.collection_run_id = cr.id
                WHERE iip.ip_address LIKE ?
                AND cr.id IN (
                    SELECT id FROM collection_runs cr2 
                    WHERE cr2.device_id = i.device_id 
                    ORDER BY cr2.collection_time DESC 
                    LIMIT 1
                )
            """

            params = [f"%{search_term}%"]
            if base_filters['device_conditions']:
                interface_ip_query += " AND " + " AND ".join(base_filters['device_conditions'])
                params.extend(base_filters['device_params'])

            results.extend(execute_query(interface_ip_query, params))

    except Exception as e:
        logging.error(f"Error searching network data: {e}")

    # Sort results to put correlations together
    def sort_key(item):
        # Primary data first, then correlations
        priority = 0 if not item.get('is_correlation') else 1
        return (priority, item['device_name'], item['data_type'])

    results.sort(key=sort_key)
    return results[:100]  # Limit results


def get_mac_ip_correlation(search_term, search_strategy):
    """Get comprehensive MAC↔IP correlation data"""
    try:
        correlations = {
            'mac_to_ip': [],
            'ip_to_mac': [],
            'summary': {}
        }

        is_mac_search = search_strategy == 'mac_address' or re.match(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$',
                                                                     search_term)
        is_ip_search = search_strategy == 'ip_address' or re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', search_term)

        if is_mac_search:
            # Search for IP addresses associated with this MAC
            normalized_mac = normalize_mac_for_search(search_term)

            # Get ARP entries for this MAC
            arp_query = """
                SELECT DISTINCT
                    d.device_name,
                    d.site_code,
                    ae.ip_address,
                    ae.mac_address,
                    ae.interface_name,
                    ae.age,
                    ae.entry_type,
                    ae.created_at as last_seen,
                    'arp' as source_table
                FROM arp_entries ae
                JOIN devices d ON ae.device_id = d.id
                JOIN collection_runs cr ON ae.collection_run_id = cr.id
                WHERE ae.mac_address = ?
                AND cr.id IN (
                    SELECT id FROM collection_runs cr2 
                    WHERE cr2.device_id = ae.device_id 
                    ORDER BY cr2.collection_time DESC 
                    LIMIT 1
                )
                ORDER BY ae.created_at DESC
            """

            correlations['mac_to_ip'] = execute_query(arp_query, [normalized_mac])

            # Get MAC table entries for this MAC
            mac_table_query = """
                SELECT DISTINCT
                    d.device_name,
                    d.site_code,
                    mat.mac_address,
                    mat.vlan_id,
                    mat.interface_name,
                    mat.entry_type,
                    mat.is_active,
                    mat.moves,
                    mat.created_at as last_seen,
                    'mac_table' as source_table
                FROM mac_address_table mat
                JOIN devices d ON mat.device_id = d.id
                JOIN collection_runs cr ON mat.collection_run_id = cr.id
                WHERE mat.mac_address = ?
                AND cr.id IN (
                    SELECT id FROM collection_runs cr2 
                    WHERE cr2.device_id = mat.device_id 
                    ORDER BY cr2.collection_time DESC 
                    LIMIT 1
                )
                ORDER BY mat.created_at DESC
            """

            mac_table_results = execute_query(mac_table_query, [normalized_mac])
            correlations['mac_table_entries'] = mac_table_results

        elif is_ip_search:
            # Search for MAC addresses associated with this IP
            ip_to_mac_query = """
                SELECT DISTINCT
                    d.device_name,
                    d.site_code,
                    ae.ip_address,
                    ae.mac_address,
                    ae.interface_name,
                    ae.age,
                    ae.entry_type,
                    ae.created_at as last_seen,
                    'arp' as source_table
                FROM arp_entries ae
                JOIN devices d ON ae.device_id = d.id
                JOIN collection_runs cr ON ae.collection_run_id = cr.id
                WHERE ae.ip_address = ?
                AND cr.id IN (
                    SELECT id FROM collection_runs cr2 
                    WHERE cr2.device_id = ae.device_id 
                    ORDER BY cr2.collection_time DESC 
                    LIMIT 1
                )
                ORDER BY ae.created_at DESC
            """

            correlations['ip_to_mac'] = execute_query(ip_to_mac_query, [search_term])

            # For each MAC found, get its L2 table entries
            for arp_entry in correlations['ip_to_mac']:
                mac_address = arp_entry['mac_address']

                mac_l2_query = """
                    SELECT DISTINCT
                        d.device_name,
                        d.site_code,
                        mat.mac_address,
                        mat.vlan_id,
                        mat.interface_name,
                        mat.entry_type,
                        mat.is_active,
                        mat.moves,
                        mat.created_at as last_seen,
                        'mac_table' as source_table
                    FROM mac_address_table mat
                    JOIN devices d ON mat.device_id = d.id
                    JOIN collection_runs cr ON mat.collection_run_id = cr.id
                    WHERE mat.mac_address = ?
                    AND cr.id IN (
                        SELECT id FROM collection_runs cr2 
                        WHERE cr2.device_id = mat.device_id 
                        ORDER BY cr2.collection_time DESC 
                        LIMIT 1
                    )
                """

                mac_entries = execute_query(mac_l2_query, [mac_address])
                if 'mac_table_entries' not in correlations:
                    correlations['mac_table_entries'] = []
                correlations['mac_table_entries'].extend(mac_entries)

        # Generate summary
        total_arp_entries = len(correlations.get('mac_to_ip', [])) + len(correlations.get('ip_to_mac', []))
        total_mac_entries = len(correlations.get('mac_table_entries', []))
        unique_devices = set()

        for data_list in correlations.values():
            if isinstance(data_list, list):
                for entry in data_list:
                    if 'device_name' in entry:
                        unique_devices.add(entry['device_name'])

        correlations['summary'] = {
            'total_arp_entries': total_arp_entries,
            'total_mac_entries': total_mac_entries,
            'unique_devices': len(unique_devices),
            'search_term': search_term,
            'search_type': 'MAC Address' if is_mac_search else 'IP Address' if is_ip_search else 'General'
        }

        return correlations

    except Exception as e:
        logging.error(f"Error getting MAC/IP correlation: {e}")
        return {'mac_to_ip': [], 'ip_to_mac': [], 'mac_table_entries': [], 'summary': {}}


@search_bp.route('/api/correlation')
def api_correlation_search():
    """API endpoint for MAC/IP correlation search"""
    try:
        search_term = request.args.get('search', '').strip()
        if not search_term:
            return jsonify({'error': 'Search term is required'}), 400

        search_strategy = determine_search_strategy(search_term, 'smart')
        base_filters = build_base_filters(
            request.args.get('device', ''),
            request.args.get('site', ''),
            request.args.get('vendor', ''),
            request.args.get('status', ''),
            request.args.get('time_range', ''),
            request.args.get('include_inactive', 'false').lower() == 'true'
        )

        correlation_data = get_mac_ip_correlation(search_term, search_strategy)

        return jsonify({
            'search_term': search_term,
            'search_strategy': search_strategy,
            'correlation': correlation_data,
            'has_results': any(len(data) > 0 for data in correlation_data.values() if isinstance(data, list))
        })

    except Exception as e:
        logging.error(f"Error in correlation search: {e}")
        return jsonify({'error': str(e)}), 500


def enhanced_network_result_formatter(results):
    """Format network search results with enhanced correlation display"""
    formatted_results = []

    # Group results by correlation
    correlation_groups = {}
    standalone_results = []

    for result in results:
        if result.get('is_correlation'):
            source = result.get('correlation_source', 'unknown')
            if source not in correlation_groups:
                correlation_groups[source] = []
            correlation_groups[source].append(result)
        else:
            # Check if this result has correlations
            search_match = result.get('search_match', '')
            has_correlations = any(r.get('correlation_source', '').endswith(search_match) for r in results)

            if has_correlations:
                if search_match not in correlation_groups:
                    correlation_groups[search_match] = []
                correlation_groups[search_match].insert(0, result)  # Put original first
            else:
                standalone_results.append(result)

    # Format correlation groups
    for group_key, group_results in correlation_groups.items():
        if len(group_results) > 1:
            # This is a correlation group
            primary_result = group_results[0]
            correlated_results = group_results[1:]

            formatted_result = {
                **primary_result,
                'has_correlations': True,
                'correlation_count': len(correlated_results),
                'correlated_data': correlated_results,
                'group_key': group_key
            }
            formatted_results.append(formatted_result)
        else:
            # Single result
            formatted_results.append(group_results[0])

    # Add standalone results
    formatted_results.extend(standalone_results)

    return formatted_results


def search_interfaces(search_term, search_strategy, base_filters):
    """Search interface data"""
    try:
        # Build interface search condition
        if search_strategy == 'interface':
            interface_condition = "i.interface_name LIKE ?"
            params = [f"%{search_term}%"]
        elif search_strategy == 'status':
            if search_term.lower() in ['up', 'down']:
                interface_condition = "i.oper_status = ?"
                params = [search_term.lower()]
            elif search_term.lower() in ['enabled', 'disabled']:
                interface_condition = "i.admin_status = ?"
                params = [search_term.lower()]
            else:
                interface_condition = "i.interface_name LIKE ? OR i.description LIKE ?"
                params = [f"%{search_term}%", f"%{search_term}%"]
        else:
            interface_condition = "i.interface_name LIKE ? OR i.description LIKE ?"
            params = [f"%{search_term}%", f"%{search_term}%"]

        # Get latest interfaces
        query = f"""
            SELECT i.*, d.device_name, d.site_code, cr.collection_time
            FROM interfaces i
            JOIN devices d ON i.device_id = d.id
            JOIN collection_runs cr ON i.collection_run_id = cr.id
            WHERE {interface_condition}
            AND cr.id IN (
                SELECT id FROM collection_runs cr2 
                WHERE cr2.device_id = i.device_id 
                ORDER BY cr2.collection_time DESC 
                LIMIT 1
            )
        """

        if base_filters['device_conditions']:
            query += " AND " + " AND ".join(base_filters['device_conditions'])
            params.extend(base_filters['device_params'])

        query += " ORDER BY d.device_name, i.interface_name LIMIT 100"

        return execute_query(query, params)

    except Exception as e:
        logging.error(f"Error searching interfaces: {e}")
        return []


def search_topology(search_term, search_strategy, base_filters):
    """Search LLDP topology data"""
    try:
        topology_condition = """
            (ln.remote_hostname LIKE ? OR 
             ln.local_interface LIKE ? OR 
             ln.remote_port LIKE ? OR
             ln.remote_system_description LIKE ?)
        """
        params = [f"%{search_term}%"] * 4

        query = f"""
            SELECT 
                d.device_name as local_device,
                d.site_code as local_site,
                ln.local_interface,
                ln.remote_hostname as remote_device,
                ln.remote_port as remote_interface,
                ln.remote_system_description,
                'lldp' as connection_type,
                cr.collection_time as last_seen
            FROM lldp_neighbors ln
            JOIN devices d ON ln.device_id = d.id
            JOIN collection_runs cr ON ln.collection_run_id = cr.id
            WHERE {topology_condition}
            AND cr.id IN (
                SELECT id FROM collection_runs cr2 
                WHERE cr2.device_id = ln.device_id 
                ORDER BY cr2.collection_time DESC 
                LIMIT 1
            )
        """

        if base_filters['device_conditions']:
            query += " AND " + " AND ".join(base_filters['device_conditions'])
            params.extend(base_filters['device_params'])

        query += " ORDER BY d.device_name, ln.local_interface LIMIT 50"

        return execute_query(query, params)

    except Exception as e:
        logging.error(f"Error searching topology: {e}")
        return []


def search_hardware(search_term, search_strategy, base_filters):
    """Search hardware inventory including optics"""
    try:
        hardware_condition = """
            (hi.component_type LIKE ? OR 
             hi.part_number LIKE ? OR 
             hi.serial_number LIKE ? OR
             hi.description LIKE ? OR
             hi.vendor LIKE ? OR
             hi.model LIKE ?)
        """
        params = [f"%{search_term}%"] * 6

        query = f"""
            SELECT 
                hi.*,
                d.device_name,
                d.site_code,
                cr.collection_time as last_seen
            FROM hardware_inventory hi
            JOIN devices d ON hi.device_id = d.id
            JOIN collection_runs cr ON hi.collection_run_id = cr.id
            WHERE {hardware_condition}
            AND cr.id IN (
                SELECT id FROM collection_runs cr2 
                WHERE cr2.device_id = hi.device_id 
                ORDER BY cr2.collection_time DESC 
                LIMIT 1
            )
        """

        if base_filters['device_conditions']:
            query += " AND " + " AND ".join(base_filters['device_conditions'])
            params.extend(base_filters['device_params'])

        query += " ORDER BY d.device_name, hi.component_type, hi.slot_position LIMIT 100"

        results = execute_query(query, params)

        # Add optics data for transceivers
        for result in results:
            if result['component_type'] == 'transceiver' and result['additional_data']:
                try:
                    optics_data = json.loads(result['additional_data'])
                    result['optics_input_power'] = optics_data.get('input_power_dbm')
                    result['optics_output_power'] = optics_data.get('output_power_dbm')
                    result['optics_bias_current'] = optics_data.get('laser_bias_current_ma')
                except:
                    pass

        return results

    except Exception as e:
        logging.error(f"Error searching hardware: {e}")
        return []


def search_routing(search_term, search_strategy, base_filters):
    """Search routing table and BGP data"""
    results = []

    try:
        # Search routes
        if search_strategy in ['ip_address', 'subnet', 'contains']:
            route_condition = """
                (r.destination_network LIKE ? OR 
                 r.next_hop LIKE ? OR
                 r.interface_name LIKE ? OR
                 r.protocol LIKE ?)
            """
            params = [f"%{search_term}%"] * 4

            route_query = f"""
                SELECT 'route' as data_type,
                       d.device_name, d.site_code,
                       r.destination_network,
                       r.prefix_length,
                       r.next_hop,
                       r.interface_name,
                       r.protocol,
                       r.metric,
                       r.administrative_distance,
                       cr.collection_time as last_seen
                FROM routes r
                JOIN devices d ON r.device_id = d.id
                JOIN collection_runs cr ON r.collection_run_id = cr.id
                WHERE {route_condition}
                AND cr.id IN (
                    SELECT id FROM collection_runs cr2 
                    WHERE cr2.device_id = r.device_id 
                    ORDER BY cr2.collection_time DESC 
                    LIMIT 1
                )
            """

            route_params = params.copy()
            if base_filters['device_conditions']:
                route_query += " AND " + " AND ".join(base_filters['device_conditions'])
                route_params.extend(base_filters['device_params'])

            route_query += " ORDER BY d.device_name LIMIT 50"
            results.extend(execute_query(route_query, route_params))

        # Search BGP peers
        bgp_condition = """
            (bp.peer_ip LIKE ? OR 
             CAST(bp.peer_as AS TEXT) LIKE ? OR
             bp.peer_description LIKE ?)
        """
        params = [f"%{search_term}%"] * 3

        bgp_query = f"""
            SELECT 'bgp_peer' as data_type,
                   d.device_name, d.site_code,
                   bp.peer_ip,
                   bp.peer_as,
                   bp.local_as,
                   bp.peer_state,
                   bp.session_state,
                   bp.received_prefixes,
                   bp.sent_prefixes,
                   bp.peer_description,
                   cr.collection_time as last_seen
            FROM bgp_peers bp
            JOIN devices d ON bp.device_id = d.id
            JOIN collection_runs cr ON bp.collection_run_id = cr.id
            WHERE {bgp_condition}
            AND cr.id IN (
                SELECT id FROM collection_runs cr2 
                WHERE cr2.device_id = bp.device_id 
                ORDER BY cr2.collection_time DESC 
                LIMIT 1
            )
        """

        bgp_params = params.copy()
        if base_filters['device_conditions']:
            bgp_query += " AND " + " AND ".join(base_filters['device_conditions'])
            bgp_params.extend(base_filters['device_params'])

        bgp_query += " ORDER BY d.device_name LIMIT 50"
        results.extend(execute_query(bgp_query, bgp_params))

    except Exception as e:
        logging.error(f"Error searching routing data: {e}")

    return results


def search_environment(search_term, search_strategy, base_filters):
    """Search environment monitoring data"""
    try:
        # Search environment data for specific thresholds or issues
        environment_conditions = []
        params = []

        if search_term.lower() in ['high', 'critical']:
            environment_conditions.append("ed.cpu_usage > 80")
        elif search_term.lower() in ['cpu', 'processor']:
            environment_conditions.append("ed.cpu_usage IS NOT NULL")
        elif search_term.lower() in ['memory', 'ram']:
            environment_conditions.append("ed.memory_used IS NOT NULL")
        else:
            # General search in JSON data
            environment_conditions.append("""
                (ed.temperature_sensors LIKE ? OR 
                 ed.power_supplies LIKE ? OR
                 ed.fans LIKE ?)
            """)
            params = [f"%{search_term}%"] * 3

        if not environment_conditions:
            return []

        query = f"""
            SELECT 
                d.device_name,
                d.site_code,
                ed.cpu_usage,
                ed.memory_used,
                ed.memory_available,
                ed.memory_total,
                CASE 
                    WHEN ed.memory_total > 0 THEN ROUND((ed.memory_used * 100.0 / ed.memory_total), 2)
                    WHEN ed.memory_available > 0 THEN ROUND((ed.memory_used * 100.0 / (ed.memory_used + ed.memory_available)), 2)
                    ELSE NULL
                END as memory_usage_percent,
                ed.temperature_sensors,
                ed.power_supplies,
                ed.fans,
                ed.created_at as last_seen
            FROM environment_data ed
            JOIN devices d ON ed.device_id = d.id
            JOIN collection_runs cr ON ed.collection_run_id = cr.id
            WHERE {' OR '.join(environment_conditions)}
            AND cr.id IN (
                SELECT id FROM collection_runs cr2 
                WHERE cr2.device_id = ed.device_id 
                ORDER BY cr2.collection_time DESC 
                LIMIT 1
            )
        """

        if base_filters['device_conditions']:
            query += " AND " + " AND ".join(base_filters['device_conditions'])
            params.extend(base_filters['device_params'])

        query += " ORDER BY d.device_name LIMIT 50"

        return execute_query(query, params)

    except Exception as e:
        logging.error(f"Error searching environment data: {e}")
        return []


def normalize_mac_for_search(mac_address):
    """Normalize MAC address for search"""
    if not mac_address:
        return ""

    # Remove common separators and convert to uppercase
    mac = re.sub(r'[:\-\.]', '', mac_address.upper())

    # If it looks like a partial MAC, keep it as-is for LIKE search
    if len(mac) < 12:
        return mac

    # If it's a full MAC, format as XX:XX:XX:XX:XX:XX
    if len(mac) == 12:
        return ':'.join([mac[i:i + 2] for i in range(0, 12, 2)])

    return mac_address


@search_bp.route('/api/suggestions')
def api_search_suggestions():
    """Provide search suggestions based on input"""
    try:
        query = request.args.get('q', '').strip()
        category = request.args.get('category', 'all')

        suggestions = []

        if len(query) >= 2:
            # Device name suggestions
            if category in ['all', 'devices']:
                device_query = """
                    SELECT DISTINCT device_name 
                    FROM devices 
                    WHERE device_name LIKE ? AND is_active = 1
                    ORDER BY device_name LIMIT 10
                """
                devices = execute_query(device_query, [f"%{query}%"])
                suggestions.extend([{'type': 'device', 'value': d['device_name']} for d in devices])

            # Interface suggestions
            if category in ['all', 'interfaces']:
                interface_query = """
                    SELECT DISTINCT interface_name 
                    FROM interfaces 
                    WHERE interface_name LIKE ?
                    ORDER BY interface_name LIMIT 10
                """
                interfaces = execute_query(interface_query, [f"%{query}%"])
                suggestions.extend([{'type': 'interface', 'value': i['interface_name']} for i in interfaces])

            # VLAN suggestions
            if category in ['all', 'network']:
                vlan_query = """
                    SELECT DISTINCT vlan_name, vlan_id
                    FROM vlans 
                    WHERE vlan_name LIKE ? OR CAST(vlan_id AS TEXT) LIKE ?
                    ORDER BY vlan_id LIMIT 10
                """
                vlans = execute_query(vlan_query, [f"%{query}%", f"%{query}%"])
                suggestions.extend(
                    [{'type': 'vlan', 'value': f"VLAN {v['vlan_id']}: {v['vlan_name'] or 'Unnamed'}"} for v in vlans])

        return jsonify({'suggestions': suggestions})

    except Exception as e:
        logging.error(f"Error getting suggestions: {e}")
        return jsonify({'suggestions': []})


@search_bp.route('/api/sites')
def api_sites():
    """Get list of sites for filters"""
    try:
        sites_query = """
            SELECT site_code, COUNT(*) as device_count
            FROM devices 
            WHERE is_active = 1
            GROUP BY site_code 
            ORDER BY site_code
        """
        sites = execute_query(sites_query)
        return jsonify(sites)

    except Exception as e:
        logging.error(f"Error getting sites: {e}")
        return jsonify([])


@search_bp.route('/api/export')
def api_export_results():
    """Export search results in various formats"""
    try:
        # This would implement the actual export functionality
        # For now, return a placeholder
        format_type = request.args.get('format', 'csv')

        return jsonify({
            'message': f'Export in {format_type} format would be implemented here',
            'download_url': f'/search/download/results.{format_type}'
        })

    except Exception as e:
        logging.error(f"Error exporting results: {e}")
        return jsonify({'error': str(e)}), 500


# Detail view endpoints
@search_bp.route('/api/config/<int:config_id>')
def api_config_detail(config_id):
    """Get detailed configuration view"""
    try:
        query = """
            SELECT 
                dc.*,
                d.device_name,
                d.site_code,
                cr.collection_time
            FROM device_configs dc
            JOIN devices d ON dc.device_id = d.id
            JOIN collection_runs cr ON dc.collection_run_id = cr.id
            WHERE dc.id = ?
        """

        result = execute_query(query, [config_id])
        if not result:
            return jsonify({'error': 'Configuration not found'}), 404

        config = result[0]
        return jsonify(config)

    except Exception as e:
        logging.error(f"Error getting config detail: {e}")
        return jsonify({'error': str(e)}), 500


@search_bp.route('/api/hardware/<int:hardware_id>')
def api_hardware_detail(hardware_id):
    """Get detailed hardware view"""
    try:
        query = """
            SELECT 
                hi.*,
                d.device_name,
                d.site_code,
                cr.collection_time
            FROM hardware_inventory hi
            JOIN devices d ON hi.device_id = d.id
            JOIN collection_runs cr ON hi.collection_run_id = cr.id
            WHERE hi.id = ?
        """

        result = execute_query(query, [hardware_id])
        if not result:
            return jsonify({'error': 'Hardware component not found'}), 404

        hardware = result[0]

        # Parse additional data if it's JSON
        if hardware['additional_data']:
            try:
                hardware['parsed_data'] = json.loads(hardware['additional_data'])
            except:
                hardware['parsed_data'] = None

        return jsonify(hardware)

    except Exception as e:
        logging.error(f"Error getting hardware detail: {e}")
        return jsonify({'error': str(e)}), 500


# Configuration viewing routes (moved from config blueprint)
@search_bp.route('/config/view/<int:config_id>')
def view_config(config_id):
    """View a specific configuration"""
    try:
        config_query = """
            SELECT 
                dc.id,
                dc.device_id,
                dc.collection_run_id,
                dc.config_type,
                dc.config_content,
                dc.config_hash,
                dc.size_bytes,
                dc.line_count,
                dc.created_at,
                d.device_name,
                d.site_code,
                cr.collection_time
            FROM device_configs dc
            JOIN devices d ON dc.device_id = d.id
            JOIN collection_runs cr ON dc.collection_run_id = cr.id
            WHERE dc.id = ?
        """
        config_result = execute_query(config_query, [config_id])

        if not config_result:
            return render_template('search/error.html',
                                   error="Configuration not found",
                                   message="The requested configuration could not be found."), 404

        config = config_result[0]
        return render_template('search/view_config.html', config=config)

    except Exception as e:
        logging.error(f"Error loading configuration: {e}")
        return render_template('search/error.html',
                               error="Error loading configuration",
                               message=str(e)), 500


@search_bp.route('/config/compare/<int:old_id>/<int:new_id>')
def compare_configs(old_id, new_id):
    """Compare two configurations"""
    try:
        # Get both configurations
        config_query = """
            SELECT 
                dc.id,
                dc.device_id,
                dc.collection_run_id,
                dc.config_type,
                dc.config_content,
                dc.config_hash,
                dc.size_bytes,
                dc.line_count,
                dc.created_at,
                d.device_name,
                d.site_code,
                cr.collection_time
            FROM device_configs dc
            JOIN devices d ON dc.device_id = d.id
            JOIN collection_runs cr ON dc.collection_run_id = cr.id
            WHERE dc.id IN (?, ?)
            ORDER BY dc.created_at
        """
        configs = execute_query(config_query, [old_id, new_id])

        if len(configs) != 2:
            return render_template('search/error.html',
                                   error="Configuration not found",
                                   message="One or both configurations could not be found."), 404

        old_config = configs[0]
        new_config = configs[1]

        # Get change details if available
        change_query = """
            SELECT * FROM config_changes
            WHERE old_config_id = ? AND new_config_id = ?
        """
        change_result = execute_query(change_query, [old_id, new_id])
        change = change_result[0] if change_result else None

        return render_template('search/compare_configs.html',
                               old_config=old_config,
                               new_config=new_config,
                               change=change)

    except Exception as e:
        logging.error(f"Error comparing configurations: {e}")
        return render_template('search/error.html',
                               error="Error comparing configurations",
                               message=str(e)), 500


@search_bp.route('/config/device/<device_name>')
def device_configs(device_name):
    """Show configurations for a specific device"""
    try:
        # Get device info
        device_query = "SELECT id, device_name, site_code FROM devices WHERE device_name = ? AND is_active = 1"
        device_result = execute_query(device_query, [device_name])

        if not device_result:
            return render_template('search/error.html',
                                   error="Device not found",
                                   message=f"Device '{device_name}' could not be found."), 404

        device = device_result[0]
        device_id = device['id']

        # Get configurations
        configs_query = """
            SELECT 
                dc.id,
                dc.device_id,
                dc.collection_run_id,
                dc.config_type,
                dc.config_hash,
                dc.size_bytes,
                dc.line_count,
                dc.created_at,
                cr.collection_time
            FROM device_configs dc
            JOIN collection_runs cr ON dc.collection_run_id = cr.id
            WHERE dc.device_id = ?
            ORDER BY dc.created_at DESC, dc.config_type
        """
        configs = execute_query(configs_query, [device_id])

        # Get configuration changes
        changes_query = """
            SELECT 
                cc.id,
                cc.device_id,
                cc.old_config_id,
                cc.new_config_id,
                cc.change_type,
                cc.change_summary,
                cc.change_size,
                cc.detected_at,
                nc.config_type,
                nc.created_at as new_config_time,
                oc.created_at as old_config_time
            FROM config_changes cc
            JOIN device_configs nc ON cc.new_config_id = nc.id
            LEFT JOIN device_configs oc ON cc.old_config_id = oc.id
            WHERE cc.device_id = ?
            ORDER BY cc.detected_at DESC
        """
        changes = execute_query(changes_query, [device_id])

        return render_template('search/device_configs.html',
                               device=device,
                               configs=configs,
                               changes=changes)

    except Exception as e:
        logging.error(f"Error loading device configurations: {e}")
        return render_template('search/error.html',
                               error="Error loading configurations",
                               message=str(e)), 500

