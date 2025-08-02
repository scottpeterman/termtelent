#!/usr/bin/env python3
"""
Concurrent NAPALM Device Collector with Enhanced Inventory and Runtime Tracking
Collects configuration, inventory, and version information from network devices
WITH IMPROVED MULTI-CREDENTIAL SUPPORT AND SEQUENTIAL COLLECTION PER DEVICE
"""

import json
import yaml
import os
import logging
import argparse
import time
import re
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any
import napalm
from napalm.base.exceptions import ConnectionException, CommandErrorException


class CredentialManager:
    """Manages credentials from both config files and environment variables"""

    def __init__(self, config: Dict):
        self.config = config

    def load_credentials(self) -> List[Dict]:
        """
        Load credentials ONLY from environment variables.

        Environment variable patterns:
        - NAPALM_USER_<n> or NAPALM_USERNAME_<n>
        - NAPALM_PASS_<n> or NAPALM_PASSWORD_<n>
        - NAPALM_ENABLE_<n> or NAPALM_ENABLE_PASSWORD_<n>
        - NAPALM_PRIORITY_<n>

        Where <n> is the credential set name (e.g., PRIMARY, BACKUP, etc.)
        """
        logging.info("Loading credentials from environment variables only")

        # Load credentials from environment variables
        env_creds = self._load_env_credentials()

        # Validate credentials
        validated_creds = self._validate_credentials(env_creds)

        if not validated_creds:
            logging.error("No valid credentials found in environment variables")
            logging.error("Required environment variables:")
            logging.error("  NAPALM_USERNAME_<name> (or NAPALM_USER_<name>)")
            logging.error("  NAPALM_PASSWORD_<name> (or NAPALM_PASS_<name>)")
            logging.error("  NAPALM_PRIORITY_<name> (optional, defaults to 999)")
            logging.error("  NAPALM_ENABLE_<name> (optional)")
            logging.error("")
            logging.error("Example:")
            logging.error("  export NAPALM_USERNAME_PRIMARY=admin")
            logging.error("  export NAPALM_PASSWORD_PRIMARY=secret123")
            logging.error("  export NAPALM_PRIORITY_PRIMARY=1")
            raise SystemExit("No credentials found in environment variables - cannot continue")
        else:
            # Log credential names (not passwords)
            cred_names = [cred['name'] for cred in validated_creds]
            logging.info(f"Loaded {len(validated_creds)} credential sets from environment: {', '.join(cred_names)}")

        return validated_creds

    def _load_env_credentials(self) -> List[Dict]:
        """Load credentials from environment variables"""
        env_creds = {}

        # Scan environment for credential patterns
        for env_var, value in os.environ.items():
            if not env_var.startswith('NAPALM_'):
                continue

            # Parse environment variable name
            parts = env_var.split('_')
            if len(parts) < 3:
                continue

            # Extract credential type and name
            cred_type = parts[1].lower()
            cred_name = '_'.join(parts[2:]).upper()

            # Initialize credential dict if needed
            if cred_name not in env_creds:
                env_creds[cred_name] = {
                    'name': cred_name.lower(),
                    '_source': 'environment'
                }

            # Map environment variable to credential field
            if cred_type in ['user', 'username']:
                env_creds[cred_name]['username'] = value
            elif cred_type in ['pass', 'password']:
                env_creds[cred_name]['password'] = value
            elif cred_type in ['enable', 'enable_password']:
                env_creds[cred_name]['enable_password'] = value
            elif cred_type == 'priority':
                try:
                    env_creds[cred_name]['priority'] = int(value)
                except ValueError:
                    logging.warning(f"Invalid priority value in {env_var}: {value}")

        return list(env_creds.values())

    def _validate_credentials(self, credentials: List[Dict]) -> List[Dict]:
        """Validate that credentials have required fields"""
        validated = []

        for cred in credentials:
            name = cred.get('name')
            username = cred.get('username')
            password = cred.get('password')

            if not name:
                logging.warning("Skipping credential without name")
                continue

            if not username:
                logging.error(f"Credential '{name}' is missing username - check NAPALM_USERNAME_{name.upper()}")
                continue

            if not password:
                logging.error(f"Credential '{name}' is missing password - check NAPALM_PASSWORD_{name.upper()}")
                continue

            # Set default priority if not specified
            if 'priority' not in cred:
                cred['priority'] = 999

            # Ensure enable_password is set (can be empty string)
            if 'enable_password' not in cred:
                cred['enable_password'] = ''

            validated.append(cred)

        return validated


class CollectionStats:
    """Track collection statistics and timing"""

    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.device_times = {}
        self.collection_results = []
        self.error_summary = {}

    def start_collection(self):
        """Mark collection start time"""
        self.start_time = datetime.now()

    def end_collection(self):
        """Mark collection end time"""
        self.end_time = datetime.now()

    def start_device_collection(self, device_ip: str):
        """Mark start time for individual device"""
        self.device_times[device_ip] = {'start': datetime.now()}

    def end_device_collection(self, device_ip: str):
        """Mark end time for individual device"""
        if device_ip in self.device_times:
            self.device_times[device_ip]['end'] = datetime.now()
            self.device_times[device_ip]['duration'] = (
                    self.device_times[device_ip]['end'] -
                    self.device_times[device_ip]['start']
            ).total_seconds()

    def add_result(self, result: Dict):
        """Add a collection result"""
        self.collection_results.append(result)

    def get_total_runtime(self) -> float:
        """Get total collection runtime in seconds"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0

    def get_average_device_time(self) -> float:
        """Get average time per device"""
        times = [d['duration'] for d in self.device_times.values() if 'duration' in d]
        return sum(times) / len(times) if times else 0


class DeviceCollector:
    """Main collector class for NAPALM-based device data collection"""

    def __init__(self, config_file: str = "collector_config.yaml", max_workers: int = 10):
        self.config_file = config_file
        self.max_workers = max_workers
        self.config = self._load_config()
        self.capture_dir = Path(self.config.get('capture_directory', 'captures'))
        self.setup_logging()

        # Initialize credential manager
        self.credential_manager = CredentialManager(self.config)

        # Initialize statistics tracking
        self.stats = CollectionStats()

        # Create capture directory if it doesn't exist
        self.capture_dir.mkdir(exist_ok=True)

        # NAPALM driver mapping for different vendors
        self.driver_mapping = {
            'cisco': 'ios',
            'arista': 'eos',
            'paloalto': 'panos',
            'hp': 'procurve',
            'aruba': 'arubaoss',
            'fortinet': 'fortios',
            'juniper': 'junos'
        }

    def _load_config(self) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(self.config_file, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logging.error(f"Config file {self.config_file} not found. Creating template...")
            self._create_config_template()
            raise

    def _create_config_template(self):
        """Create a template configuration file WITHOUT credentials (env vars only)"""
        template_config = {
            'capture_directory': 'captures',
            'timeout': 60,
            'max_workers': 10,
            'enhanced_inventory': True,
            'inventory_cli_fallback': True,
            'inventory_parsing': True,
            'detailed_timing': True,
            'performance_metrics': True,
            '_credentials_info': {
                '_note': 'Credentials are loaded ONLY from environment variables',
                '_required_variables': [
                    'NAPALM_USERNAME_<name> (or NAPALM_USER_<name>)',
                    'NAPALM_PASSWORD_<name> (or NAPALM_PASS_<name>)'
                ],
                '_optional_variables': [
                    'NAPALM_ENABLE_<name> (or NAPALM_ENABLE_PASSWORD_<name>)',
                    'NAPALM_PRIORITY_<name> (lower number = higher priority)'
                ],
                '_examples': [
                    'export NAPALM_USERNAME_PRIMARY=admin',
                    'export NAPALM_PASSWORD_PRIMARY=secret123',
                    'export NAPALM_ENABLE_PRIMARY=enable_secret',
                    'export NAPALM_PRIORITY_PRIMARY=1',
                    'export NAPALM_USERNAME_BACKUP=backup_user',
                    'export NAPALM_PASSWORD_BACKUP=backup_pass',
                    'export NAPALM_PRIORITY_BACKUP=2'
                ]
            },
            'collection_methods': {
                'get_config': True,
                'get_facts': True,
                'get_inventory': True,
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
            'vendor_overrides': {
                'hp_procurve': 'procurve',
                'hp_aruba_cx': 'arubaoss',
                'cisco_ios': 'ios',
                'cisco_nxos': 'nxos',
                'cisco_asa': 'asa'
            },
            'driver_options': {
                'eos': {'transport': 'ssh'},
                'arubaoss': {'transport': 'ssh'}
            }
        }

        with open(self.config_file, 'w') as f:
            yaml.dump(template_config, f, default_flow_style=False, indent=2)

        # Also create environment template file
        env_template_path = self.config_file.replace('.yaml', '_env_template.sh')
        env_template = """#!/bin/bash
# NAPALM Collector Environment Variable Template
# Source this file or add these exports to your shell profile

# Primary credentials (highest priority)
export NAPALM_USERNAME_PRIMARY="admin"
export NAPALM_PASSWORD_PRIMARY="your_password_here"
export NAPALM_ENABLE_PRIMARY="your_enable_password_here"  # Optional
export NAPALM_PRIORITY_PRIMARY="1"

# Backup credentials
export NAPALM_USERNAME_BACKUP="backup_user"
export NAPALM_PASSWORD_BACKUP="backup_password"
export NAPALM_ENABLE_BACKUP=""  # Empty if no enable password
export NAPALM_PRIORITY_BACKUP="2"

# Service account credentials
export NAPALM_USERNAME_SERVICE="svc_napalm"
export NAPALM_PASSWORD_SERVICE="service_account_password"
export NAPALM_PRIORITY_SERVICE="3"

# Alternative variable names also supported:
# NAPALM_USER_* instead of NAPALM_USERNAME_*
# NAPALM_PASS_* instead of NAPALM_PASSWORD_*
# NAPALM_ENABLE_PASSWORD_* instead of NAPALM_ENABLE_*

echo "NAPALM environment variables loaded"
"""

        with open(env_template_path, 'w') as f:
            f.write(env_template)

        print(f"Created template config file: {self.config_file}")
        print(f"Created environment template: {env_template_path}")

    def setup_logging(self):
        """Setup logging configuration"""
        log_level = self.config.get('log_level', 'INFO')
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('collector.log'),
                logging.StreamHandler()
            ]
        )

    def get_napalm_driver(self, device: Dict) -> Optional[str]:
        """Determine the appropriate NAPALM driver for a device"""
        vendor = device.get('vendor', '').lower()
        device_type = device.get('device_type', '').lower()

        # Check vendor overrides first
        vendor_overrides = self.config.get('vendor_overrides', {})
        for override_key, driver in vendor_overrides.items():
            if override_key.lower() in f"{vendor}_{device_type}":
                return driver

        # Check sys_descr for more specific identification
        sys_descr = device.get('sys_descr', '').lower()

        # Cisco specific logic
        if vendor == 'cisco':
            if 'nx-os' in sys_descr or 'nexus' in sys_descr:
                return 'nxos'
            elif 'asa' in sys_descr:
                return 'asa'
            elif 'xe' in sys_descr or 'ios' in sys_descr:
                return 'ios'

        # HP/Aruba logic
        elif vendor == 'hp' or vendor == 'aruba':
            if 'procurve' in sys_descr or 'j' in device.get('sys_name', '').lower():
                return 'procurve'
            elif 'arubaos' in sys_descr or 'cx' in sys_descr:
                return 'arubaoss'

        # Default mapping
        return self.driver_mapping.get(vendor)

    def _clean_device_name(self, device_name: str) -> str:
        """Clean device name by removing domain and making filesystem-safe"""
        if not device_name:
            return "unknown_device"

        # Don't split IP addresses - only split actual hostnames with domains
        if not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', device_name):
            # Strip domain name (everything after first dot) only if it's not an IP
            if '.' in device_name:
                device_name = device_name.split('.')[0]

        # Replace filesystem-unsafe characters
        unsafe_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', ' ']
        for char in unsafe_chars:
            device_name = device_name.replace(char, '_')

        # Remove consecutive underscores and strip leading/trailing underscores
        while '__' in device_name:
            device_name = device_name.replace('__', '_')
        device_name = device_name.strip('_')

        # Ensure we have a valid name
        if not device_name:
            device_name = "unknown_device"

        return device_name

    def save_device_data(self, device_result: Dict):
        """Save collected device data to files"""
        if not device_result['success']:
            logging.error(f"Skipping save for {device_result['device_name']} - collection failed")
            return

        device_name = device_result['device_name']
        device_ip = device_result['device_ip']

        # Clean device name for filesystem safety
        safe_device_name = device_name.replace('/', '_').replace('\\', '_').replace(':', '_')

        device_dir = self.capture_dir / safe_device_name
        device_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save complete result as JSON
        result_file = device_dir / f"{safe_device_name}_complete.json"
        with open(result_file, 'w') as f:
            json.dump(device_result, f, indent=2, default=str)

        # Save individual data types as separate files
        for data_type, data in device_result['data'].items():
            if data_type == 'get_config':
                # Save configs as text files
                if isinstance(data, dict):
                    for config_type, config_content in data.items():
                        config_file = device_dir / f"{safe_device_name}_{config_type}_config.txt"
                        with open(config_file, 'w') as f:
                            f.write(config_content)
                else:
                    config_file = device_dir / f"{safe_device_name}_config.txt"
                    with open(config_file, 'w') as f:
                        f.write(str(data))

            else:
                # Save other data as JSON
                data_file = device_dir / f"{safe_device_name}_{data_type}.json"
                with open(data_file, 'w') as f:
                    json.dump(data, f, indent=2, default=str)

        logging.info(f"Saved data for {device_name} ({device_ip}) to {device_dir}")

    def generate_comprehensive_summary(self, results: List[Dict]):
        """Generate comprehensive collection summary with runtime statistics"""

        # Calculate summary statistics
        total_devices = len(results)
        successful = sum(1 for r in results if r['success'])
        failed = total_devices - successful

        # Vendor analysis
        vendors = {}
        device_types = {}
        credential_usage = {}
        error_analysis = {}
        method_statistics = {}

        for result in results:
            # Vendor statistics
            if result['success'] and 'get_facts' in result['data']:
                facts = result['data']['get_facts']
                vendor = facts.get('vendor', 'unknown')
                vendors[vendor] = vendors.get(vendor, 0) + 1

                # Device type statistics
                device_type = facts.get('model', 'unknown')
                device_types[device_type] = device_types.get(device_type, 0) + 1

            # Credential usage
            if result.get('credential_used'):
                cred = result['credential_used']
                credential_usage[cred] = credential_usage.get(cred, 0) + 1

            # Error analysis
            for error in result.get('errors', []):
                error_type = error.split(':')[0] if ':' in error else 'unknown'
                error_analysis[error_type] = error_analysis.get(error_type, 0) + 1

            # Method statistics
            for method_info in result.get('methods_collected', []):
                method_name = method_info['method']
                if method_name not in method_statistics:
                    method_statistics[method_name] = {
                        'success_count': 0,
                        'total_duration': 0,
                        'avg_duration': 0,
                        'total_data_size': 0
                    }
                method_statistics[method_name]['success_count'] += 1
                method_statistics[method_name]['total_duration'] += method_info['duration']
                method_statistics[method_name]['total_data_size'] += method_info['data_size']

        # Calculate averages
        for method_name, stats in method_statistics.items():
            if stats['success_count'] > 0:
                stats['avg_duration'] = stats['total_duration'] / stats['success_count']

        # Performance statistics
        device_times = [self.stats.device_times[ip].get('duration', 0)
                        for ip in self.stats.device_times.keys()]

        summary = {
            'collection_summary': {
                'start_time': self.stats.start_time.isoformat() if self.stats.start_time else None,
                'end_time': self.stats.end_time.isoformat() if self.stats.end_time else None,
                'total_runtime_seconds': self.stats.get_total_runtime(),
                'total_runtime_formatted': str(timedelta(seconds=int(self.stats.get_total_runtime()))),
                'devices_per_minute': (successful / (
                        self.stats.get_total_runtime() / 60)) if self.stats.get_total_runtime() > 0 else 0
            },
            'collection_results': {
                'total_devices': total_devices,
                'successful_collections': successful,
                'failed_collections': failed,
                'success_rate': (successful / total_devices * 100) if total_devices > 0 else 0
            },
            'performance_metrics': {
                'average_device_time': self.stats.get_average_device_time(),
                'fastest_device_time': min(device_times) if device_times else 0,
                'slowest_device_time': max(device_times) if device_times else 0,
                'concurrent_workers': self.max_workers
            },
            'vendor_breakdown': vendors,
            'device_types': device_types,
            'credential_usage': credential_usage,
            'error_analysis': error_analysis,
            'method_statistics': method_statistics,
            'configuration_used': {
                'max_workers': self.max_workers,
                'timeout': self.config.get('timeout', 60),
                'enhanced_inventory': self.config.get('enhanced_inventory', False),
                'collection_methods': self.config.get('collection_methods', {})
            }
        }

        # Save comprehensive summary
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_file = self.capture_dir / f"collection_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        logging.info(f"Comprehensive summary saved to {summary_file}")

        return summary

    def filter_collectible_devices(self, devices: Dict) -> List[Dict]:
        """Filter devices that can be collected via NAPALM and convert to database-compatible format"""
        collectible_devices = []

        for device_id, device in devices.items():
            # Skip devices without vendor info or unknown device types
            if not device.get('vendor') or device.get('device_type') == 'unknown':
                logging.debug(f"Skipping {device['primary_ip']} - no vendor or unknown device type")
                continue

            # Skip non-network devices
            device_type = device.get('device_type', '').lower()
            if device_type in ['printer', 'ups', 'server', 'workstation']:
                logging.debug(f"Skipping {device['primary_ip']} - non-network device ({device_type})")
                continue

            # Check if we have a NAPALM driver for this device
            if self.get_napalm_driver(device):
                # Convert to database-compatible format
                db_compatible_device = {
                    'primary_ip': device['primary_ip'],
                    'device_name': device.get('device_name', device['primary_ip']),
                    'vendor': device.get('vendor', 'unknown'),
                    'model': device.get('model', 'unknown'),
                    'serial_number': device.get('serial_number', ''),
                    'site_code': device.get('site_code', ''),
                    'device_role': device.get('device_role', ''),
                    'device_type': device.get('device_type', 'network'),
                    'sys_name': device.get('sys_name', device.get('device_name', device['primary_ip'])),
                    'sys_descr': device.get('sys_descr', ''),
                    'hostname': device.get('hostname', device.get('device_name', device['primary_ip'])),
                    'id': device_id  # Use the JSON device_id as database_id equivalent
                }
                collectible_devices.append(db_compatible_device)
            else:
                logging.debug(f"Skipping {device['primary_ip']} - no NAPALM driver available")

        return collectible_devices

    def collect_single_device_sequential(self, device: Dict, credentials: List[Dict]) -> Dict:
        """
        Collect all data from a single device sequentially in one thread.
        FIXED: Proper credential fallback logic matching database version
        """
        device_ip = device['primary_ip']
        device_name = device.get('device_name', device_ip)

        # Start timing for this device
        self.stats.start_device_collection(device_ip)

        result = {
            'device_ip': device_ip,
            'device_name': device_name,
            'success': False,
            'data': {},
            'errors': [],
            'credential_used': None,
            'credential_source': None,
            'collection_time': datetime.now().isoformat(),
            'collection_duration': 0,
            'methods_collected': [],
            'methods_failed': []
        }

        # Determine NAPALM driver
        napalm_driver = self.get_napalm_driver(device)
        if not napalm_driver:
            result['errors'].append(f"No NAPALM driver found for vendor: {device.get('vendor', 'unknown')}")
            self.stats.end_device_collection(device_ip)
            return result

        logging.info(f"[{device_name}] Starting sequential collection using driver: {napalm_driver}")

        # Prepare credentials to try - EXACT DATABASE VERSION LOGIC
        credentials_to_try = []

        # Sort credentials by priority and add to try list
        for cred in sorted(credentials, key=lambda x: x.get('priority', 999)):
            credentials_to_try.append((cred, 'tested'))

        # Try to establish connection with working credentials
        device_conn = None
        working_credential = None
        credential_source = None

        for cred, source in credentials_to_try:
            try:
                logging.info(f"[{device_name}] Attempting connection with {source} credentials: {cred['name']}")

                # Setup device connection parameters
                device_params = {
                    'hostname': device_ip,
                    'username': cred['username'],
                    'password': cred['password'],
                    'timeout': self.config.get('timeout', 60),
                    'optional_args': {}
                }

                # Add enable password if provided
                if cred.get('enable_password'):
                    device_params['optional_args']['secret'] = cred['enable_password']

                # Apply driver-specific options from config
                driver_options = self.config.get('driver_options', {})
                if napalm_driver in driver_options:
                    device_params['optional_args'].update(driver_options[napalm_driver])

                # Initialize NAPALM driver
                driver = napalm.get_network_driver(napalm_driver)
                device_conn = driver(**device_params)

                # Test connection
                device_conn.open()
                logging.info(f"[{device_name}] Successfully connected with {source} credentials: {cred['name']}")

                working_credential = cred
                credential_source = source
                break

            except (ConnectionException, CommandErrorException) as e:
                logging.warning(f"[{device_name}] Failed to connect with {source} credentials {cred['name']}: {str(e)}")
                result['errors'].append(f"Credential {cred['name']} ({source}): {str(e)}")

                if device_conn:
                    try:
                        device_conn.close()
                    except:
                        pass
                    device_conn = None
                continue

            except Exception as e:
                logging.error(f"[{device_name}] Unexpected error with credentials {cred['name']}: {str(e)}")
                result['errors'].append(f"Unexpected error: {str(e)}")
                if device_conn:
                    try:
                        device_conn.close()
                    except:
                        pass
                    device_conn = None
                continue

        # If no connection established, return failure
        if not device_conn or not working_credential:
            logging.error(f"[{device_name}] Could not establish connection with any credentials")
            self.stats.end_device_collection(device_ip)
            return result

        # Now collect data sequentially using the established connection
        try:
            # Get collection methods from configuration and build unique list
            collection_methods = self.config.get('collection_methods', {})
            enabled_methods = set()

            for method_name, enabled in collection_methods.items():
                if enabled:
                    enabled_methods.add(method_name)

            # Convert to ordered list, prioritizing get_facts first
            methods_to_collect = []
            if 'get_facts' in enabled_methods:
                methods_to_collect.append('get_facts')
                enabled_methods.remove('get_facts')

            # Add remaining methods in alphabetical order for consistency
            methods_to_collect.extend(sorted(enabled_methods))

            logging.info(
                f"[{device_name}] Will collect {len(methods_to_collect)} methods sequentially using existing connection: {', '.join(methods_to_collect)}")

            # Execute each collection method sequentially
            for method_name in methods_to_collect:
                method_start_time = time.time()
                try:
                    logging.info(f"[{device_name}] Collecting {method_name} using existing connection")

                    # Get the method from the device connection
                    method_func = getattr(device_conn, method_name, None)
                    if not method_func:
                        raise AttributeError(f"Method {method_name} not available for driver {napalm_driver}")

                    # Execute the method
                    method_data = method_func()

                    # Calculate timing and data size
                    method_duration = time.time() - method_start_time
                    data_size = len(json.dumps(method_data, default=str)) if method_data else 0

                    # Store the result
                    result['data'][method_name] = method_data
                    result['methods_collected'].append({
                        'method': method_name,
                        'duration': method_duration,
                        'data_size': data_size,
                        'success': True
                    })

                    # Update device name after collecting facts
                    if method_name == 'get_facts' and method_data:
                        hostname = method_data.get('hostname', method_data.get('fqdn', device_ip))
                        if hostname and hostname != device_ip:
                            clean_hostname = self._clean_device_name(hostname)
                            result['device_name'] = clean_hostname
                            logging.info(
                                f"[{device_name}] Updated device name from facts: {device_ip} -> {clean_hostname}")

                    logging.info(
                        f"[{device_name}] Successfully collected {method_name} in {method_duration:.2f}s ({data_size} bytes)")

                except Exception as method_error:
                    method_duration = time.time() - method_start_time
                    result['methods_failed'].append({
                        'method': method_name,
                        'duration': method_duration,
                        'error': str(method_error),
                        'success': False
                    })
                    logging.warning(
                        f"[{device_name}] Failed to collect {method_name} in {method_duration:.2f}s: {str(method_error)}")
                    # Continue with next method instead of failing completely

            # Mark as successful if we collected at least some data
            if result['methods_collected']:
                result['success'] = True
                result['credential_used'] = working_credential['name']
                result['credential_source'] = credential_source
                logging.info(
                    f"[{device_name}] Collection completed successfully - {len(result['methods_collected'])} methods succeeded, {len(result['methods_failed'])} failed")
            else:
                logging.error(f"[{device_name}] Collection failed - no methods completed successfully")

        except Exception as e:
            logging.error(f"[{device_name}] Unexpected error during data collection: {str(e)}")
            result['errors'].append(f"Collection error: {str(e)}")

        finally:
            # Always close the connection
            if device_conn:
                try:
                    device_conn.close()
                    logging.debug(f"[{device_name}] Connection closed after all collections")
                except Exception as e:
                    logging.warning(f"[{device_name}] Error closing connection: {str(e)}")

        # End timing for this device
        self.stats.end_device_collection(device_ip)
        if device_ip in self.stats.device_times:
            result['collection_duration'] = self.stats.device_times[device_ip].get('duration', 0)

        return result

    def run_collection(self, scan_file: str):
        """Main collection runner with sequential collection per device"""

        # Start collection timing
        self.stats.start_collection()

        logging.info(f"Starting collection from scan file: {scan_file}")

        # Load scan data
        with open(scan_file, 'r') as f:
            scan_data = json.load(f)

        devices = scan_data.get('devices', {})
        logging.info(f"Loaded {len(devices)} devices from scan file")

        # Filter collectible devices and convert to database-compatible format
        collectible_devices = self.filter_collectible_devices(devices)
        logging.info(f"Found {len(collectible_devices)} collectible network devices")

        if not collectible_devices:
            logging.warning("No collectible devices found")
            return

        # Load credentials using enhanced credential manager
        credentials = self.credential_manager.load_credentials()
        if not credentials:
            logging.error("No credentials configured")
            return

        logging.info(f"Starting collection from {len(collectible_devices)} devices using {self.max_workers} threads")
        logging.info("Each device will be processed sequentially within its own thread")

        # Collect data with one thread per device - SEQUENTIAL COLLECTION APPROACH
        results = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit one task per device - each will do sequential collection
            # Use device IP as key to ensure no duplicates
            submitted_devices = set()
            future_to_device = {}

            for device in collectible_devices:
                device_ip = device['primary_ip']
                device_name = device['device_name']

                # Check for duplicate devices by IP
                if device_ip in submitted_devices:
                    logging.warning(
                        f"Skipping duplicate device {device_name} ({device_ip}) - already submitted for collection")
                    continue

                # Submit the task using the sequential collection method
                future = executor.submit(self.collect_single_device_sequential, device, credentials)
                future_to_device[future] = device
                submitted_devices.add(device_ip)
                logging.info(f"Submitted collection task for {device_name} ({device_ip})")

            logging.info(f"Submitted {len(future_to_device)} unique collection tasks")

            # Process completed tasks
            for future in as_completed(future_to_device):
                device = future_to_device[future]
                try:
                    result = future.result()
                    results.append(result)
                    self.stats.add_result(result)

                    # Save the collected data
                    if result['success']:
                        self.save_device_data(result)
                        logging.info(
                            f"Saved data for {result['device_name']} - {len(result['methods_collected'])} methods")
                    else:
                        logging.warning(f"No data to save for {result['device_name']} - collection failed")

                except Exception as e:
                    logging.error(f"Error processing device {device['device_name']}: {str(e)}")
                    # Create failed result entry
                    failed_result = {
                        'device_ip': device['primary_ip'],
                        'device_name': device.get('device_name', device['primary_ip']),
                        'success': False,
                        'errors': [f"Thread execution error: {str(e)}"],
                        'collection_time': datetime.now().isoformat(),
                        'methods_collected': [],
                        'methods_failed': []
                    }
                    results.append(failed_result)
                    self.stats.add_result(failed_result)

        # End collection timing
        self.stats.end_collection()

        # Generate comprehensive summary
        summary = self.generate_comprehensive_summary(results)

        # Log final summary
        logging.info(f"Collection complete in {summary['collection_summary']['total_runtime_formatted']}")
        logging.info(f"Success: {summary['collection_results']['successful_collections']}, "
                     f"Failed: {summary['collection_results']['failed_collections']}")
        logging.info(f"Average time per device: {summary['performance_metrics']['average_device_time']:.2f}s")

        # Log credential usage summary
        cred_usage = summary.get('credential_usage', {})
        if cred_usage:
            logging.info("Credential usage summary:")
            for cred_name, count in cred_usage.items():
                logging.info(f"  {cred_name}: {count} devices")

        return summary


def main():
    parser = argparse.ArgumentParser(
        description='NAPALM Device Collector with Enhanced Multi-Credential Support and Sequential Collection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Environment Variable Support:
  Credentials can be provided via environment variables which take precedence over config file.

  Variable patterns:
    NAPALM_USERNAME_<name> or NAPALM_USER_<name>
    NAPALM_PASSWORD_<name> or NAPALM_PASS_<name>
    NAPALM_ENABLE_<name> or NAPALM_ENABLE_PASSWORD_<name>
    NAPALM_PRIORITY_<name>

  Where <name> is the credential set name (PRIMARY, BACKUP, etc.)

  Examples:
    export NAPALM_USERNAME_PRIMARY="admin"
    export NAPALM_PASSWORD_PRIMARY="secret123"
    export NAPALM_ENABLE_PRIMARY="enable_secret"
    export NAPALM_PRIORITY_PRIMARY="1"

    export NAPALM_USERNAME_BACKUP="backup_admin"
    export NAPALM_PASSWORD_BACKUP="backup_pass"
    export NAPALM_PRIORITY_BACKUP="2"

Sequential Collection per Device:
  - Each device gets its own thread for collection
  - Within each thread, a single connection is established and reused for all collection methods
  - Credential failover tries each credential set once until connection succeeds
  - All collection methods (get_facts, get_config, etc.) run sequentially using the same connection
  - Connection is closed only after all collections are complete
        ''')
    parser.add_argument('scan_file', nargs='?', help='JSON scan file from SNMP scanner')
    parser.add_argument('--config', default='collector_config.yaml', help='Configuration file')
    parser.add_argument('--workers', type=int, default=10, help='Maximum concurrent workers')
    parser.add_argument('--create-config', action='store_true', help='Create template configuration file')
    parser.add_argument('--env-template', action='store_true',
                        help='Create environment variable template file')
    parser.add_argument('--show-credentials', action='store_true',
                        help='Show loaded credential sources (usernames only)')

    args = parser.parse_args()

    if args.create_config:
        collector = DeviceCollector(args.config, args.workers)
        collector._create_config_template()
        return

    if args.env_template:
        env_template = """#!/bin/bash
# NAPALM Collector Environment Variable Template
# Source this file or add these exports to your shell profile

# Primary credentials (highest priority)
export NAPALM_USERNAME_PRIMARY="admin"
export NAPALM_PASSWORD_PRIMARY="your_password_here"
export NAPALM_ENABLE_PRIMARY="your_enable_password_here"  # Optional
export NAPALM_PRIORITY_PRIMARY="1"

# Backup credentials
export NAPALM_USERNAME_BACKUP="backup_user"
export NAPALM_PASSWORD_BACKUP="backup_password"
export NAPALM_ENABLE_BACKUP=""  # Empty if no enable password
export NAPALM_PRIORITY_BACKUP="2"

# Service account credentials
export NAPALM_USERNAME_SERVICE="svc_napalm"
export NAPALM_PASSWORD_SERVICE="service_account_password"
export NAPALM_PRIORITY_SERVICE="3"

# Alternative variable names also supported:
# NAPALM_USER_* instead of NAPALM_USERNAME_*
# NAPALM_PASS_* instead of NAPALM_PASSWORD_*
# NAPALM_ENABLE_PASSWORD_* instead of NAPALM_ENABLE_*

echo "NAPALM environment variables template created"
"""
        with open('napalm_env_template.sh', 'w') as f:
            f.write(env_template)
        print("Created napalm_env_template.sh")
        return

    if args.show_credentials:
        try:
            collector = DeviceCollector(args.config, args.workers)
            credentials = collector.credential_manager.load_credentials()
            print(f"\nLoaded {len(credentials)} credential sets from environment variables:")
            for cred in sorted(credentials, key=lambda x: x.get('priority', 999)):
                print(f"  {cred['name']}: username={cred['username']}, priority={cred['priority']}")
            print("\nNote: All credentials are loaded from environment variables only.")
        except SystemExit:
            print("No credentials found in environment variables.")
            print("Set NAPALM_USERNAME_<n> and NAPALM_PASSWORD_<n> environment variables.")
        except Exception as e:
            print(f"Error loading credentials: {str(e)}")
        return

    if not args.scan_file:
        parser.print_help()
        print("\nError: scan_file is required unless using --create-config, --env-template, or --show-credentials")
        return

    if not os.path.exists(args.scan_file):
        print(f"Error: Scan file {args.scan_file} not found")
        return

    try:
        collector = DeviceCollector(args.config, args.workers)
        collector.run_collection(args.scan_file)
    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    main()