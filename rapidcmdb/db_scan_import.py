#!/usr/bin/env python3
"""
DB Scan Import Tool - Import SNMP discovery data into NAPALM CMDB
Handles rich SNMP device data from scan files with dry-run and filtering capabilities
Fixed to commit changes per record to avoid database locking issues
"""

import argparse
import json
import sqlite3
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, asdict
import hashlib
import re
from pathlib import Path
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ImportedDevice:
    """Represents a device to be imported"""
    device_key: str
    device_name: str
    hostname: str
    fqdn: Optional[str]
    vendor: str
    model: str
    serial_number: str
    os_version: Optional[str]
    site_code: str
    device_role: str
    primary_ip: str
    all_ips: List[str]
    mac_addresses: List[str]
    snmp_data: Dict
    confidence_score: int
    detection_method: str
    first_seen: str
    last_seen: str
    notes: Optional[str] = None


class ScanImporter:
    """Main import tool for scan data"""

    def __init__(self, db_path: str, dry_run: bool = False):
        self.db_path = db_path
        self.dry_run = dry_run
        self.stats = {
            'devices_processed': 0,
            'devices_imported': 0,
            'devices_updated': 0,
            'devices_skipped': 0,
            'duplicates_found': 0,
            'errors': 0
        }

        # Device type mappings for role assignment
        self.device_role_mapping = {
            'router': 'router',
            'switch': 'switch',
            'firewall': 'firewall',
            'ups': 'ups',  # Now supported in schema
            'printer': 'printer',  # Now supported in schema
            'camera': 'camera',  # Now supported in schema
            'server': 'server',  # Now supported in schema
            'wireless_controller': 'wireless',
            'sdwan': 'router',
            'load_balancer': 'load_balancer',
            'label_printer': 'printer',  # Map to printer
            'unknown': 'unknown'
        }

        # Vendor normalization
        self.vendor_mapping = {
            'cisco systems': 'cisco',
            'cisco systems, inc.': 'cisco',
            'hewlett packard': 'hp',
            'hewlett-packard': 'hp',
            'hewlett packard enterprise': 'hpe',
            'juniper networks': 'juniper',
            'juniper networks, inc.': 'juniper',
            'palo alto networks': 'palo_alto',
            'american power conversion': 'apc',
            'fortinet': 'fortinet',
            'arista networks': 'arista'
        }

        if not self.dry_run:
            self._init_database()

    def _init_database(self):
        """Initialize database connection and verify schema"""
        try:
            conn = sqlite3.connect(self.db_path)

            # Test if devices table exists
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='devices'
            """)

            if not cursor.fetchone():
                logger.error(f"Database schema not found. Please create using cmdb.sql first.")
                sys.exit(1)

            conn.close()
            logger.info(f"Database connection verified: {self.db_path}")

        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            sys.exit(1)

    def _get_db_connection(self) -> sqlite3.Connection:
        """Get database connection with optimized settings for avoiding locks"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=60.0,  # Increased timeout
            isolation_level=None  # Autocommit mode
        )
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        # Reduce busy timeout
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def normalize_vendor(self, vendor: str) -> str:
        """Normalize vendor names"""
        if not vendor:
            return 'unknown'

        vendor_lower = vendor.lower().strip()

        # Check direct mappings
        if vendor_lower in self.vendor_mapping:
            return self.vendor_mapping[vendor_lower]

        # Check partial matches
        for key, mapped in self.vendor_mapping.items():
            if key in vendor_lower:
                return mapped

        return vendor_lower

    def generate_device_key(self, vendor: str, serial: str, model: str) -> str:
        """Generate stable device key for deduplication"""
        key_string = f"{vendor}|{serial}|{model}".lower()
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]

    def extract_model_from_sys_descr(self, vendor: str, device_type: str, sys_descr: str) -> Optional[str]:
        """Extract model number from system description based on vendor patterns"""
        if not sys_descr:
            return None

        sys_descr = sys_descr.strip()

        # Palo Alto Networks patterns
        if vendor == 'palo_alto' or 'palo alto' in sys_descr.lower():
            # Pattern: "Palo Alto Networks PA-220 series firewall"
            # Pattern: "Palo Alto Networks PA-3020 firewall"
            # Pattern: "Palo Alto Networks VM-50 series firewall"
            pa_patterns = [
                r'PA-(\d+[A-Z]*)\s+series',  # PA-220 series, PA-3020 series
                r'PA-(\d+[A-Z]*)\s+firewall',  # PA-220 firewall
                r'VM-(\d+)\s+series',  # VM-50 series
                r'VM-(\d+)\s+firewall',  # VM-50 firewall
                r'PA-(\d+[A-Z]*)',  # Generic PA-model
                r'VM-(\d+)'  # Generic VM-model
            ]

            for pattern in pa_patterns:
                match = re.search(pattern, sys_descr, re.IGNORECASE)
                if match:
                    model_num = match.group(1)
                    if 'VM-' in sys_descr:
                        return f"VM-{model_num}"
                    else:
                        return f"PA-{model_num}"

        # Cisco patterns
        elif vendor == 'cisco' or 'cisco' in sys_descr.lower():
            # Pattern: "Cisco IOS Software, C2960X Software"
            # Pattern: "Cisco ASA Software Version 9.8(4)20"
            cisco_patterns = [
                r'C(\d+[A-Z]*)[^a-zA-Z]',  # C2960X, C3850, etc.
                r'ASA\s+(\d+[A-Z]*)',  # ASA 5516, ASA5516-X
                r'ISR(\d+[A-Z]*)',  # ISR4331, ISR2901
                r'ASR(\d+[A-Z]*)',  # ASR1001-X
                r'WS-C(\d+[A-Z-]*)',  # WS-C2960X-48FPS-L
                r'Catalyst\s+(\d+[A-Z-]*)'  # Catalyst 2960X
            ]

            for pattern in cisco_patterns:
                match = re.search(pattern, sys_descr, re.IGNORECASE)
                if match:
                    model_num = match.group(1)
                    # Determine prefix based on pattern
                    if 'ASA' in sys_descr:
                        return f"ASA{model_num}"
                    elif 'ISR' in sys_descr:
                        return f"ISR{model_num}"
                    elif 'ASR' in sys_descr:
                        return f"ASR{model_num}"
                    elif 'WS-C' in sys_descr:
                        return f"WS-C{model_num}"
                    else:
                        return f"C{model_num}"

        # Arista patterns
        elif vendor == 'arista' or 'arista' in sys_descr.lower():
            # Pattern: "Arista Networks EOS version 4.20.1F running on an Arista Networks DCS-7050CX3-32S"
            arista_patterns = [
                r'DCS-([0-9A-Z-]+)',  # DCS-7050CX3-32S
                r'CCS-([0-9A-Z-]+)',  # CCS series
                r'vEOS-([0-9A-Z-]+)'  # Virtual EOS
            ]

            for pattern in arista_patterns:
                match = re.search(pattern, sys_descr, re.IGNORECASE)
                if match:
                    return f"DCS-{match.group(1)}" if 'DCS' in pattern else f"CCS-{match.group(1)}"

        # Juniper patterns
        elif vendor == 'juniper' or 'juniper' in sys_descr.lower():
            # Pattern: "Juniper Networks, Inc. srx220 internet router"
            # Pattern: "Juniper Networks, Inc. ex4200-48t"
            juniper_patterns = [
                r'(srx\d+[a-z]*)',  # srx220, srx1500
                r'(ex\d+[a-z-]*)',  # ex4200-48t
                r'(mx\d+[a-z-]*)',  # mx480, mx960
                r'(qfx\d+[a-z-]*)'  # qfx5100
            ]

            for pattern in juniper_patterns:
                match = re.search(pattern, sys_descr, re.IGNORECASE)
                if match:
                    return match.group(1).upper()

        # Generic patterns for other vendors
        else:
            # Try to find common model patterns
            generic_patterns = [
                r'(\b[A-Z]{2,4}-\d+[A-Z]*)',  # XX-1234A format
                r'(\b\d+[A-Z]+\b)',  # 2960X, 3850X format
                r'(\b[A-Z]+\d+[A-Z-]*)'  # ASA5516-X format
            ]

            for pattern in generic_patterns:
                match = re.search(pattern, sys_descr)
                if match:
                    return match.group(1)

        return None

    def parse_device_from_scan(self, device_id: str, device_data: Dict) -> Optional[ImportedDevice]:
        """Parse device data from scan format into ImportedDevice"""
        try:
            # ✅ CRITICAL VALIDATION: Check for fundamental SNMP fields first
            sys_name = device_data.get('sys_name', '').strip()
            sys_descr = device_data.get('sys_descr', '').strip()

            # Skip devices with no useful SNMP information
            if not sys_name and not sys_descr:
                logger.warning(
                    f"Skipping device {device_id}: both sys_name and sys_descr are empty - no valuable device information")
                return None

            # Also check SNMP data for system description if main fields are empty
            if not sys_descr:
                snmp_data = device_data.get('snmp_data_by_ip', {})
                for ip, snmp_info in snmp_data.items():
                    snmp_sys_descr = snmp_info.get('1.3.6.1.2.1.1.1.0', '').strip()
                    if snmp_sys_descr and snmp_sys_descr != '<nil>':
                        sys_descr = snmp_sys_descr
                        device_data['sys_descr'] = sys_descr  # Update the original data
                        logger.info(f"Found sys_descr in SNMP data for {device_id}: {sys_descr[:50]}...")
                        break

            # Also check SNMP data for system name if main field is empty
            if not sys_name:
                snmp_data = device_data.get('snmp_data_by_ip', {})
                for ip, snmp_info in snmp_data.items():
                    snmp_sys_name = snmp_info.get('1.3.6.1.2.1.1.5.0', '').strip()
                    if snmp_sys_name and snmp_sys_name != '<nil>' and snmp_sys_name != ip:
                        sys_name = snmp_sys_name
                        device_data['sys_name'] = sys_name  # Update the original data
                        logger.info(f"Found sys_name in SNMP data for {device_id}: {sys_name}")
                        break

            # ✅ FINAL VALIDATION: After trying SNMP extraction, check again
            if not sys_name and not sys_descr:
                logger.warning(f"Skipping device {device_id}: no sys_name or sys_descr found even in SNMP data")
                return None

            # ✅ ADDITIONAL QUALITY CHECKS: Skip devices with meaningless data
            if sys_name and sys_name.lower() in ['unknown', 'null', 'none', '']:
                sys_name = ''  # Reset meaningless values

            if sys_descr and sys_descr.lower() in ['unknown', 'null', 'none', '']:
                sys_descr = ''  # Reset meaningless values

            # Re-check after quality filtering
            if not sys_name and not sys_descr:
                logger.warning(f"Skipping device {device_id}: sys_name and sys_descr contain no meaningful data")
                return None

            # Extract basic device info
            vendor = self.normalize_vendor(device_data.get('vendor', 'unknown'))
            model = device_data.get('model', '').strip()
            serial_number = device_data.get('serial_number', '').strip()
            device_type = device_data.get('device_type', 'unknown')

            # ✅ VENDOR VALIDATION: Skip devices with no vendor information AND no useful sys_descr
            if vendor == 'unknown' and not sys_descr:
                logger.warning(f"Skipping device {device_id}: unknown vendor and no sys_descr to identify device")
                return None

            # Enhanced serial number extraction from SNMP data if missing
            if not serial_number:
                snmp_data = device_data.get('snmp_data_by_ip', {})
                for ip, snmp_info in snmp_data.items():
                    # Try various SNMP fields for serial number
                    serial_candidates = [
                        snmp_info.get('APC Serial Number'),
                        snmp_info.get('Lexmark Serial Number'),
                        snmp_info.get('Entity Serial Number'),
                        snmp_info.get('Serial Number')
                    ]
                    for candidate in serial_candidates:
                        if candidate and candidate != '<nil>' and candidate.strip():
                            serial_number = candidate.strip()
                            logger.info(f"Found serial number in SNMP data for {device_id}: {serial_number}")
                            break
                    if serial_number:
                        break

            # Try to extract serial from sys_descr for specific vendors
            if not serial_number:
                if vendor == 'lexmark' and sys_descr:
                    # Look for patterns like "version NH.HS60.N762" which might contain device ID
                    version_match = re.search(r'version\s+([A-Z0-9\.]+)', sys_descr)
                    if version_match:
                        serial_number = f"lexmark_{version_match.group(1)}"
                        logger.info(f"Extracted version-based serial for {device_id}: {serial_number}")

            # Generate device identifiers - prefer sys_name, fall back to device_id
            hostname = sys_name or device_id
            primary_ip = device_data.get('primary_ip', '')

            # Handle devices without serial numbers by using alternative identifiers
            if not serial_number or not serial_number.strip():
                # For printers and other devices, use hostname + IP as fallback serial
                if hostname and hostname.strip() and primary_ip:
                    serial_number = f"{hostname.strip()}_{primary_ip}".replace('.', '_')
                    logger.info(f"Using fallback serial for {device_id}: {serial_number}")
                elif primary_ip:
                    serial_number = f"ip_{primary_ip}".replace('.', '_')
                    logger.info(f"Using IP-based serial for {device_id}: {serial_number}")
                else:
                    # Last resort: use device_id
                    serial_number = device_id.strip() if device_id else f"unknown_{hash(str(device_data))}"
                    logger.info(f"Using device_id as serial for {device_id}: {serial_number}")

            # Final validation - ensure serial is not empty
            if not serial_number or not serial_number.strip():
                logger.error(f"Cannot generate valid serial number for device {device_id}")
                return None

            # Clean up serial number (remove any problematic characters)
            serial_number = serial_number.strip()
            if len(serial_number) == 0:
                logger.error(f"Serial number is empty after cleanup for device {device_id}")
                return None

            device_key = self.generate_device_key(vendor, serial_number, model)
            site_code = self.extract_site_code(hostname, primary_ip)
            device_role = self.device_role_mapping.get(device_type, 'unknown')

            # Extract IP addresses
            all_ips = device_data.get('all_ips', [])
            if primary_ip and primary_ip not in all_ips:
                all_ips.insert(0, primary_ip)

            # Extract MAC addresses
            mac_addresses = device_data.get('mac_addresses', [])

            # Process interfaces for additional IPs/MACs
            interfaces = device_data.get('interfaces', {})
            for iface_name, iface_data in interfaces.items():
                if isinstance(iface_data, dict):
                    iface_ip = iface_data.get('ip_address')
                    if iface_ip and iface_ip not in all_ips:
                        all_ips.append(iface_ip)

                    iface_mac = iface_data.get('mac_address')
                    if iface_mac and iface_mac not in mac_addresses:
                        mac_addresses.append(iface_mac)

            # Extract enhanced device info from SNMP data
            snmp_data = device_data.get('snmp_data_by_ip', {})
            os_version = device_data.get('os_version')

            # Enhanced model extraction from SNMP and sys_descr if missing
            if not model:
                # First try SNMP vendor-specific fields
                for ip, snmp_info in snmp_data.items():
                    model_candidates = [
                        snmp_info.get('APC Model Number'),
                        snmp_info.get('Lexmark Model'),
                        snmp_info.get('Entity Model Name')
                    ]
                    for candidate in model_candidates:
                        if candidate and candidate != '<nil>' and candidate.strip():
                            model = candidate.strip()
                            break
                    if model:
                        break

                # If still no model, try extracting from sys_descr
                if not model and sys_descr:
                    model = self.extract_model_from_sys_descr(vendor, device_type, sys_descr)
                    if model:
                        logger.info(f"Extracted model from sys_descr for {device_id}: {model}")

            # For printers, try to get firmware version from SNMP
            if device_type == 'printer' and not os_version:
                for ip, snmp_info in snmp_data.items():
                    firmware_candidates = [
                        snmp_info.get('Lexmark Firmware Version'),
                        snmp_info.get('Firmware Version'),
                        snmp_info.get('Software Version')
                    ]
                    for candidate in firmware_candidates:
                        if candidate and candidate != '<nil>' and candidate.strip():
                            os_version = candidate.strip()
                            break
                    if os_version:
                        break

            # For UPS devices, extract additional info
            ups_info = None
            if device_type == 'ups':
                for ip, snmp_info in snmp_data.items():
                    ups_model = snmp_info.get('APC Model Number')
                    ups_serial = snmp_info.get('APC Serial Number')
                    if ups_model or ups_serial:
                        ups_info = {
                            'model': ups_model,
                            'serial': ups_serial,
                            'management_card': 'APC Web/SNMP Management Card' if 'APC Web/SNMP' in snmp_info.get(
                                '1.3.6.1.2.1.1.1.0', '') else None
                        }
                        break

            # Generate FQDN if we have hostname and site
            fqdn = None
            if hostname and not hostname.endswith('.'):
                if site_code != 'UNK':
                    fqdn = f"{hostname}.{site_code.lower()}.local"

            # Enhanced notes with device-specific information
            notes_parts = [f"Imported from scan data. Device type: {device_type}"]

            # ✅ ADD VALIDATION NOTES: Document what data was available
            data_quality_notes = []
            if sys_name:
                data_quality_notes.append("sys_name available")
            if sys_descr:
                data_quality_notes.append("sys_descr available")
            if not sys_name and not sys_descr:
                data_quality_notes.append("limited SNMP data")

            if data_quality_notes:
                notes_parts.append(f"Data quality: {', '.join(data_quality_notes)}")

            if ups_info:
                notes_parts.append(f"UPS Management: {ups_info.get('management_card', 'Standard SNMP')}")

            if device_type == 'printer':
                # Extract printer-specific info
                for ip, snmp_info in snmp_data.items():
                    kernel_info = None
                    if 'kernel' in sys_descr.lower():
                        kernel_match = re.search(r'kernel\s+([\d\.-]+)', sys_descr, re.IGNORECASE)
                        if kernel_match:
                            kernel_info = kernel_match.group(1)
                            notes_parts.append(f"Kernel: {kernel_info}")
                    break

            notes = '; '.join(notes_parts)

            # Create device object
            device = ImportedDevice(
                device_key=device_key,
                device_name=hostname or device_id,
                hostname=hostname,
                fqdn=fqdn,
                vendor=vendor,
                model=model,
                serial_number=serial_number,
                os_version=os_version,
                site_code=site_code,
                device_role=device_role,
                primary_ip=primary_ip,
                all_ips=all_ips,
                mac_addresses=mac_addresses,
                snmp_data=snmp_data,
                confidence_score=device_data.get('confidence_score', 50),
                detection_method=device_data.get('detection_method', 'snmp_scan'),
                first_seen=device_data.get('first_seen', datetime.now(timezone.utc).isoformat()),
                last_seen=device_data.get('last_seen', datetime.now(timezone.utc).isoformat()),
                notes=notes
            )

            # ✅ FINAL LOG: Show what device was accepted
            logger.info(
                f"Accepted device {device_id}: vendor={vendor}, sys_name='{sys_name}', sys_descr='{sys_descr[:50] if sys_descr else 'N/A'}{'...' if sys_descr and len(sys_descr) > 50 else ''}'")

            return device

        except Exception as e:
            logger.error(f"Error parsing device {device_id}: {e}")
            return None
    def extract_site_code(self, hostname: str, primary_ip: str) -> str:
        """Extract site code from hostname or IP"""
        if not hostname:
            hostname = ""

        # Look for site patterns in hostname (e.g., frc-device, usc-switch)
        site_match = re.match(r'^([a-z]{2,4})-', hostname.lower())
        if site_match:
            return site_match.group(1).upper()

        # Extract from IP address (e.g., 10.67.x.x = FRC site)
        if primary_ip:
            ip_parts = primary_ip.split('.')
            if len(ip_parts) >= 3:
                # Example: 10.67.x.x = FRC, 10.68.x.x = USC
                if ip_parts[0] == '10' and ip_parts[1] == '67':
                    return 'FRC'
                elif ip_parts[0] == '10' and ip_parts[1] == '68':
                    return 'USC'

        return 'UNK'  # Unknown site

    def import_device(self, device: ImportedDevice) -> bool:
        """Import single device into database with immediate commit"""
        try:
            # Check if device already exists
            exists, existing_id = self.device_exists(device)

            if exists:
                logger.info(f"Device already exists: {device.device_name} (ID: {existing_id})")
                self.stats['duplicates_found'] += 1
                return self.update_device(device, existing_id)

            if self.dry_run:
                logger.info(f"[DRY RUN] Would import device: {device.device_name} ({device.vendor} {device.model})")
                self.stats['devices_imported'] += 1
                return True

            # Validate required fields before attempting insert
            if not device.serial_number or not device.serial_number.strip():
                logger.error(f"Cannot import device {device.device_name}: empty serial number")
                self.stats['errors'] += 1
                return False

            if not device.vendor or not device.vendor.strip():
                logger.error(f"Cannot import device {device.device_name}: empty vendor")
                self.stats['errors'] += 1
                return False

            if not device.device_name or not device.device_name.strip():
                logger.error(f"Cannot import device: empty device name")
                self.stats['errors'] += 1
                return False

            # Create new connection for this transaction
            conn = None
            try:
                conn = self._get_db_connection()
                cursor = conn.cursor()

                # Start explicit transaction
                cursor.execute("BEGIN IMMEDIATE")

                insert_query = """
                    INSERT INTO devices (
                        device_key, device_name, hostname, fqdn, vendor, model, 
                        serial_number, os_version, site_code, device_role, notes,
                        first_discovered, last_updated, is_active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

                now = datetime.now().isoformat()

                cursor.execute(insert_query, (
                    device.device_key,
                    device.device_name,
                    device.hostname,
                    device.fqdn,
                    device.vendor,
                    device.model,
                    device.serial_number,
                    device.os_version,
                    device.site_code,
                    device.device_role,
                    device.notes,
                    now,
                    now,
                    1  # is_active
                ))

                device_id = cursor.lastrowid

                # Insert IP addresses
                for i, ip in enumerate(device.all_ips):
                    if ip and ip.strip():  # Skip empty IPs
                        cursor.execute("""
                            INSERT INTO device_ips (
                                device_id, ip_address, ip_type, is_primary, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            device_id,
                            ip,
                            'management' if i == 0 else 'secondary',
                            1 if i == 0 else 0,  # First IP is primary
                            now,
                            now
                        ))

                # Commit the transaction
                cursor.execute("COMMIT")

                logger.info(f"Successfully imported device: {device.device_name} (ID: {device_id})")
                self.stats['devices_imported'] += 1
                return True

            except sqlite3.DatabaseError as e:
                if conn:
                    try:
                        conn.execute("ROLLBACK")
                    except:
                        pass
                raise e

            finally:
                if conn:
                    conn.close()

        except sqlite3.IntegrityError as e:
            logger.error(f"Database constraint error importing device {device.device_name}: {e}")
            self.stats['errors'] += 1
            return False
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower():
                logger.warning(f"Database locked while importing {device.device_name}, retrying...")
                time.sleep(0.1)  # Brief pause before retry
                # Could implement retry logic here if needed
            logger.error(f"Database operational error importing device {device.device_name}: {e}")
            self.stats['errors'] += 1
            return False
        except Exception as e:
            logger.error(f"Error importing device {device.device_name}: {e}")
            self.stats['errors'] += 1
            return False

    def device_exists(self, device: ImportedDevice) -> Tuple[bool, Optional[int]]:
        """Check if device already exists in database"""
        if self.dry_run:
            return False, None

        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()

            # Check by device key first (most reliable)
            cursor.execute("SELECT id FROM devices WHERE device_key = ?", (device.device_key,))
            result = cursor.fetchone()

            if result:
                return True, result[0]

            # Check by serial number and vendor
            cursor.execute("""
                SELECT id FROM devices 
                WHERE serial_number = ? AND vendor = ?
            """, (device.serial_number, device.vendor))
            result = cursor.fetchone()

            return bool(result), result[0] if result else None

        except Exception as e:
            logger.error(f"Error checking if device exists: {e}")
            return False, None
        finally:
            if conn:
                conn.close()

    def update_device(self, device: ImportedDevice, existing_id: int) -> bool:
        """Update existing device with new information with immediate commit"""
        try:
            if self.dry_run:
                logger.info(f"[DRY RUN] Would update device: {device.device_name} (ID: {existing_id})")
                self.stats['devices_updated'] += 1
                return True

            conn = None
            try:
                conn = self._get_db_connection()
                cursor = conn.cursor()

                # Start explicit transaction
                cursor.execute("BEGIN IMMEDIATE")

                # Update device record
                update_query = """
                    UPDATE devices SET
                        device_name = ?, hostname = ?, fqdn = ?, os_version = ?,
                        last_updated = ?, notes = ?
                    WHERE id = ?
                """

                now = datetime.now().isoformat()

                cursor.execute(update_query, (
                    device.device_name,
                    device.hostname,
                    device.fqdn,
                    device.os_version,
                    now,
                    device.notes,
                    existing_id
                ))

                # Update IP addresses (simple approach: remove and re-add)
                cursor.execute("DELETE FROM device_ips WHERE device_id = ?", (existing_id,))

                for i, ip in enumerate(device.all_ips):
                    if ip:
                        cursor.execute("""
                            INSERT INTO device_ips (
                                device_id, ip_address, ip_type, is_primary, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            existing_id,
                            ip,
                            'management' if i == 0 else 'secondary',
                            1 if i == 0 else 0,
                            now,
                            now
                        ))

                # Commit the transaction
                cursor.execute("COMMIT")

                logger.info(f"Successfully updated device: {device.device_name} (ID: {existing_id})")
                self.stats['devices_updated'] += 1
                return True

            except sqlite3.DatabaseError as e:
                if conn:
                    try:
                        conn.execute("ROLLBACK")
                    except:
                        pass
                raise e

            finally:
                if conn:
                    conn.close()

        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower():
                logger.warning(f"Database locked while updating {device.device_name}, retrying...")
                time.sleep(0.1)
            logger.error(f"Database operational error updating device {device.device_name}: {e}")
            self.stats['errors'] += 1
            return False
        except Exception as e:
            logger.error(f"Error updating device {device.device_name}: {e}")
            self.stats['errors'] += 1
            return False

    def import_scan_file(self, scan_file: str, filters: Dict = None) -> bool:
        """Import devices from a single scan file"""
        logger.info(f"Processing scan file: {scan_file}")

        try:
            with open(scan_file, 'r', encoding='utf-8') as f:
                scan_data = json.load(f)

            devices = scan_data.get('devices', {})
            logger.info(f"Found {len(devices)} devices in scan file")

            for device_id, device_data in devices.items():
                self.stats['devices_processed'] += 1

                # Apply filters if specified
                if filters and not self._passes_filters(device_data, filters):
                    self.stats['devices_skipped'] += 1
                    continue

                # Parse device
                device = self.parse_device_from_scan(device_id, device_data)
                if not device:
                    self.stats['devices_skipped'] += 1
                    continue

                # Import device (each device commits immediately)
                self.import_device(device)

                # Add small delay to prevent overwhelming the database
                if not self.dry_run and self.stats['devices_processed'] % 100 == 0:
                    time.sleep(0.01)  # 10ms pause every 100 devices

            return True

        except Exception as e:
            logger.error(f"Error processing scan file {scan_file}: {e}")
            return False

    def _passes_filters(self, device_data: Dict, filters: Dict) -> bool:
        """Check if device passes filter criteria"""

        # Vendor filter
        vendor_filter = filters.get('vendors')
        if vendor_filter:
            device_vendor = self.normalize_vendor(device_data.get('vendor', ''))
            if device_vendor not in vendor_filter:
                return False

        # Device type filter
        type_filter = filters.get('device_types')
        if type_filter:
            device_type = device_data.get('device_type', '')
            if device_type not in type_filter:
                return False

        # Confidence threshold filter
        min_confidence = filters.get('min_confidence')
        if min_confidence:
            confidence = device_data.get('confidence_score', 0)
            if confidence < min_confidence:
                return False

        # Site filter (based on IP or hostname)
        site_filter = filters.get('sites')
        if site_filter:
            hostname = device_data.get('sys_name', '')
            primary_ip = device_data.get('primary_ip', '')
            site_code = self.extract_site_code(hostname, primary_ip)
            if site_code not in site_filter:
                return False

        return True

    def import_scan_directory(self, scan_dir: str, filters: Dict = None) -> None:
        """Import all scan files from directory"""
        scan_dir_path = Path(scan_dir)

        if not scan_dir_path.exists():
            logger.error(f"Scan directory not found: {scan_dir}")
            return

        scan_files = list(scan_dir_path.glob("*.json"))
        logger.info(f"Found {len(scan_files)} scan files in {scan_dir}")

        for scan_file in scan_files:
            logger.info(f"Processing: {scan_file.name}")
            self.import_scan_file(str(scan_file), filters)

        self.print_summary()

    def print_summary(self):
        """Print import summary statistics"""
        logger.info("=" * 60)
        logger.info("IMPORT SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Devices processed:    {self.stats['devices_processed']:,}")
        logger.info(f"Devices imported:     {self.stats['devices_imported']:,}")
        logger.info(f"Devices updated:      {self.stats['devices_updated']:,}")
        logger.info(f"Devices skipped:      {self.stats['devices_skipped']:,}")
        logger.info(f"Duplicates found:     {self.stats['duplicates_found']:,}")
        logger.info(f"Errors encountered:   {self.stats['errors']:,}")
        logger.info("=" * 60)

        if self.dry_run:
            logger.info("*** DRY RUN MODE - No changes were made to the database ***")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Import SNMP discovery scan data into NAPALM CMDB',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run import of all scan files
  python db_scan_import.py --scan-dir scans --dry-run

  # Import only UPS and printer devices with high confidence
  python db_scan_import.py --scan-dir scans --device-types ups,printer --min-confidence 70

  # Import specific vendors from single file
  python db_scan_import.py --scan-file scan_results.json --vendors apc,lexmark,xerox

  # Import only FRC site devices
  python db_scan_import.py --scan-dir scans --sites FRC --dry-run
        """
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--scan-file', help='Single scan file to import')
    input_group.add_argument('--scan-dir', help='Directory containing scan files')

    # Database options
    parser.add_argument('--db-path', default='napalm_cmdb.db',
                        help='Path to CMDB database file (default: napalm_cmdb.db)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be imported without making changes')

    # Filter options
    parser.add_argument('--vendors', help='Comma-separated list of vendors to include (e.g., apc,lexmark)')
    parser.add_argument('--device-types', help='Comma-separated list of device types (e.g., ups,printer,camera)')
    parser.add_argument('--sites', help='Comma-separated list of site codes (e.g., FRC,USC)')
    parser.add_argument('--min-confidence', type=int, help='Minimum confidence score (0-100)')

    # Logging options
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--quiet', action='store_true', help='Reduce output (errors only)')

    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.ERROR)

    # Build filters
    filters = {}
    if args.vendors:
        filters['vendors'] = [v.strip().lower() for v in args.vendors.split(',')]
    if args.device_types:
        filters['device_types'] = [t.strip().lower() for t in args.device_types.split(',')]
    if args.sites:
        filters['sites'] = [s.strip().upper() for s in args.sites.split(',')]
    if args.min_confidence:
        filters['min_confidence'] = args.min_confidence

    # Log filter configuration
    if filters:
        logger.info("Filter configuration:")
        for key, value in filters.items():
            logger.info(f"  {key}: {value}")

    # Initialize importer
    importer = ScanImporter(args.db_path, dry_run=args.dry_run)

    # Process files
    if args.scan_file:
        if not os.path.exists(args.scan_file):
            logger.error(f"Scan file not found: {args.scan_file}")
            sys.exit(1)
        importer.import_scan_file(args.scan_file, filters)
        importer.print_summary()
    else:
        importer.import_scan_directory(args.scan_dir, filters)


if __name__ == '__main__':
    main()