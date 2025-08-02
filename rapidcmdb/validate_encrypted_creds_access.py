#!/usr/bin/env python3
"""
RapidCMDB Credential Setup and Testing Utility
Helps set up and test the secure credential management system for the pipeline
"""

import os
import sys
import argparse
import getpass
import yaml
import json
from pathlib import Path
from datetime import datetime

# Import the credential manager (adjust path as needed)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from termtel.helpers.credslib import SecureCredentials
except ImportError:
    print("Error: Could not import SecureCredentials")
    print("Please ensure termtel.helpers.credslib is available")
    sys.exit(1)


class RapidCMDBCredentialManager:
    """Utility class for managing RapidCMDB credentials"""

    def __init__(self):
        self.network_cred_manager = SecureCredentials("rapidcmdb_collector")

    def setup_credentials(self):
        """Initial setup of credential store"""
        print("🔐 RapidCMDB Network Credential Setup")
        print("=" * 50)

        if self.network_cred_manager.is_initialized:
            print("✅ Credential store already initialized")

            if self.network_cred_manager.is_unlocked():
                print("✅ Credential store is unlocked")
            else:
                print("🔒 Credential store is locked")
                self._unlock_credentials()
        else:
            print("🆕 Setting up new credential store...")
            self._initialize_credential_store()

    def _initialize_credential_store(self):
        """Initialize a new credential store"""
        print("\nCreating new secure credential store...")

        while True:
            master_password = getpass.getpass("Enter master password for credential store: ")
            confirm_password = getpass.getpass("Confirm master password: ")

            if master_password != confirm_password:
                print("❌ Passwords don't match. Please try again.")
                continue

            if len(master_password) < 8:
                print("❌ Password must be at least 8 characters long.")
                continue

            break

        if self.network_cred_manager.setup_new_credentials(master_password):
            print("✅ Credential store initialized successfully!")
            return True
        else:
            print("❌ Failed to initialize credential store")
            return False

    def _unlock_credentials(self):
        """Unlock existing credential store"""
        attempts = 3

        while attempts > 0:
            master_password = getpass.getpass(f"Enter master password ({attempts} attempts remaining): ")

            if self.network_cred_manager.unlock(master_password):
                print("✅ Credential store unlocked successfully!")
                return True
            else:
                attempts -= 1
                if attempts > 0:
                    print(f"❌ Invalid password. {attempts} attempts remaining.")
                else:
                    print("❌ Maximum attempts exceeded.")

        return False

    def add_credential(self, name=None, username=None, password=None, enable_password=None, priority=None):
        """Add a new credential set"""
        if not self.network_cred_manager.is_unlocked():
            print("❌ Credential store is not unlocked")
            return False

        print("\n📝 Adding New Network Credential")
        print("-" * 30)

        # Get credential details interactively if not provided
        if not name:
            name = input("Credential name (e.g., 'primary', 'backup'): ").strip()

        if not username:
            username = input("Device username: ").strip()

        if not password:
            password = getpass.getpass("Device password: ")

        if enable_password is None:
            enable_input = getpass.getpass("Enable password (press Enter if none): ")
            enable_password = enable_input if enable_input else ""

        if priority is None:
            try:
                priority = int(input("Priority (1-999, lower = higher priority) [999]: ") or "999")
            except ValueError:
                priority = 999

        # Validate inputs
        if not name or not username or not password:
            print("❌ Name, username, and password are required")
            return False

        # Load existing credentials
        try:
            creds_path = self.network_cred_manager.config_dir / "network_credentials.yaml"

            if creds_path.exists():
                existing_creds = self.network_cred_manager.load_credentials(creds_path)
            else:
                existing_creds = []

            # Check for duplicate names
            if any(cred['name'] == name for cred in existing_creds):
                print(f"❌ Credential '{name}' already exists")
                return False

            # Create new credential
            new_credential = {
                'name': name,
                'username': username,
                'password': password,
                'enable_password': enable_password,
                'priority': priority,
                'created': datetime.now().isoformat()
            }

            # Add to list and save
            existing_creds.append(new_credential)
            self.network_cred_manager.save_credentials(existing_creds, creds_path)

            print(f"✅ Credential '{name}' added successfully!")
            return True

        except Exception as e:
            print(f"❌ Error adding credential: {e}")
            return False

    def list_credentials(self):
        """List all stored credentials"""
        if not self.network_cred_manager.is_unlocked():
            print("❌ Credential store is not unlocked")
            return

        try:
            creds_path = self.network_cred_manager.config_dir / "network_credentials.yaml"

            if not creds_path.exists():
                print("📝 No credentials stored yet")
                return

            credentials = self.network_cred_manager.load_credentials(creds_path)

            if not credentials:
                print("📝 No credentials found")
                return

            print("\n📋 Stored Network Credentials")
            print("=" * 50)

            # Sort by priority
            credentials.sort(key=lambda x: x.get('priority', 999))

            for cred in credentials:
                print(f"Name: {cred.get('name', 'Unknown')}")
                print(f"  Username: {cred.get('username', 'Unknown')}")
                print(f"  Enable Password: {'Yes' if cred.get('enable_password') else 'No'}")
                print(f"  Priority: {cred.get('priority', 999)}")
                print(f"  Created: {cred.get('created', 'Unknown')[:19]}")
                print()

        except Exception as e:
            print(f"❌ Error listing credentials: {e}")

    def test_environment_variables(self):
        """Test environment variable generation"""
        if not self.network_cred_manager.is_unlocked():
            print("❌ Credential store is not unlocked")
            return

        try:
            creds_path = self.network_cred_manager.config_dir / "network_credentials.yaml"

            if not creds_path.exists():
                print("❌ No credentials found")
                return

            credentials = self.network_cred_manager.load_credentials(creds_path)

            if not credentials:
                print("❌ No credentials found")
                return

            print("\n🧪 Environment Variables Test")
            print("=" * 40)

            # Sort by priority
            credentials.sort(key=lambda x: x.get('priority', 999))

            print("Environment variables that would be set:")
            print()

            for cred in credentials:
                name = cred.get('name', 'unknown').upper()
                username = cred.get('username', '')
                password = cred.get('password', '')
                enable_password = cred.get('enable_password', '')
                priority = cred.get('priority', 999)

                print(f"NAPALM_USERNAME_{name}={username}")
                print(f"NAPALM_PASSWORD_{name}={'*' * len(password)}")
                if enable_password:
                    print(f"NAPALM_ENABLE_{name}={'*' * len(enable_password)}")
                print(f"NAPALM_PRIORITY_{name}={priority}")
                print()

            print(f"Total credential sets: {len(credentials)}")

        except Exception as e:
            print(f"❌ Error testing environment variables: {e}")

    def import_from_legacy_config(self, config_file):
        """Import credentials from legacy YAML config"""
        if not self.network_cred_manager.is_unlocked():
            print("❌ Credential store is not unlocked")
            return False

        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            if not config or 'credentials' not in config:
                print("❌ No credentials found in config file")
                return False

            legacy_creds = config['credentials']
            if not legacy_creds:
                print("❌ No credentials found in config file")
                return False

            print(f"\n📥 Importing {len(legacy_creds)} credentials from {config_file}")
            print("-" * 50)

            # Load existing credentials
            creds_path = self.network_cred_manager.config_dir / "network_credentials.yaml"

            if creds_path.exists():
                existing_creds = self.network_cred_manager.load_credentials(creds_path)
            else:
                existing_creds = []

            imported_count = 0

            for cred in legacy_creds:
                name = cred.get('name', f'imported_{imported_count}')
                username = cred.get('username', '')
                password = cred.get('password', '')
                enable_password = cred.get('enable_password', '')
                priority = cred.get('priority', 999)

                # Check for conflicts
                if any(existing['name'] == name for existing in existing_creds):
                    print(f"⚠️  Skipping '{name}' - already exists")
                    continue

                # Create new credential
                new_credential = {
                    'name': name,
                    'username': username,
                    'password': password,
                    'enable_password': enable_password,
                    'priority': priority,
                    'created': datetime.now().isoformat(),
                    'imported_from': config_file
                }

                existing_creds.append(new_credential)
                imported_count += 1
                print(f"✅ Imported credential '{name}'")

            if imported_count > 0:
                # Save updated credentials
                self.network_cred_manager.save_credentials(existing_creds, creds_path)
                print(f"\n✅ Successfully imported {imported_count} credentials")

                # Suggest removing legacy file
                print(f"\n🔒 Security Recommendation:")
                print(f"Consider deleting the legacy config file: {config_file}")
                print("It contains plaintext passwords and is no longer needed.")

                return True
            else:
                print("❌ No credentials were imported")
                return False

        except Exception as e:
            print(f"❌ Error importing credentials: {e}")
            return False

    def export_for_testing(self, output_file):
        """Export credentials in a format suitable for testing (without passwords)"""
        if not self.network_cred_manager.is_unlocked():
            print("❌ Credential store is not unlocked")
            return

        try:
            creds_path = self.network_cred_manager.config_dir / "network_credentials.yaml"

            if not creds_path.exists():
                print("❌ No credentials found")
                return

            credentials = self.network_cred_manager.load_credentials(creds_path)

            if not credentials:
                print("❌ No credentials found")
                return

            # Create sanitized export
            export_data = {
                'export_date': datetime.now().isoformat(),
                'credential_count': len(credentials),
                'credentials': []
            }

            for cred in credentials:
                sanitized_cred = {
                    'name': cred.get('name'),
                    'username': cred.get('username'),
                    'has_password': bool(cred.get('password')),
                    'has_enable_password': bool(cred.get('enable_password')),
                    'priority': cred.get('priority'),
                    'created': cred.get('created')
                }
                export_data['credentials'].append(sanitized_cred)

            with open(output_file, 'w') as f:
                json.dump(export_data, f, indent=2)

            print(f"✅ Credential summary exported to {output_file}")

        except Exception as e:
            print(f"❌ Error exporting credentials: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='RapidCMDB Credential Setup and Testing Utility',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Initial setup
  python credential_setup.py --setup

  # Add a credential interactively
  python credential_setup.py --add

  # Add a credential with parameters
  python credential_setup.py --add --name primary --username admin --priority 1

  # List all credentials
  python credential_setup.py --list

  # Test environment variable generation
  python credential_setup.py --test-env

  # Import from legacy config
  python credential_setup.py --import collector_config.yaml

  # Export sanitized summary
  python credential_setup.py --export credentials_summary.json
        ''')

    parser.add_argument('--setup', action='store_true', help='Initial credential store setup')
    parser.add_argument('--add', action='store_true', help='Add new credential')
    parser.add_argument('--list', action='store_true', help='List stored credentials')
    parser.add_argument('--test-env', action='store_true', help='Test environment variable generation')
    parser.add_argument('--import', dest='import_file', help='Import from legacy config file')
    parser.add_argument('--export', dest='export_file', help='Export credential summary')

    # Add credential parameters
    parser.add_argument('--name', help='Credential name')
    parser.add_argument('--username', help='Device username')
    parser.add_argument('--priority', type=int, help='Credential priority (1-999)')

    args = parser.parse_args()

    if not any([args.setup, args.add, args.list, args.test_env, args.import_file, args.export_file]):
        parser.print_help()
        return

    # Initialize credential manager
    cred_manager = RapidCMDBCredentialManager()

    try:
        if args.setup:
            cred_manager.setup_credentials()

        elif args.add:
            if not cred_manager.network_cred_manager.is_initialized:
                print("❌ Credential store not initialized. Run with --setup first.")
                return

            if not cred_manager.network_cred_manager.is_unlocked():
                if not cred_manager._unlock_credentials():
                    return

            cred_manager.add_credential(
                name=args.name,
                username=args.username,
                priority=args.priority
            )

        elif args.list:
            if not cred_manager.network_cred_manager.is_initialized:
                print("❌ Credential store not initialized. Run with --setup first.")
                return

            if not cred_manager.network_cred_manager.is_unlocked():
                if not cred_manager._unlock_credentials():
                    return

            cred_manager.list_credentials()

        elif args.test_env:
            if not cred_manager.network_cred_manager.is_initialized:
                print("❌ Credential store not initialized. Run with --setup first.")
                return

            if not cred_manager.network_cred_manager.is_unlocked():
                if not cred_manager._unlock_credentials():
                    return

            cred_manager.test_environment_variables()

        elif args.import_file:
            if not cred_manager.network_cred_manager.is_initialized:
                print("❌ Credential store not initialized. Run with --setup first.")
                return

            if not cred_manager.network_cred_manager.is_unlocked():
                if not cred_manager._unlock_credentials():
                    return

            if not os.path.exists(args.import_file):
                print(f"❌ File not found: {args.import_file}")
                return

            cred_manager.import_from_legacy_config(args.import_file)

        elif args.export_file:
            if not cred_manager.network_cred_manager.is_initialized:
                print("❌ Credential store not initialized. Run with --setup first.")
                return

            if not cred_manager.network_cred_manager.is_unlocked():
                if not cred_manager._unlock_credentials():
                    return

            cred_manager.export_for_testing(args.export_file)

    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()