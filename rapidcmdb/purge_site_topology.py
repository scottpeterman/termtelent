#!/usr/bin/env python3
"""
Site Topology Purge Script
Removes topology data for a specific site to test topology rebuilding
"""

import sqlite3
import argparse
import logging
import os
from datetime import datetime
from typing import List, Dict, Optional


class SiteTopologyPurger:
    """Purges topology data for a specific site"""

    def __init__(self, db_path: str = "napalm_cmdb.db"):
        self.db_path = db_path
        self.setup_logging()

    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('topology_purge.log'),
                logging.StreamHandler()
            ]
        )

    def get_db_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory"""
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database file not found: {self.db_path}")

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_site_devices(self, site_code: str) -> List[Dict]:
        """Get all devices for a specific site"""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        query = """
            SELECT id, device_name, site_code, device_role, vendor, is_active
            FROM devices 
            WHERE UPPER(site_code) = UPPER(?)
            ORDER BY device_name
        """

        cursor.execute(query, (site_code,))
        devices = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return devices

    def analyze_site_topology(self, site_code: str) -> Dict:
        """Analyze current topology state for a site"""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        site_devices = self.get_site_devices(site_code)
        device_ids = [str(d['id']) for d in site_devices]

        if not device_ids:
            return {
                'devices': [],
                'topology_as_source': 0,
                'topology_as_destination': 0,
                'lldp_neighbors': 0,
                'inter_site_connections': 0
            }

        device_ids_str = ','.join(device_ids)

        # Count topology connections where site devices are source
        cursor.execute(f"""
            SELECT COUNT(*) as count
            FROM network_topology nt
            WHERE nt.source_device_id IN ({device_ids_str})
        """)
        topology_as_source = cursor.fetchone()['count']

        # Count topology connections where site devices are destination
        cursor.execute(f"""
            SELECT COUNT(*) as count
            FROM network_topology nt
            WHERE nt.destination_device_id IN ({device_ids_str})
        """)
        topology_as_destination = cursor.fetchone()['count']

        # Count LLDP neighbors for site devices
        cursor.execute(f"""
            SELECT COUNT(*) as count
            FROM lldp_neighbors ln
            WHERE ln.device_id IN ({device_ids_str})
        """)
        lldp_neighbors = cursor.fetchone()['count']

        # Count inter-site connections (from this site to other sites)
        cursor.execute(f"""
            SELECT COUNT(*) as count
            FROM network_topology nt
            JOIN devices d1 ON nt.source_device_id = d1.id
            JOIN devices d2 ON nt.destination_device_id = d2.id
            WHERE d1.id IN ({device_ids_str})
            AND UPPER(d1.site_code) != UPPER(d2.site_code)
        """)
        inter_site_connections = cursor.fetchone()['count']

        conn.close()

        return {
            'devices': site_devices,
            'topology_as_source': topology_as_source,
            'topology_as_destination': topology_as_destination,
            'lldp_neighbors': lldp_neighbors,
            'inter_site_connections': inter_site_connections
        }

    def get_detailed_topology(self, site_code: str) -> List[Dict]:
        """Get detailed topology connections for a site"""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        query = """
            SELECT 
                nt.id as topology_id,
                d1.device_name as source_device,
                d1.site_code as source_site,
                nt.source_interface,
                d2.device_name as dest_device,
                d2.site_code as dest_site,
                nt.destination_interface,
                nt.connection_type,
                nt.discovery_method,
                nt.confidence_score,
                nt.created_at
            FROM network_topology nt
            JOIN devices d1 ON nt.source_device_id = d1.id
            JOIN devices d2 ON nt.destination_device_id = d2.id
            WHERE UPPER(d1.site_code) = UPPER(?) OR UPPER(d2.site_code) = UPPER(?)
            ORDER BY d1.device_name, nt.source_interface
        """

        cursor.execute(query, (site_code, site_code))
        topology = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return topology

    def purge_site_topology(self, site_code: str, dry_run: bool = True) -> Dict:
        """Purge topology data for a site"""
        logging.info(f"{'DRY RUN: ' if dry_run else ''}Purging topology data for site: {site_code}")

        # Analyze before purging
        before_analysis = self.analyze_site_topology(site_code)

        if not before_analysis['devices']:
            logging.warning(f"No devices found for site code: {site_code}")
            return {'success': False, 'reason': 'No devices found'}

        logging.info(f"Found {len(before_analysis['devices'])} devices in site {site_code}")
        logging.info(f"Topology connections as source: {before_analysis['topology_as_source']}")
        logging.info(f"Topology connections as destination: {before_analysis['topology_as_destination']}")
        logging.info(f"LLDP neighbors: {before_analysis['lldp_neighbors']}")
        logging.info(f"Inter-site connections: {before_analysis['inter_site_connections']}")

        if dry_run:
            logging.info("DRY RUN: No data will be deleted. Use --execute to actually purge data.")
            return {
                'success': True,
                'dry_run': True,
                'before_analysis': before_analysis,
                'would_delete': {
                    'topology_as_source': before_analysis['topology_as_source'],
                    'topology_as_destination': before_analysis['topology_as_destination']
                }
            }

        # Actual purging
        conn = self.get_db_connection()
        cursor = conn.cursor()

        device_ids = [d['id'] for d in before_analysis['devices']]
        device_ids_str = ','.join(str(id) for id in device_ids)

        try:
            # Delete topology connections where site devices are source
            cursor.execute(f"""
                DELETE FROM network_topology 
                WHERE source_device_id IN ({device_ids_str})
            """)
            deleted_as_source = cursor.rowcount

            # Delete topology connections where site devices are destination
            cursor.execute(f"""
                DELETE FROM network_topology 
                WHERE destination_device_id IN ({device_ids_str})
            """)
            deleted_as_destination = cursor.rowcount

            conn.commit()

            logging.info(f"Deleted {deleted_as_source} topology connections (as source)")
            logging.info(f"Deleted {deleted_as_destination} topology connections (as destination)")

            # Analyze after purging
            after_analysis = self.analyze_site_topology(site_code)

            conn.close()

            return {
                'success': True,
                'dry_run': False,
                'before_analysis': before_analysis,
                'after_analysis': after_analysis,
                'deleted': {
                    'topology_as_source': deleted_as_source,
                    'topology_as_destination': deleted_as_destination
                }
            }

        except Exception as e:
            conn.rollback()
            conn.close()
            logging.error(f"Error purging topology data: {e}")
            return {'success': False, 'error': str(e)}

    def backup_site_topology(self, site_code: str, backup_file: Optional[str] = None) -> str:
        """Backup site topology data before purging"""
        if not backup_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"topology_backup_{site_code.lower()}_{timestamp}.sql"

        logging.info(f"Creating topology backup: {backup_file}")

        detailed_topology = self.get_detailed_topology(site_code)

        with open(backup_file, 'w') as f:
            f.write(f"-- Topology backup for site {site_code}\n")
            f.write(f"-- Created: {datetime.now().isoformat()}\n")
            f.write(f"-- Total connections: {len(detailed_topology)}\n\n")

            for conn_data in detailed_topology:
                f.write(f"-- {conn_data['source_device']} -> {conn_data['dest_device']}\n")

        logging.info(f"Backup saved to: {backup_file}")
        return backup_file

    def restore_from_backup(self, backup_file: str) -> bool:
        """Restore topology from backup file (placeholder)"""
        logging.info(f"Restore functionality not implemented. Backup file: {backup_file}")
        logging.info("Manual restoration would require re-running the collector or manual SQL.")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Purge network topology data for a specific site',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Dry run (default) - see what would be deleted
  python purge_site_topology.py CAL

  # Actually purge the data
  python purge_site_topology.py CAL --execute

  # Purge with custom database path
  python purge_site_topology.py CAL --execute --db-path /path/to/napalm_cmdb.db

  # Create backup before purging
  python purge_site_topology.py CAL --execute --backup

  # Show detailed topology before purging
  python purge_site_topology.py CAL --show-details
        ''')

    parser.add_argument('site_code', help='Site code to purge (e.g., CAL, FRC, USC)')
    parser.add_argument('--db-path', default='napalm_cmdb.db', help='Path to SQLite database')
    parser.add_argument('--execute', action='store_true', help='Actually purge data (default is dry run)')
    parser.add_argument('--backup', action='store_true', help='Create backup before purging')
    parser.add_argument('--show-details', action='store_true', help='Show detailed topology connections')
    parser.add_argument('--backup-file', help='Custom backup file name')

    args = parser.parse_args()

    try:
        purger = SiteTopologyPurger(args.db_path)

        # Show detailed topology if requested
        if args.show_details:
            print(f"\n=== Detailed Topology for Site {args.site_code} ===")
            detailed = purger.get_detailed_topology(args.site_code)

            if not detailed:
                print("No topology connections found.")
            else:
                for conn in detailed:
                    print(f"{conn['source_device']}[{conn['source_interface']}] -> "
                          f"{conn['dest_device']}[{conn['destination_interface']}] "
                          f"({conn['connection_type']}, confidence: {conn['confidence_score']})")
            print()

        # Create backup if requested
        if args.backup:
            backup_file = purger.backup_site_topology(args.site_code, args.backup_file)
            print(f"Backup created: {backup_file}")

        # Purge topology data
        result = purger.purge_site_topology(args.site_code, dry_run=not args.execute)

        if result['success']:
            print(f"\n=== Purge Results for Site {args.site_code} ===")

            if result.get('dry_run'):
                print("DRY RUN - No data was actually deleted")
                print(f"Would delete {result['would_delete']['topology_as_source']} connections (as source)")
                print(f"Would delete {result['would_delete']['topology_as_destination']} connections (as destination)")
            else:
                print("ACTUAL PURGE COMPLETED")
                print(f"Deleted {result['deleted']['topology_as_source']} connections (as source)")
                print(f"Deleted {result['deleted']['topology_as_destination']} connections (as destination)")

                after = result['after_analysis']
                print(f"\nAfter purge:")
                print(f"  Remaining topology connections (as source): {after['topology_as_source']}")
                print(f"  Remaining topology connections (as destination): {after['topology_as_destination']}")
                print(f"  LLDP neighbors (preserved): {after['lldp_neighbors']}")

            print(f"\nNext steps:")
            print(f"1. Run: python npcollector_db.py --site {args.site_code}")
            print(f"2. Check if topology gets rebuilt automatically")
            print(f"3. Test site mapping functionality")

        else:
            print(f"Purge failed: {result.get('error', result.get('reason', 'Unknown error'))}")
            return 1

    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        logging.exception("Unexpected error during topology purge")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())