#!/usr/bin/env python3
"""
NAPALM CMDB Database Manager
Handles insertion and querying of NAPALM collection data in SQLite database
Uses the new schema with proper constraints and data integrity
"""

import sqlite3
import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import re


class NapalmCMDB:
    """Database manager for NAPALM network device data"""

    def __init__(self, db_path: str = "napalm_cmdb.db", schema_path: str = "cmdb.sql"):
        self.db_path = db_path
        self.schema_path = schema_path
        self.connection = None
        self.setup_database()

    def setup_database(self):
        """Initialize database connection and create tables if needed"""
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row  # Enable column access by name

        # Enable foreign key constraints
        self.connection.execute("PRAGMA foreign_keys = ON")

        # Load and execute schema if tables don't exist
        cursor = self.connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='devices'")
        if not cursor.fetchone():
            self.create_schema()

    def create_schema(self):
        """Create database schema from SQL file"""
        logging.info("Creating database schema...")

        # Try to load from schema file first
        schema_path = Path(self.schema_path)
        if schema_path.exists():
            with open(schema_path, 'r') as f:
                schema_sql = f.read()

            # Execute the schema
            cursor = self.connection.cursor()
            try:
                cursor.executescript(schema_sql)
                self.connection.commit()
                logging.info("Database schema created successfully from file")
                return
            except sqlite3.Error as e:
                logging.error(f"Error executing schema from file: {e}")
                # Fall back to embedded schema

        # Fallback to embedded schema if file doesn't exist
        logging.warning(f"Schema file {self.schema_path} not found, using embedded schema")
        self._create_embedded_schema()

    def _create_embedded_schema(self):
        """Create basic schema if SQL file is not available"""
        schema_statements = [
            # Enable pragmas
            "PRAGMA foreign_keys = ON",
            "PRAGMA journal_mode = WAL",

            # Main devices table with proper constraints
            """CREATE TABLE devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_key TEXT NOT NULL UNIQUE,
                device_name TEXT NOT NULL UNIQUE,
                hostname TEXT,
                fqdn TEXT,
                vendor TEXT NOT NULL,
                model TEXT,
                serial_number TEXT NOT NULL,
                os_version TEXT,
                uptime REAL,
                first_discovered DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_updated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                site_code TEXT NOT NULL,
                device_role TEXT NOT NULL,
                notes TEXT,

                CONSTRAINT check_vendor_not_empty CHECK (TRIM(vendor) != ''),
                CONSTRAINT check_serial_not_empty CHECK (TRIM(serial_number) != ''),
                CONSTRAINT check_device_name_not_empty CHECK (TRIM(device_name) != ''),
                CONSTRAINT check_device_role_valid CHECK (device_role IN ('core', 'access', 'distribution', 'firewall', 'router', 'switch', 'wireless', 'load_balancer', 'unknown')),
                CONSTRAINT check_uptime_positive CHECK (uptime IS NULL OR uptime >= 0)
            )""",

            # Device IP addresses table
            """CREATE TABLE device_ips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                ip_address TEXT NOT NULL UNIQUE,
                ip_type TEXT NOT NULL,
                interface_name TEXT,
                subnet_mask TEXT,
                vlan_id INTEGER,
                is_primary BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                CONSTRAINT check_ip_type_valid CHECK (ip_type IN ('management', 'loopback', 'vlan', 'secondary', 'virtual', 'hsrp', 'vrrp')),
                CONSTRAINT check_vlan_id_valid CHECK (vlan_id IS NULL OR (vlan_id >= 1 AND vlan_id <= 4094))
            )""",

            # Collection runs tracking
            """CREATE TABLE collection_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                collection_ip TEXT NOT NULL,
                collection_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                success BOOLEAN NOT NULL,
                credential_used TEXT,
                errors TEXT,
                collection_duration REAL,
                methods_collected TEXT,
                napalm_driver TEXT,
                collector_version TEXT,

                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                CONSTRAINT check_collection_duration CHECK (collection_duration IS NULL OR collection_duration >= 0)
            )""",

            # Other essential tables (simplified for embedded version)
            """CREATE TABLE interfaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                collection_run_id INTEGER NOT NULL,
                interface_name TEXT NOT NULL,
                interface_type TEXT NOT NULL,
                admin_status TEXT NOT NULL,
                oper_status TEXT NOT NULL,
                description TEXT,
                mac_address TEXT,
                speed REAL,
                mtu INTEGER,
                last_flapped REAL,
                duplex TEXT,
                vlan_id INTEGER,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,

                CONSTRAINT check_interface_name_not_empty CHECK (TRIM(interface_name) != ''),
                CONSTRAINT check_admin_status CHECK (admin_status IN ('enabled', 'disabled')),
                CONSTRAINT check_oper_status CHECK (oper_status IN ('up', 'down', 'testing'))
            )""",

            # LLDP neighbors table
            """CREATE TABLE lldp_neighbors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                collection_run_id INTEGER NOT NULL,
                local_interface TEXT NOT NULL,
                remote_hostname TEXT,
                remote_port TEXT,
                remote_system_description TEXT,
                remote_chassis_id TEXT,
                remote_port_id TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,

                CONSTRAINT check_local_interface_not_empty CHECK (TRIM(local_interface) != '')
            )""",

            # ARP entries table
            """CREATE TABLE arp_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                collection_run_id INTEGER NOT NULL,
                interface_name TEXT,
                ip_address TEXT NOT NULL,
                mac_address TEXT NOT NULL,
                age REAL,
                entry_type TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,

                CONSTRAINT check_age_positive CHECK (age IS NULL OR age >= 0)
            )""",

            # MAC address table
            """CREATE TABLE mac_address_table (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                collection_run_id INTEGER NOT NULL,
                mac_address TEXT NOT NULL,
                interface_name TEXT,
                vlan_id INTEGER,
                entry_type TEXT NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                moves INTEGER DEFAULT 0,
                last_move REAL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,

                CONSTRAINT check_vlan_id_table CHECK (vlan_id IS NULL OR (vlan_id >= 1 AND vlan_id <= 4094)),
                CONSTRAINT check_moves_positive CHECK (moves >= 0)
            )""",

            # Environment data table
            """CREATE TABLE environment_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                collection_run_id INTEGER NOT NULL,
                cpu_usage REAL,
                memory_used INTEGER,
                memory_available INTEGER,
                memory_total INTEGER,
                temperature_sensors TEXT,
                power_supplies TEXT,
                fans TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,

                CONSTRAINT check_cpu_usage CHECK (cpu_usage IS NULL OR (cpu_usage >= 0 AND cpu_usage <= 100))
            )""",

            # Device configurations table
            """CREATE TABLE device_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                collection_run_id INTEGER NOT NULL,
                config_type TEXT NOT NULL,
                config_content TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                line_count INTEGER NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,

                CONSTRAINT check_config_type CHECK (config_type IN ('running', 'startup', 'candidate')),
                CONSTRAINT check_size_positive CHECK (size_bytes > 0),
                CONSTRAINT check_lines_positive CHECK (line_count > 0)
            )""",

            # Device users table
            """CREATE TABLE device_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                collection_run_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                privilege_level INTEGER,
                password_hash TEXT,
                ssh_keys TEXT,
                user_type TEXT,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,

                CONSTRAINT check_username_not_empty CHECK (TRIM(username) != ''),
                CONSTRAINT check_privilege_level CHECK (privilege_level IS NULL OR (privilege_level >= 0 AND privilege_level <= 15))
            )""",

            # VLAN database
            """CREATE TABLE vlans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                collection_run_id INTEGER NOT NULL,
                vlan_id INTEGER NOT NULL,
                vlan_name TEXT,
                status TEXT NOT NULL,
                interfaces TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,

                CONSTRAINT check_vlan_id_range CHECK (vlan_id >= 1 AND vlan_id <= 4094),
                CONSTRAINT check_vlan_status CHECK (status IN ('active', 'suspended', 'shutdown'))
            )""",

            # Routing table entries
            """CREATE TABLE routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                collection_run_id INTEGER NOT NULL,
                destination_network TEXT NOT NULL,
                prefix_length INTEGER NOT NULL,
                next_hop TEXT,
                interface_name TEXT,
                protocol TEXT NOT NULL,
                metric INTEGER,
                administrative_distance INTEGER,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,

                CONSTRAINT check_prefix_length_route CHECK (prefix_length >= 0 AND prefix_length <= 128),
                CONSTRAINT check_metric_positive CHECK (metric IS NULL OR metric >= 0),
                CONSTRAINT check_admin_distance CHECK (administrative_distance IS NULL OR (administrative_distance >= 0 AND administrative_distance <= 255))
            )""",

            # Create essential indexes
            "CREATE INDEX idx_devices_device_key ON devices(device_key)",
            "CREATE INDEX idx_devices_device_name ON devices(device_name)",
            "CREATE INDEX idx_devices_serial ON devices(vendor, serial_number)",
            "CREATE INDEX idx_device_ips_device ON device_ips(device_id)",
            "CREATE INDEX idx_device_ips_address ON device_ips(ip_address)",
            "CREATE INDEX idx_collection_device_time ON collection_runs(device_id, collection_time DESC)",

            # Create trigger for single primary IP
            """CREATE TRIGGER enforce_single_primary_ip
                BEFORE INSERT ON device_ips
                FOR EACH ROW
                WHEN NEW.is_primary = 1
            BEGIN
                UPDATE device_ips SET is_primary = 0 
                WHERE device_id = NEW.device_id AND is_primary = 1;
            END""",

            # Create trigger to update device timestamp
            """CREATE TRIGGER update_device_timestamp
                AFTER INSERT ON collection_runs
                FOR EACH ROW
            BEGIN
                UPDATE devices
                SET last_updated = NEW.collection_time
                WHERE id = NEW.device_id;
            END"""
        ]

        cursor = self.connection.cursor()
        for statement in schema_statements:
            try:
                cursor.execute(statement)
                logging.debug(f"Executed: {statement[:50]}...")
            except sqlite3.Error as e:
                logging.error(f"Error executing statement: {e}")
                logging.error(f"Statement: {statement}")
                raise

        self.connection.commit()
        logging.info("Embedded database schema created successfully")

    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()

    def generate_device_key(self, vendor: str, serial_number: str, model: str) -> str:
        """Generate a stable device key from vendor, serial, and model"""
        key_string = f"{vendor}|{serial_number}|{model}".upper()
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]

    def extract_site_code(self, device_name: str) -> str:
        """Extract site code from device name"""
        # Example: frc-c03h2-swl-01 -> FRC
        parts = device_name.split('-')
        if parts:
            site = parts[0].upper()
            # Validate site code format (3+ uppercase letters)
            if len(site) >= 3 and site.isalpha():
                return site
        return 'UNK'  # Default for unknown

    def determine_device_role(self, device_name: str, interfaces: Dict) -> str:
        """Determine device role based on naming convention and interfaces"""
        name_lower = device_name.lower()

        # Role mapping from naming convention
        role_keywords = {
            'core': ['core', '-c-', 'c01', 'c02'],
            'access': ['swl', 'access', 'acc'],
            'distribution': ['dist', 'distribution', 'd01', 'd02'],
            'firewall': ['fw', 'firewall', 'asa', 'pix'],
            'router': ['rtr', 'router', 'r01', 'r02'],
            'switch': ['sw', 'switch']
        }

        for role, keywords in role_keywords.items():
            if any(keyword in name_lower for keyword in keywords):
                return role

        # Analyze interfaces to determine role if naming doesn't match
        if interfaces:
            interface_count = len([i for i in interfaces.keys()
                                   if
                                   any(itype in i for itype in ['GigabitEthernet', 'TenGigabitEthernet', 'Ethernet'])])
            if interface_count >= 24:
                return 'access'
            elif interface_count >= 12:
                return 'distribution'

        return 'unknown'

    def insert_or_update_device(self, napalm_data: Dict) -> int:
        """Insert or update device record and return device ID"""
        facts = napalm_data['data'].get('get_facts', {})
        interfaces = napalm_data['data'].get('get_interfaces', {})

        device_name = napalm_data['device_name']
        collection_ip = napalm_data['device_ip']  # The IP used for collection

        # Extract device information
        vendor = facts.get('vendor', 'Unknown')
        serial_number = facts.get('serial_number', 'Unknown')
        model = facts.get('model', 'Unknown')

        # Generate stable device key
        device_key = self.generate_device_key(vendor, serial_number, model)

        site_code = self.extract_site_code(device_name)
        device_role = self.determine_device_role(device_name, interfaces)

        cursor = self.connection.cursor()

        try:
            # Check if device exists by device_key (most reliable) or device_name
            cursor.execute("""
                SELECT id FROM devices 
                WHERE device_key = ? OR device_name = ?
            """, (device_key, device_name))
            existing = cursor.fetchone()

            if existing:
                # Update existing device
                device_id = existing[0]
                cursor.execute("""
                    UPDATE devices SET
                        device_key = ?, device_name = ?, hostname = ?, fqdn = ?, 
                        vendor = ?, model = ?, serial_number = ?, os_version = ?, 
                        uptime = ?, last_updated = ?, site_code = ?, device_role = ?
                    WHERE id = ?
                """, (
                    device_key, device_name, facts.get('hostname'), facts.get('fqdn'),
                    vendor, model, serial_number, facts.get('os_version'),
                    facts.get('uptime'), datetime.now(), site_code, device_role, device_id
                ))
                logging.info(f"Updated existing device: {device_name} (ID: {device_id})")
            else:
                # Insert new device
                cursor.execute("""
                    INSERT INTO devices (
                        device_key, device_name, hostname, fqdn, vendor, model,
                        serial_number, os_version, uptime, site_code, device_role
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    device_key, device_name, facts.get('hostname'), facts.get('fqdn'),
                    vendor, model, serial_number, facts.get('os_version'),
                    facts.get('uptime'), site_code, device_role
                ))
                device_id = cursor.lastrowid
                logging.info(f"Inserted new device: {device_name} (ID: {device_id})")

            # Handle device IP addresses
            self._update_device_ips(device_id, collection_ip, napalm_data)

            self.connection.commit()
            return device_id

        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: devices.device_name" in str(e):
                logging.error(f"Device name '{device_name}' already exists in database")
                raise ValueError(f"Device name '{device_name}' already exists")
            else:
                logging.error(f"Database integrity error: {e}")
                raise
        except Exception as e:
            logging.error(f"Error inserting/updating device {device_name}: {e}")
            self.connection.rollback()
            raise

    def _update_device_ips(self, device_id: int, collection_ip: str, napalm_data: Dict):
        """Update device IP addresses"""
        cursor = self.connection.cursor()

        # Always ensure the collection IP is recorded
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO device_ips (
                    device_id, ip_address, ip_type, is_primary, updated_at
                ) VALUES (?, ?, 'management', 1, ?)
            """, (device_id, collection_ip, datetime.now()))
        except sqlite3.IntegrityError:
            # IP might be used by another device - this is a data issue to investigate
            logging.warning(f"IP address {collection_ip} already exists for another device")

        # Add interface IPs from interface data
        interfaces_ip = napalm_data['data'].get('get_interfaces_ip', {})
        for interface_name, ip_data in interfaces_ip.items():
            for protocol, addresses in ip_data.items():
                for ip_addr, details in addresses.items():
                    if ip_addr != collection_ip:  # Don't duplicate the management IP
                        try:
                            cursor.execute("""
                                INSERT OR IGNORE INTO device_ips (
                                    device_id, ip_address, ip_type, interface_name, 
                                    subnet_mask, is_primary, updated_at
                                ) VALUES (?, ?, 'vlan', ?, ?, 0, ?)
                            """, (
                                device_id, ip_addr, interface_name,
                                str(details.get('prefix_length', '')), datetime.now()
                            ))
                        except sqlite3.IntegrityError:
                            # IP already exists, skip
                            continue

    def insert_collection_run(self, device_id: int, napalm_data: Dict) -> int:
        """Insert collection run record and return run ID"""
        cursor = self.connection.cursor()

        collection_time = datetime.fromisoformat(napalm_data['collection_time'])
        methods_collected = list(napalm_data['data'].keys())
        errors = napalm_data.get('errors', [])
        collection_ip = napalm_data['device_ip']

        cursor.execute("""
            INSERT INTO collection_runs (
                device_id, collection_ip, collection_time, success, credential_used,
                errors, methods_collected, napalm_driver, collector_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            device_id, collection_ip, collection_time, napalm_data['success'],
            napalm_data.get('credential_used'), json.dumps(errors),
            json.dumps(methods_collected), napalm_data.get('napalm_driver'),
            napalm_data.get('collector_version', '1.0')
        ))

        run_id = cursor.lastrowid
        self.connection.commit()
        return run_id

    def insert_interfaces(self, device_id: int, run_id: int, interfaces_data: Dict, interfaces_ip_data: Dict):
        """Insert interface data"""
        cursor = self.connection.cursor()

        for interface_name, interface_info in interfaces_data.items():
            # Validate interface name
            if not interface_name or not interface_name.strip():
                continue

            # Determine interface type
            interface_type = self._determine_interface_type(interface_name)

            # Convert boolean values to proper format
            admin_status = 'enabled' if interface_info.get('is_enabled') else 'disabled'
            oper_status = 'up' if interface_info.get('is_up') else 'down'

            # Validate and clean numeric values
            speed = interface_info.get('speed')
            if speed is not None:
                try:
                    speed = float(speed)
                    if speed <= 0:
                        speed = None
                except (ValueError, TypeError):
                    speed = None

            mtu = interface_info.get('mtu')
            if mtu is not None:
                try:
                    mtu = int(mtu)
                    if mtu < 64 or mtu > 65535:
                        mtu = None
                except (ValueError, TypeError):
                    mtu = None

            last_flapped = interface_info.get('last_flapped')
            if last_flapped is not None:
                try:
                    last_flapped = float(last_flapped)
                    if last_flapped < 0:
                        last_flapped = None
                except (ValueError, TypeError):
                    last_flapped = None

            # Validate duplex
            duplex = interface_info.get('duplex')
            if duplex and duplex not in ['full', 'half', 'auto']:
                duplex = None

            cursor.execute("""
                INSERT INTO interfaces (
                    device_id, collection_run_id, interface_name, interface_type,
                    admin_status, oper_status, description, mac_address, speed, mtu,
                    last_flapped, duplex, vlan_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                device_id, run_id, interface_name, interface_type,
                admin_status, oper_status, interface_info.get('description'),
                self._normalize_mac_address(interface_info.get('mac_address')),
                speed, mtu, last_flapped, duplex, None  # VLAN ID extraction could be added here
            ))

        self.connection.commit()

    def _normalize_mac_address(self, mac_address: str) -> Optional[str]:
        """Normalize MAC address to XX:XX:XX:XX:XX:XX format"""
        if not mac_address:
            return None

        # Remove common separators and convert to uppercase
        mac = re.sub(r'[:\-\.]', '', mac_address.upper())

        # Validate length
        if len(mac) != 12:
            return None

        # Format as XX:XX:XX:XX:XX:XX
        return ':'.join([mac[i:i + 2] for i in range(0, 12, 2)])

    def _determine_interface_type(self, interface_name: str) -> str:
        """Determine interface type from name"""
        name_lower = interface_name.lower()

        type_mapping = {
            'vlan': 'VLAN',
            'loopback': 'Loopback',
            'tengigabit': 'Physical',
            'gigabit': 'Physical',
            'fastethernet': 'Physical',
            'ethernet': 'Physical',
            'tunnel': 'Tunnel',
            'port-channel': 'PortChannel',
            'po': 'PortChannel',
            'mgmt': 'Management',
            'management': 'Management'
        }

        for keyword, interface_type in type_mapping.items():
            if keyword in name_lower:
                return interface_type

        return 'Physical'  # Default

    def insert_lldp_neighbors(self, device_id: int, run_id: int, lldp_data: Dict):
        """Insert LLDP neighbor data"""
        cursor = self.connection.cursor()

        for local_interface, neighbors in lldp_data.items():
            for neighbor in neighbors:
                cursor.execute("""
                    INSERT INTO lldp_neighbors (
                        device_id, collection_run_id, local_interface,
                        remote_hostname, remote_port, remote_system_description,
                        remote_chassis_id, remote_port_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    device_id, run_id, local_interface,
                    neighbor.get('hostname'),
                    neighbor.get('port'),
                    neighbor.get('system_description'),
                    neighbor.get('chassis_id'),
                    neighbor.get('port_id')
                ))

        self.connection.commit()

    def insert_arp_table(self, device_id: int, run_id: int, arp_data: List):
        """Insert ARP table data"""
        cursor = self.connection.cursor()

        for entry in arp_data:
            # Validate and clean age value
            age = entry.get('age')
            if age is not None:
                try:
                    age = float(age)
                    if age < 0:
                        age = None  # Ignore negative ages
                except (ValueError, TypeError):
                    age = None

            # Skip entries with invalid IP or MAC
            ip_addr = entry.get('ip')
            mac_addr = self._normalize_mac_address(entry.get('mac'))

            if not ip_addr or not mac_addr:
                continue

            cursor.execute("""
                INSERT INTO arp_entries (
                    device_id, collection_run_id, interface_name,
                    ip_address, mac_address, age, entry_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                device_id, run_id,
                entry.get('interface'),
                ip_addr,
                mac_addr,
                age,
                'dynamic'  # Default to dynamic if not specified
            ))

        self.connection.commit()

    def insert_mac_address_table(self, device_id: int, run_id: int, mac_data: List):
        """Insert MAC address table data"""
        cursor = self.connection.cursor()

        for entry in mac_data:
            # Validate and clean VLAN ID
            vlan_id = entry.get('vlan')
            if vlan_id is not None:
                try:
                    vlan_id = int(vlan_id)
                    # Skip invalid VLAN IDs (must be 1-4094)
                    if vlan_id < 1 or vlan_id > 4094:
                        vlan_id = None
                except (ValueError, TypeError):
                    vlan_id = None

            # Skip entries with invalid MAC addresses
            mac_addr = self._normalize_mac_address(entry.get('mac'))
            if not mac_addr:
                continue

            entry_type = 'static' if entry.get('static') else 'dynamic'

            # Validate moves count
            moves = entry.get('moves', 0)
            try:
                moves = int(moves)
                if moves < 0:
                    moves = 0
            except (ValueError, TypeError):
                moves = 0

            # Validate last_move timestamp
            last_move = entry.get('last_move')
            if last_move is not None:
                try:
                    last_move = float(last_move)
                    if last_move < 0:
                        last_move = None
                except (ValueError, TypeError):
                    last_move = None

            cursor.execute("""
                INSERT INTO mac_address_table (
                    device_id, collection_run_id, mac_address, interface_name,
                    vlan_id, entry_type, is_active, moves, last_move
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                device_id, run_id,
                mac_addr,
                entry.get('interface'),
                vlan_id,
                entry_type,
                entry.get('active', True),
                moves,
                last_move
            ))

        self.connection.commit()

    def insert_environment_data(self, device_id: int, run_id: int, env_data: Dict):
        """Insert environment monitoring data"""
        cursor = self.connection.cursor()

        cpu_usage = None
        memory_used = None
        memory_available = None
        memory_total = None

        # Extract CPU usage (take first CPU if multiple)
        cpu_data = env_data.get('cpu', {})
        if cpu_data:
            cpu_usage = list(cpu_data.values())[0].get('%usage')

        # Extract memory information
        memory_data = env_data.get('memory', {})
        if memory_data:
            memory_used = memory_data.get('used_ram')
            memory_available = memory_data.get('available_ram')
            if memory_used and memory_available:
                memory_total = memory_used + memory_available

        cursor.execute("""
            INSERT INTO environment_data (
                device_id, collection_run_id, cpu_usage, memory_used,
                memory_available, memory_total, temperature_sensors, power_supplies, fans
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            device_id, run_id, cpu_usage, memory_used, memory_available, memory_total,
            json.dumps(env_data.get('temperature', {})),
            json.dumps(env_data.get('power', {})),
            json.dumps(env_data.get('fans', {}))
        ))

        self.connection.commit()

    def insert_device_config(self, device_id: int, run_id: int, config_data: Dict):
        """Insert device configuration data"""
        cursor = self.connection.cursor()

        for config_type, config_content in config_data.items():
            if config_content:
                # Calculate hash for change detection
                config_hash = hashlib.sha256(config_content.encode()).hexdigest()
                line_count = config_content.count('\n') + 1
                size_bytes = len(config_content.encode())

                cursor.execute("""
                    INSERT INTO device_configs (
                        device_id, collection_run_id, config_type,
                        config_content, config_hash, size_bytes, line_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    device_id, run_id, config_type, config_content,
                    config_hash, size_bytes, line_count
                ))

        self.connection.commit()

    def insert_device_users(self, device_id: int, run_id: int, users_data: Dict):
        """Insert device user account data"""
        cursor = self.connection.cursor()

        for username, user_info in users_data.items():
            cursor.execute("""
                INSERT INTO device_users (
                    device_id, collection_run_id, username,
                    privilege_level, password_hash, ssh_keys, user_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                device_id, run_id, username,
                user_info.get('level'),
                user_info.get('password'),
                json.dumps(user_info.get('sshkeys', [])),
                'local'  # Default to local if not specified
            ))

        self.connection.commit()

    def insert_vlans(self, device_id: int, run_id: int, vlan_data: Dict):
        """Insert VLAN data"""
        cursor = self.connection.cursor()

        for vlan_id, vlan_info in vlan_data.items():
            # Extract numeric VLAN ID and validate
            try:
                vlan_num = int(vlan_id)
                if vlan_num < 1 or vlan_num > 4094:
                    logging.debug(f"Skipping invalid VLAN ID: {vlan_id}")
                    continue  # Skip invalid VLAN IDs
            except (ValueError, TypeError):
                logging.debug(f"Skipping non-numeric VLAN ID: {vlan_id}")
                continue

            # Validate status
            status = vlan_info.get('status', 'active')
            if status not in ['active', 'suspended', 'shutdown']:
                status = 'active'

            cursor.execute("""
                INSERT INTO vlans (
                    device_id, collection_run_id, vlan_id, vlan_name, status,
                    interfaces
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                device_id, run_id, vlan_num,
                vlan_info.get('name'),
                status,
                json.dumps(vlan_info.get('interfaces', []))
            ))

        self.connection.commit()

    def insert_routes(self, device_id: int, run_id: int, route_data: List):
        """Insert routing table data"""
        cursor = self.connection.cursor()

        for route in route_data:
            # Parse destination network and prefix
            destination = route.get('destination', '')
            if '/' in destination:
                network, prefix = destination.split('/')
                prefix_length = int(prefix)
            else:
                network = destination
                prefix_length = 32 if '.' in destination else 128  # Default for IPv4/IPv6

            cursor.execute("""
                INSERT INTO routes (
                    device_id, collection_run_id, destination_network,
                    prefix_length, next_hop, interface_name, protocol,
                    metric, administrative_distance, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                device_id, run_id, network, prefix_length,
                route.get('next_hop'), route.get('outgoing_interface'),
                route.get('protocol', 'unknown'), route.get('metric'),
                route.get('preference'), True
            ))

        self.connection.commit()

    def get_hardware_inventory(self, device_name: str = None) -> List[Dict]:
        """Get complete hardware inventory including optics"""
        cursor = self.connection.cursor()

        base_query = """
            SELECT 
                d.device_name,
                d.site_code,
                hi.component_type,
                hi.slot_position,
                hi.part_number,
                hi.serial_number,
                hi.description,
                hi.firmware_version,
                hi.hardware_version,
                hi.status,
                hi.vendor,
                hi.model,
                hi.additional_data,
                cr.collection_time,
                ROW_NUMBER() OVER (PARTITION BY d.id, hi.component_type, hi.slot_position ORDER BY cr.collection_time DESC) as rn
            FROM hardware_inventory hi
            JOIN devices d ON hi.device_id = d.id
            JOIN collection_runs cr ON hi.collection_run_id = cr.id
        """

        if device_name:
            cursor.execute(base_query + " WHERE d.device_name = ?", (device_name,))
        else:
            cursor.execute(base_query)

        results = []
        for row in cursor.fetchall():
            if row['rn'] == 1:  # Only latest data per component
                row_dict = dict(row)
                # For transceivers, add optics data to the display
                if row['component_type'] == 'transceiver' and row['additional_data']:
                    try:
                        metrics = json.loads(row['additional_data'])
                        # Add key optics metrics to the main record
                        row_dict['input_power'] = metrics.get('input_power_dbm')
                        row_dict['output_power'] = metrics.get('output_power_dbm')
                        row_dict['laser_bias'] = metrics.get('laser_bias_current_ma')
                    except json.JSONDecodeError:
                        pass
                results.append(row_dict)

        return results

    def import_napalm_data(self, napalm_data: Dict):
        """Import complete NAPALM collection data"""
        device_name = napalm_data.get('device_name', 'Unknown')

        try:
            # Insert/update device
            device_id = self.insert_or_update_device(napalm_data)
            logging.info(f"Device {device_name} - ID: {device_id}")

            # Insert collection run
            run_id = self.insert_collection_run(device_id, napalm_data)
            logging.info(f"Collection run created - ID: {run_id}")

            data = napalm_data['data']
            imported_data_types = []

            # Insert data based on what was collected
            try:
                if 'get_interfaces' in data:
                    interfaces_ip = data.get('get_interfaces_ip', {})
                    self.insert_interfaces(device_id, run_id, data['get_interfaces'], interfaces_ip)
                    imported_data_types.append("interfaces")
            except Exception as e:
                logging.warning(f"Failed to import interfaces for {device_name}: {e}")

            try:
                if 'get_lldp_neighbors' in data:
                    self.insert_lldp_neighbors(device_id, run_id, data['get_lldp_neighbors'])
                    imported_data_types.append("lldp_neighbors")
            except Exception as e:
                logging.warning(f"Failed to import LLDP neighbors for {device_name}: {e}")

            try:
                if 'get_arp_table' in data:
                    self.insert_arp_table(device_id, run_id, data['get_arp_table'])
                    imported_data_types.append("arp_table")
            except Exception as e:
                logging.warning(f"Failed to import ARP table for {device_name}: {e}")

            try:
                if 'get_mac_address_table' in data:
                    self.insert_mac_address_table(device_id, run_id, data['get_mac_address_table'])
                    imported_data_types.append("mac_address_table")
            except Exception as e:
                logging.warning(f"Failed to import MAC address table for {device_name}: {e}")

            try:
                if 'get_environment' in data:
                    self.insert_environment_data(device_id, run_id, data['get_environment'])
                    imported_data_types.append("environment")
            except Exception as e:
                logging.warning(f"Failed to import environment data for {device_name}: {e}")

            try:
                if 'get_config' in data:
                    self.insert_device_config(device_id, run_id, data['get_config'])
                    imported_data_types.append("config")
            except Exception as e:
                logging.warning(f"Failed to import configuration for {device_name}: {e}")

            try:
                if 'get_users' in data:
                    self.insert_device_users(device_id, run_id, data['get_users'])
                    imported_data_types.append("users")
            except Exception as e:
                logging.warning(f"Failed to import users for {device_name}: {e}")

            try:
                if 'get_vlans' in data:
                    self.insert_vlans(device_id, run_id, data['get_vlans'])
                    imported_data_types.append("vlans")
            except Exception as e:
                logging.warning(f"Failed to import VLANs for {device_name}: {e}")

            try:
                if 'get_route_to' in data:
                    self.insert_routes(device_id, run_id, data['get_route_to'])
                    imported_data_types.append("routes")
            except Exception as e:
                logging.warning(f"Failed to import routes for {device_name}: {e}")

            # NEW: Hardware inventory including optics
            try:
                # Collect hardware data from multiple sources
                hardware_data = {}

                # Add optics data
                if 'get_optics' in data:
                    hardware_data['optics'] = data['get_optics']

                # Add environment hardware data
                if 'get_environment' in data:
                    env_data = data['get_environment']
                    if 'power' in env_data:
                        hardware_data['power_supplies'] = env_data['power']
                    if 'fans' in env_data:
                        hardware_data['fans'] = env_data['fans']

                # Import hardware inventory if we have any data
                if hardware_data:
                    self.insert_hardware_inventory(device_id, run_id, hardware_data)
                    imported_data_types.append("hardware_inventory")
            except Exception as e:
                logging.warning(f"Failed to import hardware inventory for {device_name}: {e}")

            if imported_data_types:
                logging.info(f"Successfully imported {device_name}: {', '.join(imported_data_types)}")
            else:
                logging.warning(f"No data imported for {device_name}")

        except Exception as e:
            logging.error(f"Error importing data for {device_name}: {str(e)}")
            self.connection.rollback()
            raise

    def insert_hardware_inventory(self, device_id: int, run_id: int, hardware_data: Dict):
        """Insert hardware inventory data including optics"""
        cursor = self.connection.cursor()

        # Process optical transceivers from get_optics data
        if 'optics' in hardware_data:
            for interface_name, optics_info in hardware_data['optics'].items():
                # Extract optical metrics from the nested structure
                physical_channels = optics_info.get('physical_channels', {})
                channels = physical_channels.get('channel', [])

                if channels:
                    channel_data = channels[0]  # Most interfaces have single channel
                    state = channel_data.get('state', {})

                    # Extract power and current measurements
                    input_power = state.get('input_power', {})
                    output_power = state.get('output_power', {})
                    laser_bias = state.get('laser_bias_current', {})

                    # Create comprehensive optics data
                    optics_metrics = {
                        'input_power_dbm': input_power.get('instant'),
                        'output_power_dbm': output_power.get('instant'),
                        'laser_bias_current_ma': laser_bias.get('instant'),
                        'interface_name': interface_name
                    }

                    # Determine transceiver status based on power levels
                    status = 'operational'
                    if input_power.get('instant', 0) < -30:  # Very low input power
                        status = 'failed'
                    elif input_power.get('instant', 0) < -20:  # Low input power
                        status = 'unknown'

                    # Insert as transceiver component
                    cursor.execute("""
                        INSERT INTO hardware_inventory (
                            device_id, collection_run_id, component_type, slot_position,
                            description, status, additional_data
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        device_id, run_id, 'transceiver', interface_name,
                        f"Optical transceiver for {interface_name}",
                        status,
                        json.dumps(optics_metrics)
                    ))

        # Process power supplies from environment data
        if 'power_supplies' in hardware_data:
            for psu_name, psu_info in hardware_data['power_supplies'].items():
                cursor.execute("""
                    INSERT INTO hardware_inventory (
                        device_id, collection_run_id, component_type, slot_position,
                        part_number, serial_number, description, status,
                        vendor, model, additional_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    device_id, run_id, 'psu', psu_name,
                    psu_info.get('part_number'),
                    psu_info.get('serial_number'),
                    psu_info.get('description'),
                    'operational' if psu_info.get('status') == 'ok' else 'failed',
                    psu_info.get('vendor'),
                    psu_info.get('model'),
                    json.dumps(psu_info)
                ))

        # Process fans from environment data
        if 'fans' in hardware_data:
            for fan_name, fan_info in hardware_data['fans'].items():
                cursor.execute("""
                    INSERT INTO hardware_inventory (
                        device_id, collection_run_id, component_type, slot_position,
                        description, status, additional_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    device_id, run_id, 'fan', fan_name,
                    fan_info.get('description'),
                    'operational' if fan_info.get('status') == 'ok' else 'failed',
                    json.dumps(fan_info)
                ))

        self.connection.commit()
    def get_device_summary(self) -> List[Dict]:
        """Get summary of all devices"""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT 
                d.device_name, di.ip_address as primary_ip, d.vendor, d.model, 
                d.os_version, d.site_code, d.device_role, d.last_updated, d.is_active
            FROM devices d
            LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
            ORDER BY d.site_code, d.device_name
        """)

        return [dict(row) for row in cursor.fetchall()]

    def get_device_interfaces(self, device_name: str) -> List[Dict]:
        """Get latest interfaces for a device"""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT i.*, d.device_name, d.site_code, cr.collection_time
            FROM interfaces i
            JOIN devices d ON i.device_id = d.id
            JOIN collection_runs cr ON i.collection_run_id = cr.id
            WHERE d.device_name = ?
            AND cr.id = (
                SELECT id FROM collection_runs cr2 
                WHERE cr2.device_id = d.id 
                ORDER BY cr2.collection_time DESC 
                LIMIT 1
            )
            ORDER BY i.interface_name
        """, (device_name,))

        return [dict(row) for row in cursor.fetchall()]

    def get_network_topology(self) -> List[Dict]:
        """Get current network topology from LLDP"""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT 
                d1.device_name as local_device,
                ln.local_interface,
                ln.remote_hostname as remote_device,
                ln.remote_port as destination_interface,
                d1.site_code as local_site,
                d2.site_code as remote_site,
                cr.collection_time
            FROM lldp_neighbors ln
            JOIN devices d1 ON ln.device_id = d1.id
            JOIN collection_runs cr ON ln.collection_run_id = cr.id
            LEFT JOIN devices d2 ON (d2.device_name = ln.remote_hostname OR d2.hostname = ln.remote_hostname)
            WHERE cr.id IN (
                SELECT id FROM collection_runs cr2 
                WHERE cr2.device_id = ln.device_id 
                ORDER BY cr2.collection_time DESC 
                LIMIT 1
            )
            ORDER BY d1.device_name, ln.local_interface
        """)

        return [dict(row) for row in cursor.fetchall()]

    def search_mac_address(self, mac_address: str) -> List[Dict]:
        """Search for MAC address across all devices"""
        # Normalize the search MAC address
        normalized_mac = self._normalize_mac_address(mac_address)
        if not normalized_mac:
            return []

        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT 
                d.device_name, di.ip_address as device_ip, d.site_code,
                mat.interface_name, mat.vlan_id, mat.entry_type,
                cr.collection_time
            FROM mac_address_table mat
            JOIN devices d ON mat.device_id = d.id
            JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
            JOIN collection_runs cr ON mat.collection_run_id = cr.id
            WHERE mat.mac_address = ?
            ORDER BY cr.collection_time DESC
        """, (normalized_mac,))

        results = [dict(row) for row in cursor.fetchall()]

        # Also search in ARP tables
        cursor.execute("""
            SELECT 
                d.device_name, di.ip_address as device_ip, d.site_code,
                ae.interface_name, NULL as vlan_id, ae.entry_type,
                cr.collection_time, ae.ip_address as arp_ip
            FROM arp_entries ae
            JOIN devices d ON ae.device_id = d.id
            JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
            JOIN collection_runs cr ON ae.collection_run_id = cr.id
            WHERE ae.mac_address = ?
            ORDER BY cr.collection_time DESC
        """, (normalized_mac,))

        arp_results = [dict(row) for row in cursor.fetchall()]

        return results + arp_results

    def get_device_health(self) -> List[Dict]:
        """Get health status of all devices"""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT 
                d.id, d.device_name, di.ip_address as primary_ip, d.site_code,
                d.vendor, d.model, d.device_role,
                ed.cpu_usage, ed.memory_used, ed.memory_available, ed.memory_total,
                CASE 
                    WHEN ed.memory_total > 0 THEN ROUND((ed.memory_used * 100.0 / ed.memory_total), 2)
                    WHEN ed.memory_available > 0 THEN ROUND((ed.memory_used * 100.0 / (ed.memory_used + ed.memory_available)), 2)
                    ELSE NULL
                END as memory_usage_percent,
                ROUND(d.uptime / 86400.0, 1) as uptime_days,
                cr.collection_time as last_collection,
                cr.success as last_collection_success
            FROM devices d
            LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
            LEFT JOIN (
                SELECT device_id, cpu_usage, memory_used, memory_available, memory_total,
                       ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY created_at DESC) as rn
                FROM environment_data
            ) ed ON d.id = ed.device_id AND ed.rn = 1
            LEFT JOIN (
                SELECT device_id, collection_time, success,
                       ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY collection_time DESC) as rn
                FROM collection_runs
            ) cr ON d.id = cr.device_id AND cr.rn = 1
            WHERE d.is_active = 1
            ORDER BY d.device_name
        """)

        return [dict(row) for row in cursor.fetchall()]

    def get_device_configs(self, device_name: str, config_type: str = None) -> List[Dict]:
        """Get device configurations"""
        cursor = self.connection.cursor()

        if config_type:
            cursor.execute("""
                SELECT dc.*, cr.collection_time
                FROM device_configs dc
                JOIN devices d ON dc.device_id = d.id
                JOIN collection_runs cr ON dc.collection_run_id = cr.id
                WHERE d.device_name = ? AND dc.config_type = ?
                ORDER BY cr.collection_time DESC
            """, (device_name, config_type))
        else:
            cursor.execute("""
                SELECT dc.*, cr.collection_time
                FROM device_configs dc
                JOIN devices d ON dc.device_id = d.id
                JOIN collection_runs cr ON dc.collection_run_id = cr.id
                WHERE d.device_name = ?
                ORDER BY dc.config_type, cr.collection_time DESC
            """, (device_name,))

        return [dict(row) for row in cursor.fetchall()]

    def get_site_summary(self) -> List[Dict]:
        """Get summary by site"""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT 
                site_code,
                COUNT(*) as device_count,
                COUNT(CASE WHEN device_role = 'core' THEN 1 END) as core_count,
                COUNT(CASE WHEN device_role = 'access' THEN 1 END) as access_count,
                COUNT(CASE WHEN device_role = 'distribution' THEN 1 END) as distribution_count,
                COUNT(CASE WHEN device_role = 'firewall' THEN 1 END) as firewall_count,
                COUNT(CASE WHEN device_role = 'router' THEN 1 END) as router_count,
                GROUP_CONCAT(DISTINCT vendor) as vendors
            FROM devices
            WHERE is_active = 1
            GROUP BY site_code
            ORDER BY site_code
        """)

        return [dict(row) for row in cursor.fetchall()]

    def check_duplicate_device_names(self) -> List[Dict]:
        """Check for any duplicate device names in the database"""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT device_name, COUNT(*) as count 
            FROM devices 
            GROUP BY device_name 
            HAVING COUNT(*) > 1
        """)

        return [dict(row) for row in cursor.fetchall()]


def import_napalm_files(db_path: str, files_directory: str, schema_path: str = "cmdb.sql"):
    """Import all NAPALM JSON files from a directory"""
    cmdb = NapalmCMDB(db_path, schema_path)
    files_path = Path(files_directory)

    json_files = list(files_path.glob("**/*_complete.json"))

    logging.info(f"Found {len(json_files)} NAPALM collection files")

    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                napalm_data = json.load(f)

            cmdb.import_napalm_data(napalm_data)
            logging.info(f"Imported: {json_file.name}")

        except Exception as e:
            logging.error(f"Failed to import {json_file}: {str(e)}")

    # Check for any duplicates after import
    duplicates = cmdb.check_duplicate_device_names()
    if duplicates:
        logging.warning(f"Found {len(duplicates)} duplicate device names:")
        for dup in duplicates:
            logging.warning(f"  {dup['device_name']}: {dup['count']} entries")

    cmdb.close()
    logging.info("Import complete")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='NAPALM CMDB Database Manager')
    parser.add_argument('--import-dir', help='Directory containing NAPALM JSON files')
    parser.add_argument('--db-path', default='napalm_cmdb.db', help='SQLite database path')
    parser.add_argument('--schema-path', default='cmdb.sql', help='SQL schema file path')
    parser.add_argument('--summary', action='store_true', help='Show device summary')
    parser.add_argument('--topology', action='store_true', help='Show network topology')
    parser.add_argument('--health', action='store_true', help='Show device health')
    parser.add_argument('--sites', action='store_true', help='Show site summary')
    parser.add_argument('--interfaces', help='Show interfaces for device (specify device name)')
    parser.add_argument('--configs', help='Show configs for device (specify device name)')
    parser.add_argument('--config-type', help='Filter configs by type (running, startup, candidate)')
    parser.add_argument('--search-mac', help='Search for MAC address')
    parser.add_argument('--check-duplicates', action='store_true', help='Check for duplicate device names')

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    if args.import_dir:
        import_napalm_files(args.db_path, args.import_dir, args.schema_path)
    elif args.summary:
        cmdb = NapalmCMDB(args.db_path, args.schema_path)
        devices = cmdb.get_device_summary()
        print(f"\n{'Device Name':<25} {'Primary IP':<15} {'Vendor':<10} {'Model':<15} {'Site':<5} {'Role':<12}")
        print("-" * 90)
        for device in devices:
            print(f"{device['device_name']:<25} {device['primary_ip'] or 'N/A':<15} "
                  f"{device['vendor']:<10} {device['model'] or 'N/A':<15} "
                  f"{device['site_code']:<5} {device['device_role']:<12}")
        cmdb.close()
    elif args.topology:
        cmdb = NapalmCMDB(args.db_path, args.schema_path)
        topology = cmdb.get_network_topology()
        print(f"\n{'Local Device':<20} {'Local Port':<15} {'Remote Device':<20} {'Remote Port':<15} {'Sites':<10}")
        print("-" * 85)
        for link in topology:
            sites = f"{link['local_site']}->{link['remote_site'] or 'UNK'}"
            print(f"{link['local_device']:<20} {link['local_interface']:<15} "
                  f"{link['remote_device'] or 'Unknown':<20} {link['destination_interface'] or 'N/A':<15} {sites:<10}")
        cmdb.close()
    elif args.health:
        cmdb = NapalmCMDB(args.db_path, args.schema_path)
        health = cmdb.get_device_health()
        print(
            f"\n{'Device Name':<20} {'Site':<5} {'CPU %':<8} {'Memory %':<10} {'Uptime Days':<12} {'Last Collection':<12}")
        print("-" * 80)
        for device in health:
            cpu = f"{device['cpu_usage']:.1f}" if device['cpu_usage'] else "N/A"
            mem = f"{device['memory_usage_percent']:.1f}" if device['memory_usage_percent'] else "N/A"
            uptime = f"{device['uptime_days']:.1f}" if device['uptime_days'] else "N/A"
            last_collection = "Success" if device['last_collection_success'] else "Failed"
            print(
                f"{device['device_name']:<20} {device['site_code']:<5} {cpu:<8} {mem:<10} {uptime:<12} {last_collection:<12}")
        cmdb.close()
    elif args.sites:
        cmdb = NapalmCMDB(args.db_path, args.schema_path)
        sites = cmdb.get_site_summary()
        print(f"\n{'Site':<5} {'Total':<6} {'Core':<5} {'Access':<7} {'Dist':<5} {'FW':<3} {'RTR':<4} {'Vendors':<20}")
        print("-" * 60)
        for site in sites:
            print(f"{site['site_code']:<5} {site['device_count']:<6} {site['core_count']:<5} "
                  f"{site['access_count']:<7} {site['distribution_count']:<5} {site['firewall_count']:<3} "
                  f"{site['router_count']:<4} {site['vendors'] or 'N/A':<20}")
        cmdb.close()
    elif args.interfaces:
        cmdb = NapalmCMDB(args.db_path, args.schema_path)
        interfaces = cmdb.get_device_interfaces(args.interfaces)
        if interfaces:
            print(f"\nInterfaces for {args.interfaces}:")
            print(f"{'Interface':<20} {'Type':<12} {'Admin':<8} {'Oper':<6} {'Speed':<10} {'Description':<25}")
            print("-" * 85)
            for intf in interfaces:
                speed = f"{intf['speed']}" if intf['speed'] else "N/A"
                desc = (intf['description'] or '')[:24]
                print(f"{intf['interface_name']:<20} {intf['interface_type']:<12} {intf['admin_status']:<8} "
                      f"{intf['oper_status']:<6} {speed:<10} {desc:<25}")
        else:
            print(f"No interfaces found for device: {args.interfaces}")
        cmdb.close()
    elif args.configs:
        cmdb = NapalmCMDB(args.db_path, args.schema_path)
        configs = cmdb.get_device_configs(args.configs, args.config_type)
        if configs:
            print(f"\nConfigurations for {args.configs}:")
            for config in configs:
                print(f"\nConfig Type: {config['config_type']}")
                print(f"Collection Time: {config['collection_time']}")
                print(f"Size: {config['size_bytes']} bytes, {config['line_count']} lines")
                print(f"Hash: {config['config_hash'][:16]}...")
                if len(configs) == 1:  # Only show content if single config
                    print("\nContent (first 500 chars):")
                    print("-" * 50)
                    print(config['config_content'][:500])
                    if len(config['config_content']) > 500:
                        print("...")
        else:
            print(f"No configurations found for device: {args.configs}")
        cmdb.close()
    elif args.search_mac:
        cmdb = NapalmCMDB(args.db_path, args.schema_path)
        results = cmdb.search_mac_address(args.search_mac)
        if results:
            print(f"\nMAC address {args.search_mac} found:")
            print(f"{'Device':<20} {'Interface':<15} {'VLAN':<6} {'Type':<8} {'Site':<5} {'Collection Time':<12}")
            print("-" * 75)
            for result in results:
                vlan = str(result['vlan_id']) if result['vlan_id'] else 'N/A'
                collection_time = result['collection_time'][:10] if result['collection_time'] else 'N/A'
                print(f"{result['device_name']:<20} {result['interface_name'] or 'N/A':<15} "
                      f"{vlan:<6} {result['entry_type']:<8} {result['site_code']:<5} {collection_time:<12}")
        else:
            print(f"MAC address {args.search_mac} not found")
        cmdb.close()
    elif args.check_duplicates:
        cmdb = NapalmCMDB(args.db_path, args.schema_path)
        duplicates = cmdb.check_duplicate_device_names()
        if duplicates:
            print("Duplicate device names found:")
            for dup in duplicates:
                print(f"  {dup['device_name']}: {dup['count']} entries")
        else:
            print("No duplicate device names found.")
        cmdb.close()
    else:
        parser.print_help()