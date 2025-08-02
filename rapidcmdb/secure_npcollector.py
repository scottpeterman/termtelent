# rapidcmdb/secure_npcollector.py
"""
Secure wrapper for existing NAPALM collectors
Maintains CLI compatibility while using secure credential storage
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import Dict, Optional

# Import your existing collectors
from .npcollector1 import DeviceCollector
from .npcollector_db import DatabaseDeviceCollector
from rapidcmdb.secure_collector_config import SecureCollectorConfig, LegacyConfigWrapper

logger = logging.getLogger(__name__)


class SecureDeviceCollector(DeviceCollector):
    """Secure version of DeviceCollector using encrypted credentials"""

    def __init__(self, secure_config: SecureCollectorConfig, max_workers: int = 10):
        self.secure_config = secure_config
        self.max_workers = max_workers

        # Get decrypted config for parent class
        config_dict = secure_config.get_legacy_config_dict()

        # Initialize parent with temporary config
        self.config = config_dict
        self.capture_dir = Path(config_dict.get('capture_directory', 'captures'))
        self.setup_logging()

        # Initialize statistics tracking
        from .npcollector1 import CollectionStats
        self.stats = CollectionStats()

        # Create capture directory
        self.capture_dir.mkdir(exist_ok=True)

        # NAPALM driver mapping
        self.driver_mapping = {
            'cisco': 'ios',
            'arista': 'eos',
            'paloalto': 'panos',
            'hp': 'procurve',
            'aruba': 'arubaoss',
            'fortinet': 'fortios',
            'juniper': 'junos'
        }


class SecureDatabaseDeviceCollector(DatabaseDeviceCollector):
    """Secure version of DatabaseDeviceCollector using encrypted credentials"""

    def __init__(self, secure_config: SecureCollectorConfig, max_workers: int = 10,
                 db_path: str = "napalm_cmdb.db"):
        self.secure_config = secure_config
        self.max_workers = max_workers
        self.db_path = db_path

        # Get decrypted config for parent class
        config_dict = secure_config.get_legacy_config_dict()

        # Initialize with secure config
        self.config = config_dict
        self.capture_dir = Path(config_dict.get('capture_directory', 'captures'))
        self.setup_logging()

        # Initialize statistics tracking
        from .npcollector_db import CollectionStats
        self.stats = CollectionStats()

        # Create capture directory
        self.capture_dir.mkdir(exist_ok=True)

        # NAPALM driver mapping for vendors in database
        self.driver_mapping = {
            'cisco': 'ios',
            'arista': 'eos',
            'palo_alto': 'panos',
            'palo_alto_sdwan': 'panos',
            'hp': 'procurve',
            'hp_network': 'procurve',
            'aruba': 'arubaoss',
            'fortinet': 'fortios',
            'juniper': 'junos',
            'generic_sdwan': None,
            'vmware': None,
            'apc': None,
            'brother': None,
            'dell': None,
            'hp_printer': None,
            'ion': None,
            'lexmark': None,
            'linux_embedded': None,
            'samsung': None,
            'unknown': None,
            'xerox': None,
            'zebra': None,
            'bluecat': None
        }


def ensure_secure_config(app_name: str = "rapidcmdb_collector") -> Optional[SecureCollectorConfig]:
    """Ensure secure configuration is available and unlocked"""
    secure_config = SecureCollectorConfig(app_name)
    wrapper = LegacyConfigWrapper(secure_config)

    if wrapper.unlock_prompt():
        return secure_config
    else:
        print("Failed to unlock secure configuration. Exiting.")
        sys.exit(1)


def secure_collector_main():
    """Main entry point for secure JSON-based collector"""
    parser = argparse.ArgumentParser(description='Secure NAPALM Device Collector (JSON input)')
    parser.add_argument('scan_file', help='JSON scan file from SNMP scanner')
    parser.add_argument('--workers', type=int, default=10, help='Maximum concurrent workers')
    parser.add_argument('--app-name', default='rapidcmdb_collector',
                        help='Application name for credential store')

    args = parser.parse_args()

    if not Path(args.scan_file).exists():
        print(f"Error: Scan file {args.scan_file} not found")
        sys.exit(1)

    try:
        # Initialize secure configuration
        secure_config = ensure_secure_config(args.app_name)

        # Create secure collector
        collector = SecureDeviceCollector(secure_config, args.workers)

        # Run collection with existing method
        summary = collector.run_collection(args.scan_file)

        print("Collection completed successfully!")
        print(f"Total devices: {summary['collection_results']['total_devices']}")
        print(f"Successful: {summary['collection_results']['successful_collections']}")
        print(f"Failed: {summary['collection_results']['failed_collections']}")

    except Exception as e:
        logger.error(f"Collection failed: {e}")
        print(f"Error: {e}")
        sys.exit(1)


def secure_db_collector_main():
    """Main entry point for secure database-driven collector"""
    parser = argparse.ArgumentParser(
        description='Secure Database-Driven NAPALM Device Collector',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Filter Examples:
  # Single filter (legacy style)
  python secure_db_collector.py --filter cisco

  # Multiple filters by type
  python secure_db_collector.py --site FRC USC --vendor cisco arista
  python secure_db_collector.py --site NYC --vendor cisco --role core access
  python secure_db_collector.py --name switch01 router --site FRC
  python secure_db_collector.py --vendor cisco --model catalyst nexus
  python secure_db_collector.py --ip 192.168.1 10.1.1

  # Complex multi-filter example
  python secure_db_collector.py --site FRC USC --vendor cisco --role core --model catalyst

Filter Types:
  --name      : Filter by device name (supports multiple values)
  --site      : Filter by site code (supports multiple values) 
  --vendor    : Filter by vendor (supports multiple values)
  --role      : Filter by device role (supports multiple values)
  --model     : Filter by model (supports multiple values)
  --ip        : Filter by IP address substring (supports multiple values)
  --filter    : Legacy single filter (searches all fields)
        ''')

    parser.add_argument('--database', default='napalm_cmdb.db', help='Database path')
    parser.add_argument('--workers', type=int, default=10, help='Maximum concurrent workers')
    parser.add_argument('--app-name', default='rapidcmdb_collector',
                        help='Application name for credential store')

    # Filter options
    parser.add_argument('--name', nargs='+', help='Filter by device name (supports multiple values)')
    parser.add_argument('--site', nargs='+', help='Filter by site code (supports multiple values)')
    parser.add_argument('--vendor', nargs='+', help='Filter by vendor (supports multiple values)')
    parser.add_argument('--role', nargs='+', help='Filter by device role (supports multiple values)')
    parser.add_argument('--model', nargs='+', help='Filter by model (supports multiple values)')
    parser.add_argument('--ip', nargs='+', help='Filter by IP address substring (supports multiple values)')
    parser.add_argument('--filter', nargs='+', help='Legacy filter - searches all fields (case-insensitive)')

    parser.add_argument('--list-devices', action='store_true', help='List available devices in database')

    args = parser.parse_args()

    if not Path(args.database).exists():
        print(f"Error: Database file {args.database} not found")
        sys.exit(1)

    try:
        # Initialize secure configuration
        secure_config = ensure_secure_config(args.app_name)

        # Create secure database collector
        collector = SecureDatabaseDeviceCollector(secure_config, args.workers, args.database)

        if args.list_devices:
            devices = collector.load_devices_from_database()

            # Apply filters to device list if provided
            filter_args = {
                'name': args.name,
                'site': args.site,
                'vendor': args.vendor,
                'role': args.role,
                'model': args.model,
                'ip': args.ip,
                'legacy': args.filter
            }

            # Remove None values
            filter_args = {k: v for k, v in filter_args.items() if v is not None}

            if filter_args:
                devices = collector.apply_runtime_filters(devices, filter_args)

            print(f"\nFound {len(devices)} devices in database:")
            print("-" * 100)
            print(f"{'Device Name':<25} {'IP Address':<15} {'Vendor':<12} {'Site':<8} {'Role':<12} {'Model':<20}")
            print("-" * 100)
            for device in devices:
                print(f"{device['device_name']:<25} {device['primary_ip']:<15} {device.get('vendor', ''):<12} "
                      f"{device.get('site_code', ''):<8} {device.get('device_role', ''):<12} {device.get('model', ''):<20}")
            return

        # Prepare filter arguments for collection
        filter_args = {
            'name': args.name,
            'site': args.site,
            'vendor': args.vendor,
            'role': args.role,
            'model': args.model,
            'ip': args.ip,
            'legacy': args.filter
        }

        # Remove None values
        filter_args = {k: v for k, v in filter_args.items() if v is not None}

        # Run collection
        summary = collector.run_collection(filter_args if filter_args else None)

        print("Collection completed successfully!")
        print(f"Total devices: {summary['collection_summary']['total_devices']}")
        print(f"Successful: {summary['collection_summary']['successful_collections']}")
        print(f"Failed: {summary['collection_summary']['failed_collections']}")

    except Exception as e:
        logger.error(f"Collection failed: {e}")
        print(f"Error: {e}")
        sys.exit(1)


def credential_management_tool():
    """Standalone credential management tool"""
    parser = argparse.ArgumentParser(description='RapidCMDB Credential Management Tool')
    parser.add_argument('--app-name', default='rapidcmdb_collector',
                        help='Application name for credential store')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Add credential
    add_parser = subparsers.add_parser('add', help='Add new credential set')
    add_parser.add_argument('name', help='Credential set name')
    add_parser.add_argument('username', help='Device username')
    add_parser.add_argument('--enable-password', default='', help='Enable password')
    add_parser.add_argument('--priority', type=int, default=999, help='Priority (lower = higher priority)')

    # List credentials
    list_parser = subparsers.add_parser('list', help='List credential sets')

    # Update credential
    update_parser = subparsers.add_parser('update', help='Update credential set')
    update_parser.add_argument('name', help='Credential set name')
    update_parser.add_argument('--username', help='New username')
    update_parser.add_argument('--enable-password', help='New enable password')
    update_parser.add_argument('--priority', type=int, help='New priority')
    update_parser.add_argument('--password', action='store_true', help='Update password (will prompt)')

    # Delete credential
    del_parser = subparsers.add_parser('delete', help='Delete credential set')
    del_parser.add_argument('name', help='Credential set name to delete')

    # Migrate legacy config
    migrate_parser = subparsers.add_parser('migrate', help='Migrate from legacy YAML config')
    migrate_parser.add_argument('legacy_file', help='Path to legacy collector_config.yaml')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Initialize secure config
    secure_config = SecureCollectorConfig(args.app_name)
    wrapper = LegacyConfigWrapper(secure_config)

    if args.command == 'migrate':
        if not wrapper.unlock_prompt():
            return

        if secure_config.migrate_legacy_config(args.legacy_file):
            print("Migration completed successfully.")
            print("Legacy configuration file has been backed up.")
            print("You can now delete the original collector_config.yaml file.")
        else:
            print("Migration failed.")
        return

    if not wrapper.unlock_prompt():
        return

    if args.command == 'add':
        import getpass
        password = getpass.getpass("Enter device password: ")

        if secure_config.add_credential_set(
                name=args.name,
                username=args.username,
                password=password,
                enable_password=args.enable_password,
                priority=args.priority
        ):
            print(f"Credential set '{args.name}' added successfully.")
        else:
            print(f"Failed to add credential set '{args.name}'.")

    elif args.command == 'list':
        creds = secure_config.load_network_credentials()
        if creds:
            print("Available credential sets:")
            print(f"{'Name':<15} {'Username':<15} {'Priority':<10} {'Created':<20}")
            print("-" * 65)
            for cred in sorted(creds, key=lambda x: x.get('priority', 999)):
                created = cred.get('created', 'Unknown')[:19] if cred.get('created') else 'Unknown'
                print(f"{cred['name']:<15} {cred['username']:<15} {cred.get('priority', 999):<10} {created:<20}")
        else:
            print("No credential sets found.")

    elif args.command == 'update':
        import getpass

        update_data = {}
        if args.username:
            update_data['username'] = args.username
        if args.enable_password is not None:
            update_data['enable_password'] = args.enable_password
        if args.priority is not None:
            update_data['priority'] = args.priority
        if args.password:
            new_password = getpass.getpass("Enter new device password: ")
            update_data['password'] = new_password

        if update_data:
            if secure_config.update_credential_set(args.name, **update_data):
                print(f"Credential set '{args.name}' updated successfully.")
            else:
                print(f"Failed to update credential set '{args.name}'.")
        else:
            print("No updates specified.")

    elif args.command == 'delete':
        confirm = input(f"Are you sure you want to delete credential set '{args.name}'? (y/N): ")
        if confirm.lower() == 'y':
            if secure_config.delete_credential_set(args.name):
                print(f"Credential set '{args.name}' deleted successfully.")
            else:
                print(f"Failed to delete credential set '{args.name}'.")
        else:
            print("Deletion cancelled.")


if __name__ == "__main__":
    import sys

    # Determine which tool to run based on script name or first argument
    script_name = Path(sys.argv[0]).name

    if 'cred' in script_name or (len(sys.argv) > 1 and sys.argv[1] == 'creds'):
        # Remove 'creds' from argv if it was used as a command
        if len(sys.argv) > 1 and sys.argv[1] == 'creds':
            sys.argv.pop(1)
        credential_management_tool()
    elif 'db' in script_name:
        secure_db_collector_main()
    else:
        secure_collector_main()