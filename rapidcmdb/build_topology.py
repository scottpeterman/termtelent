#!/usr/bin/env python3
"""
LLDP to Map JSON Converter
Converts NAPALM CMDB LLDP data to the map.json format for existing topology tools
"""

import sqlite3
import json
import argparse
import re
from collections import defaultdict
from datetime import datetime


class LLDPMapConverter:
    def __init__(self, db_path='napalm_cmdb.db'):
        """Initialize converter with database path"""
        self.db_path = db_path

    def get_db_connection(self):
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def execute_query(self, query, params=None):
        """Helper method for debug queries"""
        conn = self.get_db_connection()
        try:
            if params:
                cursor = conn.execute(query, params)
            else:
                cursor = conn.execute(query)
            results = cursor.fetchall()
            return [dict(row) for row in results]
        except Exception as e:
            print(f"Query error: {e}")
            return []
        finally:
            conn.close()

    def debug_database_contents(self):
        """Debug function to show what's actually in the database"""
        print("=== DATABASE DEBUGGING ===")

        # Show available sites
        sites_query = "SELECT DISTINCT site_code FROM devices WHERE is_active = 1 ORDER BY site_code"
        sites = self.execute_query(sites_query)
        print(f"Available site codes: {[s['site_code'] for s in sites]}")

        # Show available device names with frs
        devices_query = """
        SELECT device_name, hostname, site_code, device_role, vendor, model
        FROM devices 
        WHERE is_active = 1 AND (device_name LIKE '%frs%' OR hostname LIKE '%frs%')
        ORDER BY device_name
        """
        devices = self.execute_query(devices_query)
        print(f"Devices with 'frs' in name: {len(devices)} found")
        for device in devices[:10]:  # Show first 10
            print(
                f"  {device['device_name']} | site: {device['site_code']} | role: {device['device_role']} | {device['vendor']} {device['model']}")

        # Check for LLDP data
        lldp_query = """
        SELECT COUNT(*) as count
        FROM lldp_neighbors ln
        JOIN devices d ON ln.device_id = d.id
        WHERE d.is_active = 1
        """
        lldp_count = self.execute_query(lldp_query)
        print(f"Total LLDP entries: {lldp_count[0]['count'] if lldp_count else 0}")

        # Show recent collection runs
        collections_query = """
        SELECT d.device_name, cr.collection_time, cr.success
        FROM collection_runs cr
        JOIN devices d ON cr.device_id = d.id
        WHERE d.is_active = 1 AND (d.device_name LIKE '%frs%' OR d.hostname LIKE '%frs%')
        ORDER BY cr.collection_time DESC
        LIMIT 5
        """
        collections = self.execute_query(collections_query)
        print(f"Recent collections for frs devices:")
        for col in collections:
            print(f"  {col['device_name']} | {col['collection_time']} | success: {col['success']}")

        print("========================\n")

    def normalize_hostname(self, hostname):
        """Clean up hostname - remove domain suffixes, handle empty values"""
        if not hostname or not hostname.strip():
            return ""

        # Remove common domain suffixes (case insensitive)
        name = hostname.strip()

        # Common domain patterns to strip
        domain_patterns = [
            '.local',
            '.corp',
            '.lan',
            '.domain.com',
            '.company.com',
            '.internal',
            '.priv',
            '.private',
            '.columbia.csc'  # Adding your specific domain
        ]

        # First, try specific known patterns
        name_lower = name.lower()
        for suffix in domain_patterns:
            if name_lower.endswith(suffix.lower()):
                name = name[:-len(suffix)]
                break

        # Then try to catch any remaining FQDN pattern (.domain.tld)
        # This regex matches anything that ends with .word.word (like .domain.com)
        fqdn_pattern = r'\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$'
        name = re.sub(fqdn_pattern, '', name)

        # Also handle single domain suffixes that we might have missed
        # Match anything that ends with .word (but not if it's an IP address)
        if not re.match(r'^\d+\.\d+\.\d+\.\d+$', name):  # Not an IP
            single_domain_pattern = r'\.[a-zA-Z0-9-]+$'
            # Only strip if it looks like a domain (not a numbered interface)
            if re.search(r'\.[a-zA-Z][a-zA-Z0-9-]*$', name):
                name = re.sub(single_domain_pattern, '', name)

        return name

    def build_platform_string(self, vendor, model):
        """Build platform string from vendor and model"""
        if not vendor and not model:
            return ""
        elif vendor and model:
            return f"{vendor} {model}"
        elif vendor:
            return vendor
        else:
            return model or ""

    def get_latest_lldp_data(self, include_patterns=None, exclude_patterns=None, sites=None, roles=None):
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
            cr.collection_time
        FROM lldp_neighbors ln
        JOIN devices d ON ln.device_id = d.id
        LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
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

        conn = self.get_db_connection()
        try:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_device_details(self, include_patterns=None, exclude_patterns=None, sites=None, roles=None):
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

        conn = self.get_db_connection()
        try:
            cursor = conn.execute(query, params)
            results = cursor.fetchall()
            return {self.normalize_hostname(row['device_name']): dict(row) for row in results}
        finally:
            conn.close()

    def device_matches_filters(self, device_name, hostname, include_patterns=None, exclude_patterns=None):
        """Check if a device matches the include/exclude patterns"""
        # Check include patterns
        if include_patterns:
            matches_include = False
            for pattern in include_patterns:
                if (device_name and pattern.lower() in device_name.lower()) or \
                        (hostname and pattern.lower() in hostname.lower()):
                    matches_include = True
                    break
            if not matches_include:
                return False

        # Check exclude patterns
        if exclude_patterns:
            for pattern in exclude_patterns:
                if (device_name and pattern.lower() in device_name.lower()) or \
                        (hostname and pattern.lower() in hostname.lower()):
                    return False

        return True

    def build_map_structure(self, include_patterns=None, exclude_patterns=None, sites=None, roles=None,
                            include_connected=True, debug=False, network_only=False):
        """Build the map.json structure from LLDP data with filtering"""

        if debug:
            # Debug database contents first
            self.debug_database_contents()

            # Debug: Print filter criteria
            print(f"DEBUG: Filters applied:")
            print(f"  Include patterns: {include_patterns}")
            print(f"  Exclude patterns: {exclude_patterns}")
            print(f"  Sites: {sites}")
            print(f"  Roles: {roles}")
            print(f"  Network only: {network_only}")
            print()

        lldp_data = self.get_latest_lldp_data(include_patterns, exclude_patterns, sites, roles)

        if debug:
            print(f"DEBUG: Found {len(lldp_data)} LLDP entries after database filtering")

            # Debug: Show some sample LLDP data
            for i, entry in enumerate(lldp_data[:3]):
                print(
                    f"  Sample {i + 1}: {entry['device_name']} -> {entry['remote_hostname']} via {entry['local_interface']}")
            print()

        device_details = self.get_device_details(include_patterns, exclude_patterns, sites, roles)

        if debug:
            print(f"DEBUG: Found {len(device_details)} devices after database filtering")
            print(f"  Devices: {list(device_details.keys())[:5]}...")
            print()

        # Initialize map structure
        topology_map = {}
        connected_devices = set()
        all_source_devices = set()
        all_peer_devices = set()

        # First pass: collect all source and peer devices
        device_lldp = defaultdict(list)
        for entry in lldp_data:
            device_name = self.normalize_hostname(entry['device_name'] or entry['hostname'])
            remote_hostname = self.normalize_hostname(entry['remote_hostname'])

            device_lldp[device_name].append(entry)
            all_source_devices.add(device_name)
            if remote_hostname:
                all_peer_devices.add(remote_hostname)

            # Track connected devices if include_connected is True
            if include_connected:
                if remote_hostname:
                    connected_devices.add(remote_hostname)

        # If network_only is True, only include devices that appear as both source AND peer
        if network_only:
            network_devices = all_source_devices.intersection(all_peer_devices)
            if debug:
                print(
                    f"DEBUG: Network-only mode - found {len(network_devices)} devices that are both sources and peers")
                print(f"  Network devices: {sorted(list(network_devices))}")
            # Filter device_lldp to only include network devices
            device_lldp = {device: entries for device, entries in device_lldp.items() if device in network_devices}

        if debug:
            print(f"DEBUG: Grouped LLDP data into {len(device_lldp)} source devices")
            print(f"  Source devices: {list(device_lldp.keys())}")
            print()

        # If include_connected is True, also get details for connected devices
        if include_connected and connected_devices:
            if debug:
                print(f"DEBUG: Looking up {len(connected_devices)} connected devices")
                print(f"  Connected devices: {list(connected_devices)[:5]}...")

            # Get additional device details for connected devices not in our main filter
            additional_query = """
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
            WHERE d.is_active = 1 AND (d.device_name IN ({}) OR d.hostname IN ({}))
            """.format(
                ','.join(['?'] * len(connected_devices)),
                ','.join(['?'] * len(connected_devices))
            )

            conn = self.get_db_connection()
            try:
                params = list(connected_devices) + list(connected_devices)
                cursor = conn.execute(additional_query, params)
                additional_devices = {self.normalize_hostname(row['device_name']): dict(row) for row in
                                      cursor.fetchall()}
                if debug:
                    print(f"DEBUG: Found {len(additional_devices)} additional device details")
                # Merge with existing device details
                device_details.update(additional_devices)
            finally:
                conn.close()

        # Build topology map
        for device_name, lldp_entries in device_lldp.items():
            if debug:
                print(f"DEBUG: Processing device {device_name} with {len(lldp_entries)} LLDP entries")

            # Get device details
            device_info = device_details.get(device_name, {})

            # Build platform string from vendor and model
            platform = self.build_platform_string(device_info.get('vendor'), device_info.get('model'))

            # Initialize device entry
            topology_map[device_name] = {
                "node_details": {
                    "ip": device_info.get('ip_address', ''),
                    "platform": platform
                },
                "peers": {}
            }

            # Group connections by remote device
            peer_connections = defaultdict(list)
            peer_details = {}

            for entry in lldp_entries:
                remote_hostname = self.normalize_hostname(entry['remote_hostname'])
                if debug:
                    print(f"  DEBUG: Checking connection to {remote_hostname}")

                # Apply network_only filter to peer devices too
                if network_only and remote_hostname not in all_source_devices:
                    if debug:
                        print(f"    DEBUG: Filtered out {remote_hostname} (not a network device)")
                    continue

                # Apply include/exclude filters if include_connected is False
                if not include_connected:
                    if not self.device_matches_filters(remote_hostname, remote_hostname, include_patterns,
                                                       exclude_patterns):
                        if debug:
                            print(f"    DEBUG: Filtered out {remote_hostname} (doesn't match include/exclude)")
                        continue

                # Store peer details
                if remote_hostname and remote_hostname not in peer_details:
                    # Try to get details from device_details first (if it's in our database)
                    peer_info = device_details.get(remote_hostname, {})
                    if peer_info:
                        peer_platform = self.build_platform_string(peer_info.get('vendor'), peer_info.get('model'))
                        peer_details[remote_hostname] = {
                            'ip': peer_info.get('ip_address', ''),
                            'platform': peer_platform
                        }
                    else:
                        # Fall back to LLDP-provided info (but still try to extract platform)
                        peer_details[remote_hostname] = {
                            'ip': entry['remote_mgmt_ip'] or '',
                            'platform': self.extract_platform_from_description(entry['remote_system_description'])
                        }

                # Add connection
                connection = [
                    entry['local_interface'] or '',
                    entry['remote_port'] or ''
                ]
                peer_connections[remote_hostname].append(connection)
                if debug:
                    print(f"    DEBUG: Added connection {connection}")

            # Build peers section
            for peer_name, connections in peer_connections.items():
                peer_info = peer_details.get(peer_name, {'ip': '', 'platform': ''})

                topology_map[device_name]["peers"][peer_name] = {
                    "ip": peer_info['ip'],
                    "platform": peer_info['platform'],
                    "connections": connections
                }

            if debug:
                print(f"  DEBUG: Device {device_name} has {len(topology_map[device_name]['peers'])} peers")

        if debug:
            print(f"DEBUG: Final topology map has {len(topology_map)} devices")

        return topology_map

    def extract_platform_from_description(self, system_description):
        """Try to extract platform info from system description if not available"""
        if not system_description:
            return ""

        # Common platform indicators in system descriptions
        platform_keywords = {
            'Cisco IOS': 'Cisco IOS',
            'Cisco NX-OS': 'Cisco NX-OS',
            'Arista vEOS': 'Arista vEOS',
            'Catalyst': 'Cisco Catalyst',
            'Nexus': 'Cisco Nexus',
            'C9200': 'Cisco C9200',
            'C9300': 'Cisco C9300',
            'C9500': 'Cisco C9500'
        }

        desc_upper = system_description.upper()
        for keyword, platform in platform_keywords.items():
            if keyword.upper() in desc_upper:
                return platform

        return ""

    def generate_map_json(self, output_file=None, pretty_print=True, include_patterns=None, exclude_patterns=None,
                          sites=None, roles=None, include_connected=True, debug=False, network_only=False):
        """Generate the map.json file with filtering options"""
        topology_map = self.build_map_structure(include_patterns, exclude_patterns, sites, roles, include_connected,
                                                debug, network_only)

        # Convert to JSON
        if pretty_print:
            json_output = json.dumps(topology_map, indent=2, sort_keys=True)
        else:
            json_output = json.dumps(topology_map, separators=(',', ':'))

        # Write to file or return
        if output_file:
            with open(output_file, 'w') as f:
                f.write(json_output)
            print(f"Map JSON written to: {output_file}")
        else:
            return json_output

    def get_statistics(self, include_patterns=None, exclude_patterns=None, sites=None, roles=None, debug=False,
                       network_only=False):
        """Get statistics about the topology with filtering"""
        topology_map = self.build_map_structure(include_patterns, exclude_patterns, sites, roles,
                                                include_connected=False, debug=debug, network_only=network_only)

        total_devices = len(topology_map)
        total_connections = 0
        devices_with_lldp = 0

        for device_name, device_data in topology_map.items():
            peer_count = len(device_data['peers'])
            if peer_count > 0:
                devices_with_lldp += 1

            for peer_name, peer_data in device_data['peers'].items():
                total_connections += len(peer_data['connections'])

        return {
            'total_devices': total_devices,
            'devices_with_lldp': devices_with_lldp,
            'total_connections': total_connections,
            'coverage_percentage': round((devices_with_lldp / total_devices * 100) if total_devices > 0 else 0, 2)
        }


def main():
    """Main function for command line usage"""
    parser = argparse.ArgumentParser(description='Convert NAPALM CMDB LLDP data to map.json format')
    parser.add_argument('--db', default='napalm_cmdb.db', help='Path to CMDB database')
    parser.add_argument('--output', '-o', help='Output file path (default: prints to stdout)')
    parser.add_argument('--stats', action='store_true', help='Show topology statistics')
    parser.add_argument('--compact', action='store_true', help='Generate compact JSON (no pretty printing)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--network-only', action='store_true',
                        help='Only include devices that appear as both sources and peers (network equipment only)')

    # Filtering options
    parser.add_argument('--include', '-i', action='append',
                        help='Include devices matching pattern (can be used multiple times)')
    parser.add_argument('--exclude', '-e', action='append',
                        help='Exclude devices matching pattern (can be used multiple times)')
    parser.add_argument('--site', '-s', action='append',
                        help='Include devices from specific site (can be used multiple times)')
    parser.add_argument('--role', '-r', action='append',
                        help='Include devices with specific role (can be used multiple times)')
    parser.add_argument('--no-connected', action='store_true',
                        help='Do not include connected devices outside filter criteria')

    args = parser.parse_args()

    # Initialize converter
    converter = LLDPMapConverter(args.db)

    try:
        # Prepare filter arguments
        filter_kwargs = {
            'include_patterns': args.include,
            'exclude_patterns': args.exclude,
            'sites': args.site,
            'roles': args.role,
            'debug': args.debug,
            'network_only': args.network_only
        }

        # Show statistics if requested
        if args.stats:
            stats = converter.get_statistics(**filter_kwargs)
            print("Topology Statistics (with filters applied):")
            print(f"  Total devices: {stats['total_devices']}")
            print(f"  Devices with LLDP data: {stats['devices_with_lldp']}")
            print(f"  Total connections: {stats['total_connections']}")
            print(f"  LLDP coverage: {stats['coverage_percentage']}%")
            print()

            if args.include:
                print(f"  Include patterns: {', '.join(args.include)}")
            if args.exclude:
                print(f"  Exclude patterns: {', '.join(args.exclude)}")
            if args.site:
                print(f"  Sites: {', '.join(args.site)}")
            if args.role:
                print(f"  Roles: {', '.join(args.role)}")
            if args.network_only:
                print(f"  Network-only mode: enabled")
            print()

        # Generate map JSON
        filter_kwargs['include_connected'] = not args.no_connected

        if args.output:
            converter.generate_map_json(args.output, pretty_print=not args.compact, **filter_kwargs)
        else:
            json_output = converter.generate_map_json(pretty_print=not args.compact, **filter_kwargs)
            print(json_output)

    except FileNotFoundError:
        print(f"Error: Database file '{args.db}' not found")
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()