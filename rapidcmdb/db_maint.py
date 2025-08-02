#!/usr/bin/env python3
"""
RapidCMDB Database Maintenance Utility
Handles deduplication, normalization, and database optimization
"""

import sqlite3
import hashlib
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import argparse


class DatabaseMaintenance:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.setup_logging()

    def setup_logging(self):
        """Setup logging for maintenance operations"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('db_maintenance.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def backup_database(self) -> str:
        """Create a backup before maintenance operations"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{self.db_path}.backup_{timestamp}"

        try:
            # Create backup using SQLite backup API
            backup_conn = sqlite3.connect(backup_path)
            self.conn.backup(backup_conn)
            backup_conn.close()
            self.logger.info(f"Database backed up to: {backup_path}")
            return backup_path
        except Exception as e:
            self.logger.error(f"Backup failed: {e}")
            raise

    def normalize_vendor_names(self, dry_run: bool = True) -> Dict[str, int]:
        """Normalize vendor names to fix case inconsistencies"""
        vendor_mapping = {
            'cisco': ['Cisco', 'CISCO', 'cisco'],
            'juniper': ['Juniper', 'JUNIPER', 'juniper', 'Juniper Networks'],
            'arista': ['Arista', 'ARISTA', 'arista', 'Arista Networks'],
            'hp': ['HP', 'hp', 'Hewlett Packard', 'HPE'],
            'palo_alto': ['Palo Alto', 'palo_alto', 'PALO_ALTO', 'Palo Alto Networks'],
            'fortinet': ['Fortinet', 'FORTINET', 'fortinet'],
            'zebra': ['Zebra', 'ZEBRA', 'zebra'],
            'lexmark': ['Lexmark', 'LEXMARK', 'lexmark'],
            'apc': ['APC', 'apc', 'American Power Conversion'],
            'bluecat': ['BlueCat', 'bluecat', 'BLUECAT'],
            'aruba': ['Aruba','aruba_ap', 'aruba_wireless',"Aruba Networks"]
        }

        changes = {}
        cursor = self.conn.cursor()

        for normalized_name, variants in vendor_mapping.items():
            for variant in variants:
                if variant != normalized_name:
                    # Count devices that would be affected
                    cursor.execute("SELECT COUNT(*) FROM devices WHERE vendor = ?", (variant,))
                    count = cursor.fetchone()[0]

                    if count > 0:
                        changes[f"{variant} -> {normalized_name}"] = count

                        if not dry_run:
                            cursor.execute(
                                "UPDATE devices SET vendor = ? WHERE vendor = ?",
                                (normalized_name, variant)
                            )
                            self.logger.info(f"Updated {count} devices: {variant} -> {normalized_name}")

        if not dry_run:
            self.conn.commit()

        return changes

    def find_duplicate_devices(self) -> List[Dict]:
        """Find potential duplicate devices based on multiple criteria"""
        cursor = self.conn.cursor()

        duplicates = []

        # Find devices with same serial number but different names
        cursor.execute("""
            SELECT serial_number, COUNT(*) as count, 
                   GROUP_CONCAT(device_name) as device_names,
                   GROUP_CONCAT(id) as device_ids
            FROM devices 
            WHERE serial_number IS NOT NULL AND serial_number != ''
            GROUP BY serial_number 
            HAVING COUNT(*) > 1
        """)

        for row in cursor.fetchall():
            duplicates.append({
                'type': 'serial_duplicate',
                'criteria': row['serial_number'],
                'count': row['count'],
                'device_names': row['device_names'].split(','),
                'device_ids': [int(x) for x in row['device_ids'].split(',')]
            })

        # Find devices with same IP but different names
        cursor.execute("""
            SELECT di.ip_address, COUNT(*) as count,
                   GROUP_CONCAT(d.device_name) as device_names,
                   GROUP_CONCAT(d.id) as device_ids
            FROM device_ips di
            JOIN devices d ON di.device_id = d.id
            GROUP BY di.ip_address
            HAVING COUNT(*) > 1
        """)

        for row in cursor.fetchall():
            duplicates.append({
                'type': 'ip_duplicate',
                'criteria': row['ip_address'],
                'count': row['count'],
                'device_names': row['device_names'].split(','),
                'device_ids': [int(x) for x in row['device_ids'].split(',')]
            })

        # Find devices with similar hostnames (domain vs non-domain)
        cursor.execute("""
            SELECT d1.id as id1, d1.device_name as name1, d1.hostname as hostname1,
                   d2.id as id2, d2.device_name as name2, d2.hostname as hostname2
            FROM devices d1
            JOIN devices d2 ON d1.id < d2.id
            WHERE (
                -- One has domain, other doesn't
                (d1.hostname LIKE '%.%' AND d2.hostname = SUBSTR(d1.hostname, 1, INSTR(d1.hostname, '.') - 1))
                OR
                (d2.hostname LIKE '%.%' AND d1.hostname = SUBSTR(d2.hostname, 1, INSTR(d2.hostname, '.') - 1))
                OR
                -- Device names are similar
                (UPPER(d1.device_name) = UPPER(d2.device_name))
            )
        """)

        for row in cursor.fetchall():
            duplicates.append({
                'type': 'hostname_similar',
                'criteria': f"{row['name1']} vs {row['name2']}",
                'count': 2,
                'device_names': [row['name1'], row['name2']],
                'device_ids': [row['id1'], row['id2']],
                'hostnames': [row['hostname1'], row['hostname2']]
            })

        return duplicates

    def merge_duplicate_devices(self, primary_id: int, duplicate_ids: List[int], dry_run: bool = True) -> bool:
        """Merge duplicate devices into a primary device"""
        cursor = self.conn.cursor()

        try:
            if not dry_run:
                self.conn.execute("BEGIN TRANSACTION")

            # Get primary device info
            cursor.execute("SELECT * FROM devices WHERE id = ?", (primary_id,))
            primary_device = cursor.fetchone()

            if not primary_device:
                raise ValueError(f"Primary device {primary_id} not found")

            for dup_id in duplicate_ids:
                self.logger.info(f"Merging device {dup_id} into {primary_id}")

                # Update all foreign key references to point to primary device
                tables_to_update = [
                    'device_ips', 'collection_runs', 'interfaces', 'lldp_neighbors',
                    'arp_entries', 'mac_address_table', 'environment_data',
                    'device_configs', 'device_users', 'hardware_inventory',
                    'vlans', 'routes', 'bgp_peers'
                ]

                for table in tables_to_update:
                    if not dry_run:
                        cursor.execute(f"UPDATE {table} SET device_id = ? WHERE device_id = ?",
                                       (primary_id, dup_id))

                # Update topology references
                if not dry_run:
                    cursor.execute("UPDATE network_topology SET source_device_id = ? WHERE source_device_id = ?",
                                   (primary_id, dup_id))
                    cursor.execute(
                        "UPDATE network_topology SET destination_device_id = ? WHERE destination_device_id = ?",
                        (primary_id, dup_id))

                # Delete the duplicate device
                if not dry_run:
                    cursor.execute("DELETE FROM devices WHERE id = ?", (dup_id,))

            if not dry_run:
                self.conn.commit()
                self.logger.info(f"Successfully merged {len(duplicate_ids)} devices into device {primary_id}")
            else:
                self.logger.info(f"DRY RUN: Would merge {len(duplicate_ids)} devices into device {primary_id}")

            return True

        except Exception as e:
            if not dry_run:
                self.conn.rollback()
            self.logger.error(f"Error merging devices: {e}")
            return False

    def clean_old_data(self, dry_run: bool = True) -> Dict[str, int]:
        """Clean old data based on retention policies"""
        cursor = self.conn.cursor()

        # Get retention policies
        cursor.execute("SELECT * FROM retention_policies WHERE enabled = 1")
        policies = cursor.fetchall()

        cleanup_stats = {}

        for policy in policies:
            table_name = policy['table_name']
            retention_days = policy['retention_days']
            keep_latest_count = policy['keep_latest_count']

            cutoff_date = datetime.now() - timedelta(days=retention_days)

            # Build cleanup query based on table structure
            if table_name == 'collection_runs':
                date_column = 'collection_time'
                partition_column = 'device_id'
            elif table_name in ['interfaces', 'arp_entries', 'mac_address_table', 'environment_data']:
                date_column = 'created_at'
                partition_column = 'device_id'
            elif table_name == 'device_configs':
                date_column = 'created_at'
                partition_column = 'device_id'
            else:
                continue  # Skip unknown tables

            # Count records that would be deleted
            if keep_latest_count:
                # Keep latest N records per device, regardless of age
                query = f"""
                    SELECT COUNT(*) FROM {table_name} t1
                    WHERE t1.id NOT IN (
                        SELECT t2.id FROM {table_name} t2
                        WHERE t2.{partition_column} = t1.{partition_column}
                        ORDER BY t2.{date_column} DESC
                        LIMIT {keep_latest_count}
                    )
                    AND t1.{date_column} < ?
                """
            else:
                query = f"SELECT COUNT(*) FROM {table_name} WHERE {date_column} < ?"

            cursor.execute(query, (cutoff_date.isoformat(),))
            count = cursor.fetchone()[0]
            cleanup_stats[table_name] = count

            if count > 0 and not dry_run:
                # Execute deletion
                if keep_latest_count:
                    delete_query = f"""
                        DELETE FROM {table_name} 
                        WHERE id NOT IN (
                            SELECT id FROM {table_name} t
                            WHERE t.{partition_column} = {table_name}.{partition_column}
                            ORDER BY t.{date_column} DESC
                            LIMIT {keep_latest_count}
                        )
                        AND {date_column} < ?
                    """
                else:
                    delete_query = f"DELETE FROM {table_name} WHERE {date_column} < ?"

                cursor.execute(delete_query, (cutoff_date.isoformat(),))
                self.logger.info(f"Cleaned {count} old records from {table_name}")

        if not dry_run:
            self.conn.commit()

        return cleanup_stats

    def optimize_database(self) -> Dict[str, any]:
        """Optimize database with VACUUM, REINDEX, and ANALYZE"""
        cursor = self.conn.cursor()

        stats = {}

        # Get database size before optimization
        cursor.execute("PRAGMA page_count")
        page_count_before = cursor.fetchone()[0]
        cursor.execute("PRAGMA page_size")
        page_size = cursor.fetchone()[0]
        size_before = page_count_before * page_size

        self.logger.info("Starting database optimization...")

        # Update statistics
        cursor.execute("ANALYZE")
        stats['analyze'] = 'completed'

        # Rebuild indexes
        cursor.execute("REINDEX")
        stats['reindex'] = 'completed'

        # Vacuum database
        cursor.execute("VACUUM")
        stats['vacuum'] = 'completed'

        # Get size after optimization
        cursor.execute("PRAGMA page_count")
        page_count_after = cursor.fetchone()[0]
        size_after = page_count_after * page_size

        stats['size_before_mb'] = round(size_before / 1024 / 1024, 2)
        stats['size_after_mb'] = round(size_after / 1024 / 1024, 2)
        stats['space_saved_mb'] = round((size_before - size_after) / 1024 / 1024, 2)
        stats['space_saved_percent'] = round(((size_before - size_after) / size_before) * 100,
                                             2) if size_before > 0 else 0

        self.logger.info(f"Database optimized. Size: {stats['size_before_mb']}MB -> {stats['size_after_mb']}MB "
                         f"(saved {stats['space_saved_mb']}MB, {stats['space_saved_percent']}%)")

        return stats

    def generate_maintenance_report(self) -> Dict[str, any]:
        """Generate a comprehensive maintenance report"""
        cursor = self.conn.cursor()

        report = {
            'timestamp': datetime.now().isoformat(),
            'database_path': self.db_path,
            'database_size_mb': 0,
            'total_devices': 0,
            'vendor_distribution': {},
            'duplicate_analysis': {},
            'collection_stats': {},
            'data_freshness': {}
        }

        # Database size
        cursor.execute("PRAGMA page_count")
        page_count = cursor.fetchone()[0]
        cursor.execute("PRAGMA page_size")
        page_size = cursor.fetchone()[0]
        report['database_size_mb'] = round((page_count * page_size) / 1024 / 1024, 2)

        # Total devices
        cursor.execute("SELECT COUNT(*) FROM devices WHERE is_active = 1")
        report['total_devices'] = cursor.fetchone()[0]

        # Vendor distribution
        cursor.execute(
            "SELECT vendor, COUNT(*) FROM devices WHERE is_active = 1 GROUP BY vendor ORDER BY COUNT(*) DESC")
        report['vendor_distribution'] = dict(cursor.fetchall())

        # Duplicate analysis
        duplicates = self.find_duplicate_devices()
        report['duplicate_analysis'] = {
            'total_duplicate_groups': len(duplicates),
            'by_type': {}
        }

        for dup in duplicates:
            dup_type = dup['type']
            if dup_type not in report['duplicate_analysis']['by_type']:
                report['duplicate_analysis']['by_type'][dup_type] = 0
            report['duplicate_analysis']['by_type'][dup_type] += 1

        # Collection statistics
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT device_id) as devices_with_collections,
                COUNT(*) as total_collections,
                AVG(collection_duration) as avg_duration,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_collections
            FROM collection_runs
            WHERE collection_time > datetime('now', '-30 days')
        """)

        row = cursor.fetchone()
        report['collection_stats'] = {
            'devices_collected_30d': row[0] or 0,
            'total_collections_30d': row[1] or 0,
            'avg_duration_seconds': round(row[2] or 0, 2),
            'success_rate_percent': round((row[3] / row[1]) * 100, 2) if row[1] > 0 else 0
        }

        # Data freshness
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN last_updated > datetime('now', '-1 day') THEN 1 ELSE 0 END) as fresh_1d,
                SUM(CASE WHEN last_updated > datetime('now', '-7 days') THEN 1 ELSE 0 END) as fresh_7d,
                SUM(CASE WHEN last_updated > datetime('now', '-30 days') THEN 1 ELSE 0 END) as fresh_30d
            FROM devices WHERE is_active = 1
        """)

        row = cursor.fetchone()
        total = report['total_devices']
        if total > 0:
            report['data_freshness'] = {
                'updated_1d_percent': round((row[0] / total) * 100, 2),
                'updated_7d_percent': round((row[1] / total) * 100, 2),
                'updated_30d_percent': round((row[2] / total) * 100, 2)
            }

        return report

    def close(self):
        """Close database connection"""
        self.conn.close()


def main():
    parser = argparse.ArgumentParser(description='RapidCMDB Database Maintenance Utility')
    parser.add_argument('db_path', help='Path to SQLite database file')
    parser.add_argument('--backup', action='store_true', help='Create backup before operations')
    parser.add_argument('--normalize-vendors', action='store_true', help='Normalize vendor names')
    parser.add_argument('--find-duplicates', action='store_true', help='Find duplicate devices')
    parser.add_argument('--merge-devices', nargs='+', type=int, metavar='ID',
                        help='Merge devices (first ID is primary, rest are duplicates)')
    parser.add_argument('--clean-old-data', action='store_true', help='Clean old data per retention policies')
    parser.add_argument('--optimize', action='store_true', help='Optimize database (VACUUM, REINDEX, ANALYZE)')
    parser.add_argument('--report', action='store_true', help='Generate maintenance report')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--all', action='store_true', help='Run all maintenance operations')

    args = parser.parse_args()

    if not Path(args.db_path).exists():
        print(f"Database file not found: {args.db_path}")
        return 1

    db_maint = DatabaseMaintenance(args.db_path)

    try:
        # Create backup if requested
        if args.backup or args.all:
            db_maint.backup_database()

        # Generate report
        if args.report or args.all:
            print("\n=== MAINTENANCE REPORT ===")
            report = db_maint.generate_maintenance_report()

            print(f"Database: {report['database_path']}")
            print(f"Size: {report['database_size_mb']} MB")
            print(f"Total Active Devices: {report['total_devices']}")

            print("\nVendor Distribution:")
            for vendor, count in report['vendor_distribution'].items():
                print(f"  {vendor}: {count}")

            print(f"\nDuplicate Groups Found: {report['duplicate_analysis']['total_duplicate_groups']}")
            for dup_type, count in report['duplicate_analysis']['by_type'].items():
                print(f"  {dup_type}: {count}")

            print(f"\nCollection Stats (30 days):")
            print(f"  Devices Collected: {report['collection_stats']['devices_collected_30d']}")
            print(f"  Success Rate: {report['collection_stats']['success_rate_percent']}%")

            print(f"\nData Freshness:")
            print(f"  Updated in 1 day: {report['data_freshness']['updated_1d_percent']}%")
            print(f"  Updated in 7 days: {report['data_freshness']['updated_7d_percent']}%")

        # Find duplicates
        if args.find_duplicates or args.all:
            print("\n=== DUPLICATE ANALYSIS ===")
            duplicates = db_maint.find_duplicate_devices()

            if duplicates:
                for i, dup in enumerate(duplicates, 1):
                    print(f"\n{i}. {dup['type'].upper()}: {dup['criteria']}")
                    print(f"   Devices: {', '.join(dup['device_names'])}")
                    print(f"   IDs: {dup['device_ids']}")
                    if 'hostnames' in dup:
                        print(f"   Hostnames: {dup['hostnames']}")
            else:
                print("No duplicates found!")

        # Normalize vendors
        if args.normalize_vendors or args.all:
            print("\n=== VENDOR NORMALIZATION ===")
            changes = db_maint.normalize_vendor_names(dry_run=args.dry_run)

            if changes:
                for change, count in changes.items():
                    action = "Would update" if args.dry_run else "Updated"
                    print(f"{action} {count} devices: {change}")
            else:
                print("No vendor normalization needed!")

        # Merge devices
        if args.merge_devices:
            primary_id = args.merge_devices[0]
            duplicate_ids = args.merge_devices[1:]

            print(f"\n=== MERGING DEVICES ===")
            success = db_maint.merge_duplicate_devices(primary_id, duplicate_ids, dry_run=args.dry_run)
            if success:
                print("Device merge completed successfully!")
            else:
                print("Device merge failed!")

        # Clean old data
        if args.clean_old_data or args.all:
            print("\n=== CLEANING OLD DATA ===")
            cleanup_stats = db_maint.clean_old_data(dry_run=args.dry_run)

            if any(cleanup_stats.values()):
                for table, count in cleanup_stats.items():
                    if count > 0:
                        action = "Would clean" if args.dry_run else "Cleaned"
                        print(f"{action} {count} old records from {table}")
            else:
                print("No old data to clean!")

        # Optimize database
        if args.optimize or args.all:
            if not args.dry_run:
                print("\n=== OPTIMIZING DATABASE ===")
                stats = db_maint.optimize_database()
                print(f"Size before: {stats['size_before_mb']} MB")
                print(f"Size after: {stats['size_after_mb']} MB")
                print(f"Space saved: {stats['space_saved_mb']} MB ({stats['space_saved_percent']}%)")
            else:
                print("\n=== OPTIMIZATION (SKIPPED IN DRY RUN) ===")
                print("Database optimization requires actual execution (not compatible with dry-run)")

    finally:
        db_maint.close()

    return 0


if __name__ == "__main__":
    exit(main())