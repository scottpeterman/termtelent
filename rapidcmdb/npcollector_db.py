#!/usr/bin/env python3
"""
Database-Driven NAPALM Device Collector with Enhanced Environment Variable Support
Collects configuration, inventory, and version information from network devices
using the napalm_cmdb.db database as source instead of JSON scan files
"""

import json
import yaml
import os
import logging
import argparse
import time
import re
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any, Tuple
import napalm
from napalm.base.exceptions import ConnectionException, CommandErrorException


class CredentialManager:
    """Manages credentials from both config files and environment variables"""

    def __init__(self, config: Dict):
        self.config = config

    def load_credentials(self) -> List[Dict]:
        """
        Load credentials from config file and environment variables.
        Environment variables take precedence over config file.

        Environment variable patterns:
        - NAPALM_USER_<n> or NAPALM_USERNAME_<n>
        - NAPALM_PASS_<n> or NAPALM_PASSWORD_<n>
        - NAPALM_ENABLE_<n> or NAPALM_ENABLE_PASSWORD_<n>
        - NAPALM_PRIORITY_<n>

        Where <n> is the credential set name (e.g., PRIMARY, BACKUP, etc.)
        """
        credentials = []

        # First, load credentials from config file
        config_creds = self.config.get('credentials', [])
        for cred in config_creds:
            credentials.append(cred.copy())

        # Then, load/override with environment variables
        env_creds = self._load_env_credentials()

        # Merge environment credentials with config credentials
        credentials = self._merge_credentials(credentials, env_creds)

        # Validate credentials
        validated_creds = self._validate_credentials(credentials)

        if not validated_creds:
            logging.warning("No valid credentials found in config or environment variables")
        else:
            # Don't log actual passwords, just indicate sources
            sources = []
            for cred in validated_creds:
                source = cred.get('_source', 'config')
                sources.append(f"{cred['name']} ({source})")
            logging.info(f"Loaded {len(validated_creds)} credential sets: {', '.join(sources)}")

        return validated_creds

    def _load_env_credentials(self) -> List[Dict]:
        """Load credentials from environment variables"""
        env_creds = {}

        # DEBUG: Log all NAPALM environment variables
        napalm_env_vars = {k: v for k, v in os.environ.items() if k.startswith('NAPALM_')}
        logging.info(f"DEBUG: Found {len(napalm_env_vars)} NAPALM environment variables:")
        for var_name, var_value in napalm_env_vars.items():
            if 'PASSWORD' in var_name:
                logging.info(f"DEBUG: {var_name}=***hidden***")
            else:
                logging.info(f"DEBUG: {var_name}={var_value}")

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

            logging.info(f"DEBUG: Processing {env_var} -> type={cred_type}, name={cred_name}")

            # Initialize credential dict if needed
            if cred_name not in env_creds:
                env_creds[cred_name] = {
                    'name': cred_name.lower(),
                    '_source': 'environment'
                }

            # Map environment variable to credential field
            if cred_type in ['user', 'username']:
                env_creds[cred_name]['username'] = value
                logging.info(f"DEBUG: Set username for {cred_name}: {value}")
            elif cred_type in ['pass', 'password']:
                env_creds[cred_name]['password'] = value
                logging.info(f"DEBUG: Set password for {cred_name}: ***hidden***")
            elif cred_type in ['enable', 'enable_password']:
                env_creds[cred_name]['enable_password'] = value
            elif cred_type == 'priority':
                try:
                    env_creds[cred_name]['priority'] = int(value)
                except ValueError:
                    logging.warning(f"Invalid priority value in {env_var}: {value}")

        logging.info(f"DEBUG: Final env_creds structure: {list(env_creds.keys())}")
        return list(env_creds.values())

    def _merge_credentials(self, config_creds: List[Dict], env_creds: List[Dict]) -> List[Dict]:
        """Merge config and environment credentials, with env taking precedence"""
        merged = {}

        # Add config credentials first
        for cred in config_creds:
            name = cred.get('name', '').lower()
            if name:
                merged[name] = cred.copy()
                merged[name]['_source'] = 'config'

        # Override/add environment credentials
        for cred in env_creds:
            name = cred.get('name', '').lower()
            if name:
                if name in merged:
                    # Update existing credential with environment values
                    merged[name].update(cred)
                    merged[name]['_source'] = 'environment+config'
                else:
                    # Add new environment credential
                    merged[name] = cred

        return list(merged.values())

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
                logging.warning(f"Skipping credential '{name}' - missing username")
                continue

            if not password:
                logging.warning(f"Skipping credential '{name}' - missing password")
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


class DatabaseDeviceCollector:
    """Database-driven collector class for NAPALM-based device data collection with credential caching"""

    def __init__(self, config_file: str = "db_collector_config.yaml", max_workers: int = 10,
                 db_path: str = "napalm_cmdb.db"):
        self.config_file = config_file
        self.max_workers = max_workers
        self.db_path = db_path
        self.config = self._load_config()
        self.capture_dir = Path(self.config.get('capture_directory', 'captures'))
        self.setup_logging()

        # Initialize credential manager
        self.credential_manager = CredentialManager(self.config)

        # Initialize statistics tracking
        self.stats = CollectionStats()

        # Create capture directory if it doesn't exist
        self.capture_dir.mkdir(exist_ok=True)

        # Credential caching - maps device characteristics to working credentials
        self.credential_cache = {}
        self.cache_lock = threading.Lock()  # Thread-safe access to cache

        # NAPALM driver mapping for vendors in your database
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
        """Create a template configuration file with environment variable support"""
        template_config = {
            'capture_directory': 'captures',
            'timeout': 60,
            'max_workers': 10,
            'enhanced_inventory': True,
            'inventory_cli_fallback': True,
            'inventory_parsing': True,
            'detailed_timing': True,
            'performance_metrics': True,
            'database_path': 'napalm_cmdb.db',
            'credential_caching': {
                'enabled': True,
                'cache_by': ['site_code', 'vendor', 'device_role'],
                '_info': 'Devices with matching cache_by fields will share cached credentials'
            },
            'device_ip_resolution': {
                'use_ip_address_field': True,
                'use_device_name': True,
                'use_hostname': True,
                'use_fqdn': True,
                'enable_dns_resolution': False,
                'default_domain': '',
                'ip_lookup_methods': ['dns', 'hosts_file']
            },
            'device_filters': {
                'active_only': True,
                'site_codes': [],
                'device_roles': [],
                'vendors': [],
                'exclude_models': [],
                'include_non_network': False
            },
            'credentials': [
                {
                    'name': 'primary',
                    'username': 'admin',
                    'password': 'password123',
                    'enable_password': '',
                    'priority': 1,
                    '_comment': 'Config file credentials - can be overridden by environment variables'
                }
            ],
            '_credential_environment_variables': {
                '_info': 'Environment variables take precedence over config file credentials',
                '_pattern': 'NAPALM_<TYPE>_<n>',
                '_examples': [
                    'export NAPALM_USERNAME_PRIMARY=admin',
                    'export NAPALM_PASSWORD_PRIMARY=secret123',
                    'export NAPALM_ENABLE_PRIMARY=enable_secret',
                    'export NAPALM_PRIORITY_PRIMARY=1',
                    'export NAPALM_USERNAME_BACKUP=backup_user',
                    'export NAPALM_PASSWORD_BACKUP=backup_pass'
                ],
                '_supported_types': ['USERNAME/USER', 'PASSWORD/PASS', 'ENABLE/ENABLE_PASSWORD', 'PRIORITY']
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
# NAPALM Database Collector Environment Variable Template
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

echo "NAPALM database collector environment variables loaded"
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
                logging.FileHandler('db_collector.log'),
                logging.StreamHandler()
            ]
        )

    def get_database_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def load_devices_from_database(self) -> List[Dict]:
        """Load devices from database with filtering, joining with device_ips table"""
        conn = self.get_database_connection()
        cursor = conn.cursor()

        # Build query with JOIN to device_ips table
        query = """
            SELECT d.*, 
                   COALESCE(
                       mgmt_ip.ip_address,
                       primary_ip.ip_address,
                       any_ip.ip_address
                   ) as ip_address
            FROM devices d
            LEFT JOIN (
                SELECT device_id, ip_address 
                FROM device_ips 
                WHERE ip_type = 'management'
                ORDER BY is_primary DESC, id
            ) mgmt_ip ON d.id = mgmt_ip.device_id
            LEFT JOIN (
                SELECT device_id, ip_address 
                FROM device_ips 
                WHERE is_primary = 1
                ORDER BY id
            ) primary_ip ON d.id = primary_ip.device_id
            LEFT JOIN (
                SELECT device_id, ip_address 
                FROM device_ips 
                WHERE ip_type NOT IN ('virtual', 'hsrp', 'vrrp')
                ORDER BY 
                    CASE ip_type 
                        WHEN 'management' THEN 1
                        WHEN 'loopback' THEN 2
                        WHEN 'vlan' THEN 3
                        ELSE 4
                    END,
                    is_primary DESC, 
                    id
            ) any_ip ON d.id = any_ip.device_id
            WHERE 1=1
        """

        params = []

        # Apply filters from config
        filters = self.config.get('device_filters', {})

        if filters.get('active_only', True):
            query += " AND d.is_active = 1"

        # Only include devices that have at least one IP address
        query += " AND COALESCE(mgmt_ip.ip_address, primary_ip.ip_address, any_ip.ip_address) IS NOT NULL"

        if filters.get('site_codes'):
            placeholders = ','.join(['?' for _ in filters['site_codes']])
            query += f" AND d.site_code IN ({placeholders})"
            params.extend(filters['site_codes'])

        if filters.get('device_roles'):
            placeholders = ','.join(['?' for _ in filters['device_roles']])
            query += f" AND d.device_role IN ({placeholders})"
            params.extend(filters['device_roles'])

        if filters.get('vendors'):
            placeholders = ','.join(['?' for _ in filters['vendors']])
            query += f" AND LOWER(d.vendor) IN ({placeholders})"
            params.extend([v.lower() for v in filters['vendors']])

        if filters.get('exclude_models'):
            placeholders = ','.join(['?' for _ in filters['exclude_models']])
            query += f" AND d.model NOT IN ({placeholders})"
            params.extend(filters['exclude_models'])

        # Filter out non-network devices by default
        non_network_vendors = [
            'apc', 'brother', 'dell', 'hp_printer', 'ion', 'lexmark',
            'linux_embedded', 'samsung', 'unknown', 'xerox', 'zebra', 'bluecat'
        ]

        if not filters.get('include_non_network', False):
            placeholders = ','.join(['?' for _ in non_network_vendors])
            query += f" AND LOWER(d.vendor) NOT IN ({placeholders})"
            params.extend(non_network_vendors)

        query += " ORDER BY d.site_code, d.device_name"

        cursor.execute(query, params)
        devices = []

        for row in cursor.fetchall():
            device = dict(row)
            # Use the joined IP address directly
            device['primary_ip'] = device.get('ip_address')
            if device['primary_ip'] and self._is_valid_ip(device['primary_ip']):
                devices.append(device)
            else:
                logging.warning(f"No valid IP found for device {device['device_name']} "
                                f"(joined IP: {device.get('ip_address', 'None')})")

        conn.close()
        return devices

    def _is_valid_ip(self, ip_string: str) -> bool:
        """Check if string is a valid IP address"""
        try:
            parts = ip_string.split('.')
            if len(parts) != 4:
                return False
            for part in parts:
                if not (0 <= int(part) <= 255):
                    return False
            return True
        except (ValueError, AttributeError):
            return False

    def get_napalm_driver(self, device: Dict) -> Optional[str]:
        """Determine the appropriate NAPALM driver for a device"""
        vendor = device.get('vendor', '').lower()
        model = device.get('model', '').lower()

        # Handle case variations and normalize vendor names
        vendor_normalized = vendor.strip().lower()

        # Check vendor overrides first
        vendor_overrides = self.config.get('vendor_overrides', {})
        for override_key, driver in vendor_overrides.items():
            if override_key.lower() in f"{vendor_normalized}_{model}":
                return driver

        # Cisco specific logic - check model for more specific driver
        if vendor_normalized == 'cisco':
            if any(keyword in model for keyword in ['nx-os', 'nexus', 'n9k', 'n7k', 'n5k', 'n3k']):
                return 'nxos'
            elif any(keyword in model for keyword in ['asa', 'firepower']):
                return 'asa'
            elif any(keyword in model for keyword in ['xe', 'xr']):
                return 'ios'
            else:
                return 'ios'  # Default Cisco to IOS

        # Use the mapping table for other vendors
        driver = self.driver_mapping.get(vendor_normalized)

        # Log when no driver is found for network-looking devices
        if driver is None and vendor_normalized not in [
            'apc', 'brother', 'dell', 'hp_printer', 'ion', 'lexmark',
            'linux_embedded', 'samsung', 'unknown', 'xerox', 'zebra', 'bluecat'
        ]:
            logging.debug(f"No NAPALM driver available for vendor '{vendor}' model '{model}'")

        return driver

    def get_credential_cache_key(self, device: Dict) -> str:
        """Generate a cache key for credential lookup based on device characteristics"""
        cache_config = self.config.get('credential_caching', {})
        cache_by = cache_config.get('cache_by', ['site_code', 'vendor', 'device_role'])

        key_parts = []
        for field in cache_by:
            value = device.get(field, 'unknown')
            if value:
                key_parts.append(f"{field}:{value.lower()}")

        cache_key = "|".join(key_parts) if key_parts else "default"

        # Also consider the NAPALM driver as part of the key
        napalm_driver = self.get_napalm_driver(device)
        if napalm_driver:
            cache_key += f"|driver:{napalm_driver}"

        return cache_key

    def get_cached_credential(self, device: Dict) -> Optional[Dict]:
        """Get cached working credential for similar devices"""
        cache_key = self.get_credential_cache_key(device)

        with self.cache_lock:
            cached_cred = self.credential_cache.get(cache_key)
            if cached_cred:
                logging.info(f"Using cached credential '{cached_cred['name']}' for {device['device_name']} "
                             f"(cache key: {cache_key})")
                return cached_cred
        return None

    def cache_working_credential(self, device: Dict, credential: Dict):
        """Cache a working credential for future use with similar devices"""
        cache_key = self.get_credential_cache_key(device)

        with self.cache_lock:
            self.credential_cache[cache_key] = credential.copy()
            logging.info(f"Cached working credential '{credential['name']}' for cache key: {cache_key}")

    def collect_single_device_sequential(self, device: Dict, credentials: List[Dict]) -> Dict:
        """
        Collect all data from a single device sequentially in one thread.
        CORRECTED: Now produces identical JSON format to npcollector1.py
        """
        device_ip = device['primary_ip']
        device_name = device.get('device_name', device_ip)

        # Start timing for this device
        self.stats.start_device_collection(device_ip)

        # STANDARDIZED result structure (matches JSON collector exactly)
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

        # Prepare credentials to try - SIMPLIFIED to match JSON collector
        credentials_to_try = []

        # Sort credentials by priority (same as JSON collector)
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
                f"[{device_name}] Will collect {len(methods_to_collect)} methods sequentially: {', '.join(methods_to_collect)}")

            # Execute each collection method sequentially
            for method_name in methods_to_collect:
                method_start_time = time.time()
                try:
                    logging.info(f"[{device_name}] Collecting {method_name}")

                    # Get the method from the device connection
                    method_func = getattr(device_conn, method_name, None)
                    if not method_func:
                        raise AttributeError(f"Method {method_name} not available for driver {napalm_driver}")

                    # Execute the method and get RAW NAPALM data
                    method_data = method_func()

                    # Calculate timing and data size
                    method_duration = time.time() - method_start_time
                    data_size = len(json.dumps(method_data, default=str)) if method_data else 0

                    # Store the RAW NAPALM result without modification
                    result['data'][method_name] = method_data

                    # Track successful method
                    result['methods_collected'].append({
                        'method': method_name,
                        'duration': method_duration,
                        'data_size': data_size,
                        'success': True
                    })

                    # Update device name after collecting facts (same as JSON collector)
                    if method_name == 'get_facts' and method_data:
                        hostname = method_data.get('hostname', method_data.get('fqdn', device_ip))
                        if hostname and hostname != device_ip:
                            clean_hostname = self._clean_device_name(hostname)
                            result['device_name'] = clean_hostname
                            device_name = clean_hostname  # Update for logging
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
                    logging.debug(f"[{device_name}] Connection closed")
                except Exception as e:
                    logging.warning(f"[{device_name}] Error closing connection: {str(e)}")

        # End timing for this device
        self.stats.end_device_collection(device_ip)
        if device_ip in self.stats.device_times:
            result['collection_duration'] = self.stats.device_times[device_ip].get('duration', 0)

        return result
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
        """Save collected device data to files in JSON-compatible format"""
        if not device_result['success']:
            logging.error(f"Skipping save for {device_result['device_name']} - collection failed")
            return

        device_name = device_result['device_name']
        device_ip = device_result['device_ip']

        # Clean device name for filesystem safety
        safe_device_name = self._clean_device_name(device_name)

        device_dir = self.capture_dir / safe_device_name
        device_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save complete result as JSON (compatible with loader)
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

    def apply_runtime_filters(self, devices: List[Dict], filter_args: Dict) -> List[Dict]:
        """Apply runtime filters to devices list"""
        filtered_devices = devices[:]
        original_count = len(filtered_devices)

        # Apply each filter type
        if filter_args.get('name'):
            name_filters = [f.lower() for f in filter_args['name']]
            filtered_devices = [d for d in filtered_devices if
                                any(name_filter in (d.get('device_name') or '').lower()
                                    for name_filter in name_filters)]

        if filter_args.get('site'):
            site_filters = [f.lower() for f in filter_args['site']]
            filtered_devices = [d for d in filtered_devices if
                                any(site_filter in (d.get('site_code') or '').lower()
                                    for site_filter in site_filters)]

        if filter_args.get('vendor'):
            vendor_filters = [f.lower() for f in filter_args['vendor']]
            filtered_devices = [d for d in filtered_devices if
                                any(vendor_filter in (d.get('vendor') or '').lower()
                                    for vendor_filter in vendor_filters)]

        if filter_args.get('role'):
            role_filters = [f.lower() for f in filter_args['role']]
            filtered_devices = [d for d in filtered_devices if
                                any(role_filter in (d.get('device_role') or '').lower()
                                    for role_filter in role_filters)]

        if filter_args.get('model'):
            model_filters = [f.lower() for f in filter_args['model']]
            filtered_devices = [d for d in filtered_devices if
                                any(model_filter in (d.get('model') or '').lower()
                                    for model_filter in model_filters)]

        if filter_args.get('ip'):
            ip_filters = filter_args['ip']
            filtered_devices = [d for d in filtered_devices if
                                any(ip_filter in (d.get('primary_ip') or '')
                                    for ip_filter in ip_filters)]

        # Legacy support for the old --filter option
        if filter_args.get('legacy'):
            legacy_filters = [f.lower() for f in filter_args['legacy']]
            filtered_devices = [d for d in filtered_devices if
                                any(legacy_filter in (d.get('device_name') or '').lower() or
                                    legacy_filter in (d.get('site_code') or '').lower() or
                                    legacy_filter in (d.get('vendor') or '').lower() or
                                    legacy_filter in (d.get('device_role') or '').lower() or
                                    legacy_filter in (d.get('model') or '').lower()
                                    for legacy_filter in legacy_filters)]

        # Log filter results
        if filtered_devices != devices:
            active_filters = [f"{k}={v}" for k, v in filter_args.items() if v]
            logging.info(f"Filtered to {len(filtered_devices)} devices (from {original_count}) "
                         f"using filters: {', '.join(active_filters)}")

        return filtered_devices

    def generate_json_compatible_summary(self, results: List[Dict], devices: List[Dict]) -> Dict:
        """Generate a summary compatible with JSON scan file format"""

        # Create devices dict in the format expected by the loader
        devices_dict = {}
        for device in devices:
            device_dict = {
                'primary_ip': device['primary_ip'],
                'device_name': device['device_name'],
                'vendor': device.get('vendor', 'unknown'),
                'model': device.get('model', 'unknown'),
                'serial_number': device.get('serial_number', ''),
                'site_code': device.get('site_code', ''),
                'device_role': device.get('device_role', ''),
                'device_type': 'network',
                'sys_name': device.get('hostname', device['device_name']),
                'sys_descr': f"{device.get('vendor', '')} {device.get('model', '')}".strip(),
                'database_id': device['id']
            }
            devices_dict[device['primary_ip']] = device_dict

        # Calculate summary statistics
        total_devices = len(results)
        successful = sum(1 for r in results if r['success'])
        failed = total_devices - successful

        # Create JSON-compatible summary
        summary = {
            'scan_metadata': {
                'scan_type': 'database_napalm_collection',
                'scan_time': datetime.now().isoformat(),
                'total_runtime_seconds': self.stats.get_total_runtime(),
                'database_path': self.db_path,
                'config_file': self.config_file
            },
            'devices': devices_dict,
            'collection_summary': {
                'total_devices': total_devices,
                'successful_collections': successful,
                'failed_collections': failed,
                'success_rate': (successful / total_devices * 100) if total_devices > 0 else 0,
                'average_device_time': self.stats.get_average_device_time(),
                'max_workers': self.max_workers
            },
            'collection_results': results
        }

        return summary

    def print_credential_cache_stats(self):
        """Print statistics about credential cache usage"""
        with self.cache_lock:
            if self.credential_cache:
                logging.info(f"Credential cache contains {len(self.credential_cache)} entries:")
                for cache_key, cred in self.credential_cache.items():
                    logging.info(f"  {cache_key} -> {cred['name']}")
            else:
                logging.info("Credential cache is empty")

    def run_collection(self, filter_args: Dict = None):
        """Main collection runner - one thread per device, sequential collection within each thread"""

        # Start collection timing
        self.stats.start_collection()

        logging.info(f"Starting database-driven collection from: {self.db_path}")

        # Load devices from database
        devices = self.load_devices_from_database()
        logging.info(f"Loaded {len(devices)} devices from database")

        # Apply runtime filters if provided
        if filter_args:
            devices = self.apply_runtime_filters(devices, filter_args)

        if not devices:
            logging.warning("No devices found to collect")
            return

        # Load credentials using enhanced credential manager
        credentials = self.credential_manager.load_credentials()
        if not credentials:
            logging.error("No credentials configured")
            return

        logging.info(f"Starting collection from {len(devices)} devices using {self.max_workers} threads")
        logging.info("Each device will be processed sequentially within its own thread")

        # Collect data with one thread per device
        results = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit one task per device - each will do sequential collection
            # Use device IP as key to ensure no duplicates
            submitted_devices = set()
            future_to_device = {}

            for device in devices:
                device_ip = device['primary_ip']
                device_name = device['device_name']

                # Check for duplicate devices by IP
                if device_ip in submitted_devices:
                    logging.warning(
                        f"Skipping duplicate device {device_name} ({device_ip}) - already submitted for collection")
                    continue

                # Submit the task
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
                        'device_name': device['device_name'],
                        'database_id': device['id'],
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

        # Generate JSON-compatible summary
        summary = self.generate_json_compatible_summary(results, devices)

        # Log final summary with credential cache stats
        self.print_credential_cache_stats()
        logging.info(f"Collection complete in {timedelta(seconds=int(self.stats.get_total_runtime()))}")
        logging.info(f"Success: {summary['collection_summary']['successful_collections']}, "
                     f"Failed: {summary['collection_summary']['failed_collections']}")
        logging.info(f"Average time per device: {summary['collection_summary']['average_device_time']:.2f}s")

        return summary


def main():
    parser = argparse.ArgumentParser(
        description='Database-Driven NAPALM Device Collector with Environment Variable Support',
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

Filter Examples:
  # Single filter (legacy style)
  python db_collector.py --filter cisco

  # Multiple filters by type
  python db_collector.py --site FRC USC --vendor cisco arista
  python db_collector.py --site NYC --vendor cisco --role core access
  python db_collector.py --name switch01 router --site FRC
  python db_collector.py --vendor cisco --model catalyst nexus
  python db_collector.py --ip 192.168.1 10.1.1

  # Complex multi-filter example
  python db_collector.py --site FRC USC --vendor cisco --role core --model catalyst

Filter Types:
  --name      : Filter by device name (supports multiple values)
  --site      : Filter by site code (supports multiple values) 
  --vendor    : Filter by vendor (supports multiple values)
  --role      : Filter by device role (supports multiple values)
  --model     : Filter by model (supports multiple values)
  --ip        : Filter by IP address substring (supports multiple values)
  --filter    : Legacy single filter (searches all fields)
        ''')

    parser.add_argument('--config', default='db_collector_config.yaml', help='Configuration file')
    parser.add_argument('--database', default='napalm_cmdb.db', help='Database path')
    parser.add_argument('--workers', type=int, default=10, help='Maximum concurrent workers')

    # New specific filter options
    parser.add_argument('--name', nargs='+', help='Filter by device name (supports multiple values)')
    parser.add_argument('--site', nargs='+', help='Filter by site code (supports multiple values)')
    parser.add_argument('--vendor', nargs='+', help='Filter by vendor (supports multiple values)')
    parser.add_argument('--role', nargs='+', help='Filter by device role (supports multiple values)')
    parser.add_argument('--model', nargs='+', help='Filter by model (supports multiple values)')
    parser.add_argument('--ip', nargs='+', help='Filter by IP address substring (supports multiple values)')

    # Legacy filter option (backward compatibility)
    parser.add_argument('--filter', nargs='+', help='Legacy filter - searches all fields (case-insensitive)')

    parser.add_argument('--create-config', action='store_true', help='Create template configuration file')
    parser.add_argument('--env-template', action='store_true',
                        help='Create environment variable template file')
    parser.add_argument('--show-credentials', action='store_true',
                        help='Show loaded credential sources (usernames only)')
    parser.add_argument('--list-devices', action='store_true', help='List available devices in database')

    args = parser.parse_args()

    if args.create_config:
        collector = DatabaseDeviceCollector(args.config, args.workers, args.database)
        collector._create_config_template()
        return

    if args.env_template:
        env_template = """#!/bin/bash
# NAPALM Database Collector Environment Variable Template
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

echo "NAPALM database collector environment variables template created"
"""
        with open('napalm_db_env_template.sh', 'w') as f:
            f.write(env_template)
        print("Created napalm_db_env_template.sh")
        return

    if args.show_credentials:
        try:
            collector = DatabaseDeviceCollector(args.config, args.workers, args.database)
            credentials = collector.credential_manager.load_credentials()
            print(f"\nLoaded {len(credentials)} credential sets:")
            for cred in credentials:
                source = cred.get('_source', 'config')
                print(f"  {cred['name']}: username={cred['username']}, source={source}, priority={cred['priority']}")
        except Exception as e:
            print(f"Error loading credentials: {str(e)}")
        return

    if not os.path.exists(args.database):
        print(f"Error: Database file {args.database} not found")
        return

    try:
        collector = DatabaseDeviceCollector(args.config, args.workers, args.database)

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

        collector.run_collection(filter_args if filter_args else None)

    except Exception as e:
        print(f"Error: {str(e)}")
        raise


if __name__ == "__main__":
    main()