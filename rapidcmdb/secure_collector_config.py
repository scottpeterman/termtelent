# rapidcmdb/secure_collector_config.py
"""
Secure credential management for RapidCMDB collectors
Extends the existing SecureCredentials system for network device access
"""

import os
import yaml
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Import your existing secure credentials system
from termtel.helpers.credslib import SecureCredentials

logger = logging.getLogger(__name__)


class SecureCollectorConfig:
    """Secure configuration manager for NAPALM collectors"""

    def __init__(self, app_name: str = "rapidcmdb_collector"):
        self.app_name = app_name
        self.cred_manager = SecureCredentials(app_name)
        self.config_dir = self._get_config_dir()
        self.secure_config_file = self.config_dir / "secure_collector_config.yaml"
        self.credentials_file = self.config_dir / "network_credentials.yaml"

    def _get_config_dir(self) -> Path:
        """Get configuration directory"""
        if os.name == 'nt':  # Windows
            base_dir = Path(os.environ["APPDATA"])
        elif os.uname().sysname == 'Darwin':  # macOS
            base_dir = Path.home() / "Library" / "Application Support"
        else:  # Linux
            base_dir = Path.home() / ".config"

        config_dir = base_dir / self.app_name
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir

    def is_initialized(self) -> bool:
        """Check if secure config is initialized"""
        return self.cred_manager.is_initialized and self.secure_config_file.exists()

    def is_unlocked(self) -> bool:
        """Check if credential manager is unlocked"""
        return self.cred_manager.is_unlocked()

    def unlock(self, master_password: str) -> bool:
        """Unlock the credential manager"""
        return self.cred_manager.unlock(master_password)

    def setup_new_config(self, master_password: str) -> bool:
        """Initialize secure configuration"""
        try:
            # Initialize credential manager
            if not self.cred_manager.setup_new_credentials(master_password):
                return False

            # Create secure configuration template
            self._create_secure_config_template()

            # Create empty credentials store
            self.save_network_credentials([])

            logger.info("Secure collector configuration initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to setup secure config: {e}")
            return False

    def _create_secure_config_template(self):
        """Create secure configuration template (non-sensitive settings only)"""
        secure_config = {
            'version': '1.0',
            'created': datetime.now().isoformat(),
            'app_name': self.app_name,

            # Non-sensitive collector settings
            'collection_settings': {
                'capture_directory': 'captures',
                'timeout': 60,
                'max_workers': 10,
                'log_level': 'INFO',
                'enhanced_inventory': True,
                'inventory_cli_fallback': True,
                'detailed_timing': True,
                'performance_metrics': True
            },

            # Collection methods (what data to gather)
            'collection_methods': {
                'get_config': True,
                'get_facts': True,
                'get_interfaces': True,
                'get_interfaces_ip': True,
                'get_arp_table': True,
                'get_mac_address_table': True,
                'get_lldp_neighbors': True,
                'get_environment': True,
                'get_users': True,
                'get_optics': True,
                'get_network_instances': True
            },

            # Device filtering
            'device_filters': {
                'active_only': True,
                'site_codes': [],
                'device_roles': [],
                'vendors': [],
                'exclude_models': [],
                'include_non_network': False
            },

            # NAPALM driver mappings
            'vendor_overrides': {
                'hp_procurve': 'procurve',
                'hp_aruba_cx': 'arubaoss',
                'cisco_ios': 'ios',
                'cisco_nxos': 'nxos',
                'cisco_asa': 'asa',
                'arista_eos': 'eos',
                'paloalto_panos': 'panos'
            },

            # Driver-specific options
            'driver_options': {
                'ios': {'transport': 'ssh'},
                'nxos': {'transport': 'ssh'},
                'eos': {'transport': 'ssh'},
                'arubaoss': {'transport': 'ssh'},
                'panos': {'use_keys': False}
            }
        }

        with open(self.secure_config_file, 'w') as f:
            yaml.dump(secure_config, f, default_flow_style=False, indent=2)

    def load_secure_config(self) -> Dict:
        """Load non-sensitive configuration"""
        try:
            with open(self.secure_config_file, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error("Secure config file not found")
            return {}

    def save_network_credentials(self, credentials: List[Dict]) -> bool:
        """Save network device credentials securely"""
        if not self.cred_manager.is_unlocked():
            raise RuntimeError("Credential manager not unlocked")

        try:
            self.cred_manager.save_credentials(credentials, self.credentials_file)
            logger.info(f"Saved {len(credentials)} credential sets")
            return True
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")
            return False

    def load_network_credentials(self) -> List[Dict]:
        """Load network device credentials securely"""
        if not self.cred_manager.is_unlocked():
            raise RuntimeError("Credential manager not unlocked")

        try:
            return self.cred_manager.load_credentials(self.credentials_file)
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            return []

    def add_credential_set(self, name: str, username: str, password: str,
                           enable_password: str = "", priority: int = 999) -> bool:
        """Add a new credential set"""
        credentials = self.load_network_credentials()

        # Check for duplicate names
        if any(cred['name'] == name for cred in credentials):
            logger.warning(f"Credential set '{name}' already exists")
            return False

        new_cred = {
            'name': name,
            'username': username,
            'password': password,
            'enable_password': enable_password,
            'priority': priority,
            'created': datetime.now().isoformat()
        }

        credentials.append(new_cred)
        return self.save_network_credentials(credentials)

    def update_credential_set(self, name: str, **kwargs) -> bool:
        """Update an existing credential set"""
        credentials = self.load_network_credentials()

        for cred in credentials:
            if cred['name'] == name:
                # Update allowed fields
                for key in ['username', 'password', 'enable_password', 'priority']:
                    if key in kwargs:
                        cred[key] = kwargs[key]
                cred['modified'] = datetime.now().isoformat()
                return self.save_network_credentials(credentials)

        logger.warning(f"Credential set '{name}' not found")
        return False

    def delete_credential_set(self, name: str) -> bool:
        """Delete a credential set"""
        credentials = self.load_network_credentials()
        original_count = len(credentials)

        credentials = [cred for cred in credentials if cred['name'] != name]

        if len(credentials) < original_count:
            return self.save_network_credentials(credentials)
        else:
            logger.warning(f"Credential set '{name}' not found")
            return False

    def list_credential_sets(self) -> List[str]:
        """List available credential set names"""
        credentials = self.load_network_credentials()
        return [cred['name'] for cred in credentials]

    def get_legacy_config_dict(self) -> Dict:
        """Generate legacy-compatible config dict for existing collectors"""
        secure_config = self.load_secure_config()
        credentials = self.load_network_credentials()

        # Create legacy-compatible structure
        legacy_config = {
            # Copy all non-sensitive settings
            **secure_config.get('collection_settings', {}),
            'collection_methods': secure_config.get('collection_methods', {}),
            'device_filters': secure_config.get('device_filters', {}),
            'vendor_overrides': secure_config.get('vendor_overrides', {}),
            'driver_options': secure_config.get('driver_options', {}),

            # Add decrypted credentials
            'credentials': credentials
        }

        return legacy_config

    def migrate_legacy_config(self, legacy_config_file: str) -> bool:
        """Migrate from insecure YAML config to secure storage"""
        try:
            with open(legacy_config_file, 'r') as f:
                legacy_config = yaml.safe_load(f)

            # Extract credentials
            legacy_credentials = legacy_config.get('credentials', [])

            # Save credentials securely
            if legacy_credentials:
                self.save_network_credentials(legacy_credentials)
                logger.info(f"Migrated {len(legacy_credentials)} credential sets to secure storage")

            # Create secure config from non-sensitive settings
            secure_config = self.load_secure_config()

            # Update with legacy settings (excluding credentials)
            for section in ['collection_settings', 'collection_methods', 'device_filters',
                            'vendor_overrides', 'driver_options']:
                if section in legacy_config:
                    secure_config[section].update(legacy_config[section])

            # Save updated secure config
            with open(self.secure_config_file, 'w') as f:
                yaml.dump(secure_config, f, default_flow_style=False, indent=2)

            # Backup and remove legacy file
            backup_file = f"{legacy_config_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.rename(legacy_config_file, backup_file)
            logger.info(f"Legacy config backed up to: {backup_file}")

            return True

        except Exception as e:
            logger.error(f"Failed to migrate legacy config: {e}")
            return False


# CLI compatibility wrapper
class LegacyConfigWrapper:
    """Wrapper to maintain CLI compatibility while using secure storage"""

    def __init__(self, secure_config: SecureCollectorConfig):
        self.secure_config = secure_config

    def get_config_dict(self) -> Dict:
        """Get config dict compatible with existing collector code"""
        if not self.secure_config.is_unlocked():
            raise RuntimeError("Secure configuration not unlocked. Call unlock() first.")

        return self.secure_config.get_legacy_config_dict()

    def unlock_prompt(self) -> bool:
        """Prompt for master password and unlock"""
        import getpass

        if not self.secure_config.is_initialized():
            print("Secure configuration not initialized.")
            print("Creating new secure credential store...")

            while True:
                password = getpass.getpass("Enter new master password: ")
                confirm = getpass.getpass("Confirm master password: ")

                if password == confirm and len(password) >= 8:
                    if self.secure_config.setup_new_config(password):
                        print("Secure configuration initialized successfully.")
                        return True
                    else:
                        print("Failed to initialize secure configuration.")
                        return False
                else:
                    print("Passwords don't match or too short (minimum 8 characters)")

        else:
            attempts = 3
            while attempts > 0:
                password = getpass.getpass(f"Enter master password ({attempts} attempts remaining): ")

                if self.secure_config.unlock(password):
                    print("Credentials unlocked successfully.")
                    return True
                else:
                    attempts -= 1
                    if attempts > 0:
                        print("Invalid password. Try again.")
                    else:
                        print("Maximum attempts exceeded.")

            return False


# CLI utility functions for managing credentials
def credential_manager_cli():
    """Command-line interface for credential management"""
    import argparse

    parser = argparse.ArgumentParser(description='RapidCMDB Secure Credential Manager')
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
        creds = secure_config.list_credential_sets()
        if creds:
            print("Available credential sets:")
            for name in creds:
                print(f"  - {name}")
        else:
            print("No credential sets found.")

    elif args.command == 'delete':
        if secure_config.delete_credential_set(args.name):
            print(f"Credential set '{args.name}' deleted successfully.")
        else:
            print(f"Failed to delete credential set '{args.name}'.")


if __name__ == "__main__":
    credential_manager_cli()