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
import yaml

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


class VendorFingerprintManager:
    """Manages vendor fingerprint detection and device classification"""

    def __init__(self, fingerprint_file: str = 'vendor_fingerprints.yaml'):
        self.fingerprints = {}
        self.vendors = {}
        self.detection_rules = {}

        try:
            with open(fingerprint_file, 'r') as f:
                self.fingerprints = yaml.safe_load(f)

            self.vendors = self.fingerprints.get('vendors', {})
            self.detection_rules = self.fingerprints.get('detection_rules', {})

            logger.info(f"Loaded {len(self.vendors)} vendor fingerprints from {fingerprint_file}")

        except FileNotFoundError:
            logger.warning(f"Vendor fingerprints file not found: {fingerprint_file}")
            logger.warning("Using fallback detection methods")
        except Exception as e:
            logger.error(f"Error loading vendor fingerprints: {e}")
            logger.warning("Using fallback detection methods")

    def detect_vendor_from_snmp(self, snmp_data_by_ip: Dict, sys_descr: str = '') -> Tuple[str, int, Dict]:
        """
        Detect vendor from SNMP data using fingerprints
        Returns: (vendor, confidence_score, extracted_data)
        """
        if not self.vendors:
            return self._fallback_vendor_detection(sys_descr)

        best_vendor = 'unknown'
        best_confidence = 0
        extracted_data = {}

        # Combine all SNMP data from all IPs
        all_snmp_data = {}
        for ip, snmp_data in snmp_data_by_ip.items():
            if isinstance(snmp_data, dict):
                all_snmp_data.update(snmp_data)

        sys_descr_lower = sys_descr.lower()

        # Check vendors in priority order
        priority_order = self.detection_rules.get('priority_order', list(self.vendors.keys()))

        for vendor_key in priority_order:
            if vendor_key not in self.vendors:
                continue

            vendor_config = self.vendors[vendor_key]
            confidence = self._calculate_vendor_confidence(vendor_config, all_snmp_data, sys_descr_lower)

            if confidence > best_confidence:
                best_confidence = confidence
                best_vendor = vendor_key
                extracted_data = self._extract_vendor_data(vendor_config, all_snmp_data)

        return best_vendor, best_confidence, extracted_data

    def _calculate_vendor_confidence(self, vendor_config: Dict, snmp_data: Dict, sys_descr: str) -> int:
        """Calculate confidence score for vendor match"""
        confidence = 0

        # Check detection patterns in system description
        detection_patterns = vendor_config.get('detection_patterns', [])
        for pattern in detection_patterns:
            if pattern.lower() in sys_descr:
                confidence += 30
                break

        # Check exclusion patterns (disqualify if found)
        exclusion_patterns = vendor_config.get('exclusion_patterns', [])
        for pattern in exclusion_patterns:
            if pattern.lower() in sys_descr:
                return 0  # Disqualified

        # Check vendor-specific OIDs
        fingerprint_oids = vendor_config.get('fingerprint_oids', [])

        for oid_config in fingerprint_oids:
            oid = oid_config['oid']
            is_definitive = oid_config.get('definitive', False)
            priority = oid_config.get('priority', 2)

            # Check if OID exists in SNMP data
            if oid in snmp_data:
                value = snmp_data[oid]
                if value and value != '<nil>' and str(value).strip():
                    if is_definitive:
                        confidence += 50
                    else:
                        confidence += (25 if priority == 1 else 15)

        # Check OID patterns in SNMP data keys
        oid_patterns = vendor_config.get('oid_patterns', [])
        for pattern in oid_patterns:
            for oid_key in snmp_data.keys():
                if pattern in oid_key:
                    confidence += 10
                    break

        # Bonus for enterprise OID match
        enterprise_oid = vendor_config.get('enterprise_oid')
        if enterprise_oid:
            sys_oid = snmp_data.get('1.3.6.1.2.1.1.2.0', '')
            if enterprise_oid in str(sys_oid):
                confidence += 40

        return min(confidence, 100)  # Cap at 100

    def _extract_vendor_data(self, vendor_config: Dict, snmp_data: Dict) -> Dict:
        """Extract vendor-specific data from SNMP"""
        extracted = {}

        fingerprint_oids = vendor_config.get('fingerprint_oids', [])

        for oid_config in fingerprint_oids:
            oid = oid_config['oid']
            name = oid_config['name']

            if oid in snmp_data:
                value = snmp_data[oid]
                if value and value != '<nil>' and str(value).strip():
                    extracted[name] = str(value).strip()

        return extracted

    def _fallback_vendor_detection(self, sys_descr: str) -> Tuple[str, int, Dict]:
        """Fallback vendor detection from system description"""
        sys_descr_lower = sys_descr.lower()

        # Fallback patterns
        fallback_patterns = {
            'cisco': ['cisco', 'ios', 'catalyst', 'nexus'],
            'hp': ['hewlett', 'packard'],
            'hpe': ['hewlett packard enterprise'],
            'dell': ['dell'],
            'juniper': ['juniper'],
            'arista': ['arista'],
            'fortinet': ['fortinet', 'fortigate'],
            'palo_alto': ['palo alto'],
            'apc': ['apc', 'schneider'],
            'lexmark': ['lexmark'],
            'zebra': ['zebra'],
            'aruba': ['aruba', 'arubaos']
        }

        for vendor, patterns in fallback_patterns.items():
            for pattern in patterns:
                if pattern in sys_descr_lower:
                    return vendor, 40, {}  # Medium confidence

        return 'unknown', 0, {}

    def detect_device_type(self, vendor: str, sys_descr: str, original_type: str) -> str:
        """Detect device type using fingerprint rules"""
        if not self.vendors or vendor not in self.vendors:
            return self._fallback_device_type_detection(sys_descr, original_type)

        vendor_config = self.vendors[vendor]
        sys_descr_lower = sys_descr.lower()

        # Check for server/OS patterns first (highest priority)
        if self._is_server_device(sys_descr_lower):
            # BUT - if it's a known printer vendor with printer patterns, override server detection
            if vendor in ['lexmark', 'zebra', 'hp_printer'] or any(
                    printer_pattern in sys_descr_lower for printer_pattern in [
                        'printer', 'laserjet', 'officejet', 'deskjet', 'mx822', 'mx820', 'cx921', 'cx923', 'ms415'
                    ]):
                logger.info(f"Overriding server detection for printer device: {sys_descr[:50]}...")
                return 'printer'
            return 'server'

        # Check device type overrides
        type_overrides = vendor_config.get('device_type_overrides', {})
        for override_type, patterns in type_overrides.items():
            for pattern in patterns:
                if pattern.lower() in sys_descr_lower:
                    logger.debug(f"Device type override matched: {pattern} -> {override_type}")
                    return override_type

        # Check vendor's supported device types with sys_descr pattern matching
        supported_types = vendor_config.get('device_types', [])

        # Enhanced pattern matching for vendor-specific device types
        if vendor == 'lexmark':
            # Lexmark is always a printer
            return 'printer'
        elif vendor == 'zebra':
            # Zebra is thermal/label printer
            return 'thermal_printer'
        elif vendor == 'apc':
            if 'ups' in sys_descr_lower or 'smart-ups' in sys_descr_lower:
                return 'ups'
            elif 'pdu' in sys_descr_lower:
                return 'pdu'
        elif vendor == 'aruba':
            if 'ssr' in sys_descr_lower or ') ssr' in sys_descr_lower:
                return 'access_point'
            elif 'mobility controller' in sys_descr_lower:
                return 'wireless_controller'
            elif 'switch' in sys_descr_lower or 'procurve' in sys_descr_lower:
                return 'switch'

        # Map sys_descr patterns to device types
        type_mappings = {
            'firewall': ['firewall', 'asa', 'fortigate'],
            'switch': ['switch', 'catalyst', 'nexus'],
            'router': ['router', 'isr', 'asr'],
            'access_point': ['access point', 'ap-', 'instant', 'ssr'],
            'wireless_controller': ['wireless controller', 'mobility controller'],
            'ups': ['ups', 'smart-ups', 'back-ups'],
            'printer': ['printer', 'laserjet', 'officejet', 'lexmark', 'zebra']
        }

        for device_type, patterns in type_mappings.items():
            if device_type in supported_types:
                for pattern in patterns:
                    if pattern in sys_descr_lower:
                        logger.debug(f"Device type pattern matched: {pattern} -> {device_type}")
                        return device_type

        # If original type is supported by vendor, use it
        if original_type in supported_types:
            return original_type

        # Default to first supported type
        if supported_types:
            logger.debug(f"Using first supported type for {vendor}: {supported_types[0]}")
            return supported_types[0]

        return original_type

    def _is_server_device(self, sys_descr_lower: str) -> bool:
        """Check if device is a server/computer based on OS patterns"""
        # Don't classify printers as servers even if they run embedded Linux
        if any(printer_pattern in sys_descr_lower for printer_pattern in [
            'printer', 'laserjet', 'officejet', 'deskjet', 'lexmark', 'zebra', 'mx822', 'mx820', 'cx921', 'cx923',
            'ms415'
        ]):
            return False

        server_patterns = [
            'linux', 'ubuntu', 'centos', 'red hat', 'debian', 'suse',
            'windows', 'microsoft', 'win32', 'win64',
            'freebsd', 'openbsd', 'netbsd',
            'solaris', 'aix', 'hp-ux',
            'darwin', 'macos', 'mac os',
            'kernel', 'release:', 'machine:x86_64', 'machine:i386',
            'vmware', 'esxi', 'vcenter', 'vsphere'
        ]

        return any(pattern in sys_descr_lower for pattern in server_patterns)

    def _fallback_device_type_detection(self, sys_descr: str, original_type: str) -> str:
        """Fallback device type detection"""
        if not sys_descr:
            return original_type

        sys_descr_lower = sys_descr.lower()

        # Check for server first
        if self._is_server_device(sys_descr_lower):
            return 'server'

        # Generic patterns
        type_patterns = {
            'firewall': ['firewall'],
            'router': ['router'],
            'switch': ['switch'],
            'printer': ['printer'],
            'ups': ['ups'],
            'access_point': ['access point', 'ap-'],
            'wireless_controller': ['wireless controller']
        }

        for device_type, patterns in type_patterns.items():
            for pattern in patterns:
                if pattern in sys_descr_lower:
                    return device_type

        return original_type


class ScanImporter:
    """Main import tool for scan data"""

    def __init__(self, db_path: str, fingerprint_file: str = 'vendor_fingerprints.yaml', dry_run: bool = False):
        self.db_path = db_path
        self.dry_run = dry_run
        self.fingerprint_manager = VendorFingerprintManager(fingerprint_file)

        self.stats = {
            'devices_processed': 0,
            'devices_imported': 0,
            'devices_updated': 0,
            'devices_skipped': 0,
            'duplicates_found': 0,
            'errors': 0
        }

        # Build device type mappings from fingerprints or use fallback
        self.device_role_mapping = self._build_device_role_mapping()

        # Build vendor mappings from fingerprints or use fallback
        self.vendor_mapping = self._build_vendor_mapping()

        if not self.dry_run:
            self._init_database()

    def _build_device_role_mapping(self) -> Dict[str, str]:
        """Build device role mapping from fingerprints or fallback"""
        mapping = {}

        # Extract device types from fingerprints
        if self.fingerprint_manager.vendors:
            for vendor_config in self.fingerprint_manager.vendors.values():
                device_types = vendor_config.get('device_types', [])
                for device_type in device_types:
                    if device_type not in mapping:
                        # Map device types to database roles
                        if device_type in ['switch', 'router', 'firewall', 'server', 'printer', 'ups', 'camera']:
                            mapping[device_type] = device_type
                        elif device_type in ['access_point', 'wireless_controller']:
                            mapping[device_type] = 'wireless'
                        elif device_type in ['sdwan_gateway', 'edge_device']:
                            mapping[device_type] = 'router'
                        elif device_type in ['thermal_printer', 'label_printer', 'multifunction_printer']:
                            mapping[device_type] = 'printer'
                        elif device_type in ['pdu']:
                            mapping[device_type] = 'ups'
                        else:
                            mapping[device_type] = 'unknown'

        # Fallback mappings
        fallback_mapping = {
            'router': 'router',
            'switch': 'switch',
            'firewall': 'firewall',
            'ups': 'ups',
            'pdu': 'ups',
            'printer': 'printer',
            'camera': 'camera',
            'server': 'server',
            'wireless_controller': 'wireless',
            'access_point': 'wireless',
            'sdwan': 'router',
            'sdwan_gateway': 'router',
            'load_balancer': 'load_balancer',
            'label_printer': 'printer',
            'thermal_printer': 'printer',
            'unknown': 'unknown'
        }

        # Merge with fallback
        for key, value in fallback_mapping.items():
            if key not in mapping:
                mapping[key] = value

        return mapping

    def _build_vendor_mapping(self) -> Dict[str, str]:
        """Build vendor mapping from fingerprints or fallback"""
        mapping = {}

        # Extract display names from fingerprints
        if self.fingerprint_manager.vendors:
            for vendor_key, vendor_config in self.fingerprint_manager.vendors.items():
                display_name = vendor_config.get('display_name', vendor_key)

                # Add detection patterns as mappings
                detection_patterns = vendor_config.get('detection_patterns', [])
                for pattern in detection_patterns:
                    mapping[pattern.lower()] = vendor_key

                # Add vendor key itself
                mapping[vendor_key.lower()] = vendor_key

                # Add simplified display name
                mapping[display_name.lower()] = vendor_key

        # Fallback mappings
        fallback_mapping = {
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
            'arista networks': 'arista',
            'aruba networks': 'aruba',
            'zebra technologies': 'zebra'
        }

        # Merge with fallback
        for key, value in fallback_mapping.items():
            if key not in mapping:
                mapping[key] = value

        return mapping

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
            timeout=60.0,
            isolation_level=None
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def normalize_scan_data(self, scan_data: Dict) -> Dict:
        """Normalize different scan data formats to expected format"""

        # Handle results array format (like your Aruba JSON)
        if 'results' in scan_data and isinstance(scan_data['results'], list):
            devices = {}
            for i, result in enumerate(scan_data['results']):
                # Generate device ID from IP or index
                device_id = result.get('ip_address', f"device_{i}")

                # Convert result format to expected device format
                device_data = {
                    'sys_name': result.get('sys_name', ''),
                    'sys_descr': result.get('sys_descr', ''),
                    'vendor': result.get('vendor', ''),
                    'model': result.get('model', ''),
                    'serial_number': result.get('serial_number', ''),
                    'device_type': result.get('device_type', 'unknown'),
                    'os_version': result.get('os_version', ''),
                    'primary_ip': result.get('ip_address', ''),
                    'all_ips': [result.get('ip_address', '')],
                    'mac_addresses': result.get('mac_addresses', []),
                    'snmp_data_by_ip': {
                        result.get('ip_address', ''): result.get('snmp_data', {})
                    },
                    'confidence_score': result.get('confidence_score', 50),
                    'detection_method': result.get('detection_method', 'snmp_scan'),
                    'first_seen': result.get('scan_timestamp', datetime.now(timezone.utc).isoformat()),
                    'last_seen': result.get('scan_timestamp', datetime.now(timezone.utc).isoformat()),
                    'interfaces': {}
                }
                devices[device_id] = device_data

            logger.info(f"Converted results array format to devices format: {len(devices)} devices")
            return {'devices': devices}

        # Return as-is if already in expected format
        return scan_data

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

        # APC patterns
        if vendor == 'apc' or 'apc' in sys_descr.lower():
            # Extract MN: (Model Number) field
            mn_match = re.search(r'MN:([A-Z0-9]+)', sys_descr, re.IGNORECASE)
            if mn_match:
                return mn_match.group(1)

            # Look for other APC model patterns
            apc_patterns = [
                r'Smart-UPS\s+(\d+[A-Z]*)',
                r'Back-UPS\s+([A-Z0-9]+)',
                r'Symmetra\s+([A-Z0-9]+)'
            ]

            for pattern in apc_patterns:
                match = re.search(pattern, sys_descr, re.IGNORECASE)
                if match:
                    return match.group(1)

        # Aruba patterns
        elif vendor == 'aruba' or 'aruba' in sys_descr.lower():
            aruba_patterns = [
                r'model:\s*(\d+[a-z]*)\)',
                r'model:\s*([a-z0-9-]+)\)',
                r'aruba\s+([a-z0-9-]+)',
                r'ap-(\d+[a-z]*)',
                r'(\d{3,4}[a-z]*)\s+series'
            ]

            for pattern in aruba_patterns:
                match = re.search(pattern, sys_descr, re.IGNORECASE)
                if match:
                    model = match.group(1)
                    if model.isdigit() or re.match(r'\d+[a-z]*', model):
                        return model.upper()
                    return model

        # Palo Alto Networks patterns
        elif vendor == 'palo_alto' or 'palo alto' in sys_descr.lower():
            pa_patterns = [
                r'PA-(\d+[A-Z]*)\s+series',
                r'PA-(\d+[A-Z]*)\s+firewall',
                r'VM-(\d+)\s+series',
                r'VM-(\d+)\s+firewall',
                r'PA-(\d+[A-Z]*)',
                r'VM-(\d+)'
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
            cisco_patterns = [
                r'C(\d+[A-Z]*)[^a-zA-Z]',
                r'ASA\s+(\d+[A-Z]*)',
                r'ISR(\d+[A-Z]*)',
                r'ASR(\d+[A-Z]*)',
                r'WS-C(\d+[A-Z-]*)',
                r'Catalyst\s+(\d+[A-Z-]*)'
            ]

            for pattern in cisco_patterns:
                match = re.search(pattern, sys_descr, re.IGNORECASE)
                if match:
                    model_num = match.group(1)
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

        # Generic patterns for other vendors
        else:
            generic_patterns = [
                r'(\b[A-Z]{2,4}-\d+[A-Z]*)',
                r'(\b\d+[A-Z]+\b)',
                r'(\b[A-Z]+\d+[A-Z-]*)'
            ]

            for pattern in generic_patterns:
                match = re.search(pattern, sys_descr)
                if match:
                    return match.group(1)

        return None

    def extract_enhanced_device_info(self, device_data: Dict, snmp_data_by_ip: Dict,
                                     vendor_extracted_data: Dict = None) -> Dict:
        """Extract enhanced device information from SNMP data and fingerprint data"""
        enhanced = {}

        # Combine all SNMP data from all IPs
        all_snmp_data = {}
        for ip, snmp_data in snmp_data_by_ip.items():
            if isinstance(snmp_data, dict):
                all_snmp_data.update(snmp_data)

        # First try vendor-specific extracted data from fingerprints
        if vendor_extracted_data:
            # Look for model in vendor-extracted data
            model_keys = [k for k in vendor_extracted_data.keys() if 'model' in k.lower()]
            if model_keys:
                enhanced['model'] = vendor_extracted_data[model_keys[0]]
                enhanced['model_source'] = 'fingerprint_specific'

            # Look for serial in vendor-extracted data
            serial_keys = [k for k in vendor_extracted_data.keys() if 'serial' in k.lower()]
            if serial_keys:
                enhanced['serial_number'] = vendor_extracted_data[serial_keys[0]]
                enhanced['serial_source'] = 'fingerprint_specific'

            # Look for version in vendor-extracted data
            version_keys = [k for k in vendor_extracted_data.keys() if
                            any(term in k.lower() for term in ['version', 'firmware', 'software'])]
            if version_keys:
                enhanced['os_version'] = vendor_extracted_data[version_keys[0]]
                enhanced['version_source'] = 'fingerprint_specific'

        # Fall back to generic SNMP field extraction
        if not enhanced.get('model'):
            model = device_data.get('model', '').strip()
            if not model:
                model_candidates = [
                    all_snmp_data.get('Entity Model Name'),
                    all_snmp_data.get('Cisco Model'),
                    all_snmp_data.get('APC Model Number'),
                    all_snmp_data.get('APC Model Number 2'),
                    all_snmp_data.get('Aruba Model'),
                    all_snmp_data.get('HP Model')
                ]

                for candidate in model_candidates:
                    if candidate and candidate != '<nil>' and candidate.strip():
                        model = candidate.strip()
                        enhanced['model_source'] = 'snmp_generic'
                        break

            enhanced['model'] = model

        if not enhanced.get('serial_number'):
            serial_number = device_data.get('serial_number', '').strip()
            if not serial_number:
                serial_candidates = [
                    all_snmp_data.get('Entity Serial Number'),
                    all_snmp_data.get('Cisco Serial Number'),
                    all_snmp_data.get('APC Serial Number'),
                    all_snmp_data.get('Serial Number')
                ]

                for candidate in serial_candidates:
                    if candidate and candidate != '<nil>' and candidate.strip():
                        serial_number = candidate.strip()
                        enhanced['serial_source'] = 'snmp_generic'
                        break

            enhanced['serial_number'] = serial_number

        if not enhanced.get('os_version'):
            os_version = device_data.get('os_version', '').strip()
            if not os_version:
                version_candidates = [
                    all_snmp_data.get('Cisco IOS Version String'),
                    all_snmp_data.get('Entity Software Revision'),
                    all_snmp_data.get('APC Firmware Version'),
                    all_snmp_data.get('Software Version')
                ]

                for candidate in version_candidates:
                    if candidate and candidate != '<nil>' and candidate.strip():
                        os_version = candidate.strip()
                        enhanced['version_source'] = 'snmp_generic'
                        break

            enhanced['os_version'] = os_version

        # Extract hardware revision
        hw_revision = all_snmp_data.get('Entity Hardware Revision', '').strip()
        if hw_revision and hw_revision != '<nil>':
            enhanced['hardware_revision'] = hw_revision

        return enhanced

    def should_skip_device(self, device_data: Dict, sys_descr: str) -> Tuple[bool, str]:
        """Determine if a device should be skipped based on fingerprint rules"""

        # Use fingerprint manager to detect if it's a server
        if self.fingerprint_manager._is_server_device(sys_descr.lower()):
            vendor = device_data.get('vendor', '').lower()
            device_type = device_data.get('device_type', '').lower()

            # Skip if it's misidentified as a network device
            if device_type in ['switch', 'router', 'firewall']:
                return True, f"Misidentified server (vendor={vendor}, type={device_type}, but sys_descr shows OS: {sys_descr[:50]}...)"

        # Check for generic/unhelpful system descriptions
        if sys_descr:
            sys_descr_lower = sys_descr.lower()
            if any(pattern in sys_descr_lower for pattern in [
                'no description available',
                'unknown device',
                'generic snmp device'
            ]):
                return True, f"Generic/unhelpful system description: {sys_descr[:50]}..."

        return False, ""

    def parse_device_from_scan(self, device_id: str, device_data: Dict) -> Optional[ImportedDevice]:
        """Parse device data from scan format into ImportedDevice"""
        try:
            # Extract SNMP data - handle both formats
            snmp_data_by_ip = device_data.get('snmp_data_by_ip', {})

            # If no snmp_data_by_ip, try to construct from snmp_data + ip_address
            if not snmp_data_by_ip and 'snmp_data' in device_data:
                ip_address = device_data.get('ip_address', device_data.get('primary_ip', ''))
                if ip_address:
                    snmp_data_by_ip = {ip_address: device_data['snmp_data']}
                    logger.debug(f"Constructed snmp_data_by_ip for {device_id} from snmp_data")

            # Get sys_name and sys_descr from device_data or SNMP
            sys_name = device_data.get('sys_name', '').strip()
            sys_descr = device_data.get('sys_descr', '').strip()

            # Try to extract from SNMP data if missing
            if not sys_name or not sys_descr:
                for ip, snmp_info in snmp_data_by_ip.items():
                    if not sys_name:
                        snmp_sys_name = snmp_info.get('1.3.6.1.2.1.1.5.0', '').strip()
                        if snmp_sys_name and snmp_sys_name != '<nil>' and snmp_sys_name != ip:
                            sys_name = snmp_sys_name
                            logger.debug(f"Found sys_name in SNMP data for {device_id}: {sys_name}")

                    if not sys_descr:
                        snmp_sys_descr = snmp_info.get('1.3.6.1.2.1.1.1.0', '').strip()
                        if snmp_sys_descr and snmp_sys_descr != '<nil>':
                            sys_descr = snmp_sys_descr
                            logger.debug(f"Found sys_descr in SNMP data for {device_id}: {sys_descr[:50]}...")

            # Skip devices with no useful SNMP information
            if not sys_name and not sys_descr:
                logger.warning(f"Skipping device {device_id}: no sys_name or sys_descr available")
                return None

            # Quality checks
            if sys_name and sys_name.lower() in ['unknown', 'null', 'none', '']:
                sys_name = ''
            if sys_descr and sys_descr.lower() in ['unknown', 'null', 'none', '']:
                sys_descr = ''

            if not sys_name and not sys_descr:
                logger.warning(f"Skipping device {device_id}: no meaningful sys_name or sys_descr")
                return None

            # Check if we should skip this device
            should_skip, skip_reason = self.should_skip_device(device_data, sys_descr)
            if should_skip:
                logger.info(f"Skipping device {device_id}: {skip_reason}")
                return None

            # Use fingerprint manager for vendor detection
            detected_vendor, confidence, vendor_extracted_data = self.fingerprint_manager.detect_vendor_from_snmp(
                snmp_data_by_ip, sys_descr
            )

            # Use detected vendor if confidence is high enough
            original_vendor = self.normalize_vendor(device_data.get('vendor', 'unknown'))
            if confidence >= 70:
                vendor = detected_vendor
                logger.info(f"High-confidence vendor detection for {device_id}: {vendor} (confidence: {confidence}%)")
            elif confidence >= 40 and original_vendor == 'unknown':
                vendor = detected_vendor
                logger.info(f"Medium-confidence vendor detection for {device_id}: {vendor} (confidence: {confidence}%)")
            else:
                vendor = original_vendor
                if detected_vendor != 'unknown' and detected_vendor != vendor:
                    logger.info(
                        f"Vendor detection for {device_id}: keeping original={vendor} over detected={detected_vendor} (confidence: {confidence}%)")

            # Use fingerprint manager for device type detection
            device_type = device_data.get('device_type', 'unknown')
            device_type = self.fingerprint_manager.detect_device_type(vendor, sys_descr, device_type)

            # Enhanced device info extraction using fingerprint data
            enhanced_info = self.extract_enhanced_device_info(device_data, snmp_data_by_ip, vendor_extracted_data)

            # Use enhanced data if available
            model = enhanced_info.get('model', '')
            serial_number = enhanced_info.get('serial_number', '')
            os_version = enhanced_info.get('os_version', '')

            # Fall back to sys_descr extraction if no fingerprint-specific data
            if not model and sys_descr:
                model = self.extract_model_from_sys_descr(vendor, device_type, sys_descr)
                if model:
                    logger.info(f"Extracted model from sys_descr for {device_id}: {model}")

            # Clean OS version (remove common prefixes)
            if os_version:
                # Clean Cisco version strings
                if vendor == 'cisco' and os_version.startswith('CW_VERSION$'):
                    os_version = os_version.replace('CW_VERSION$', '').replace('$', '')
                    logger.debug(f"Cleaned Cisco OS version for {device_id}: {os_version}")

            # Generate serial if still missing
            hostname = sys_name or device_id
            primary_ip = device_data.get('primary_ip', device_data.get('ip_address', ''))

            if not serial_number:
                if hostname and primary_ip:
                    serial_number = f"{hostname}_{primary_ip}".replace('.', '_')
                    logger.debug(f"Generated fallback serial for {device_id}: {serial_number}")
                elif primary_ip:
                    serial_number = f"ip_{primary_ip}".replace('.', '_')
                else:
                    serial_number = device_id

            if not serial_number:
                logger.error(f"Cannot generate valid serial number for device {device_id}")
                return None

            # Generate device key
            device_key = self.generate_device_key(vendor, serial_number, model)
            site_code = self.extract_site_code(hostname, primary_ip)
            device_role = self.device_role_mapping.get(device_type, 'unknown')

            # Extract IP addresses
            all_ips = device_data.get('all_ips', [])
            if primary_ip and primary_ip not in all_ips:
                all_ips.insert(0, primary_ip)

            # Extract other data
            mac_addresses = device_data.get('mac_addresses', [])

            # Generate FQDN
            fqdn = None
            if hostname and not hostname.endswith('.') and site_code != 'UNK':
                fqdn = f"{hostname}.{site_code.lower()}.local"

            # Create detailed notes with enhancement information
            notes_parts = [f"Imported from scan data. Device type: {device_type}"]

            # Add data quality and fingerprint information
            data_quality_notes = []
            if sys_name:
                data_quality_notes.append("sys_name available")
            if sys_descr:
                data_quality_notes.append("sys_descr available")
            if confidence > 0:
                data_quality_notes.append(f"vendor confidence: {confidence}%")
            if enhanced_info.get('model_source'):
                data_quality_notes.append(f"model from {enhanced_info['model_source']}")
            if enhanced_info.get('serial_source'):
                data_quality_notes.append(f"serial from {enhanced_info['serial_source']}")
            if enhanced_info.get('version_source'):
                data_quality_notes.append(f"version from {enhanced_info['version_source']}")

            if data_quality_notes:
                notes_parts.append(f"Data quality: {', '.join(data_quality_notes)}")

            # Add hardware revision if available
            if enhanced_info.get('hardware_revision'):
                notes_parts.append(f"Hardware revision: {enhanced_info['hardware_revision']}")

            # Add fingerprint detection info
            if vendor_extracted_data:
                notes_parts.append(f"Fingerprint data: {len(vendor_extracted_data)} fields extracted")

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
                snmp_data=snmp_data_by_ip,
                confidence_score=max(device_data.get('confidence_score', 50), confidence),
                detection_method=device_data.get('detection_method', 'snmp_scan'),
                first_seen=device_data.get('first_seen',
                                           device_data.get('scan_timestamp', datetime.now(timezone.utc).isoformat())),
                last_seen=device_data.get('last_seen',
                                          device_data.get('scan_timestamp', datetime.now(timezone.utc).isoformat())),
                notes=notes
            )

            logger.info(
                f"Parsed device {device_id}: vendor={vendor}, type={device_type}, model={model}, serial={serial_number[:8]}...")
            return device

        except Exception as e:
            logger.error(f"Error parsing device {device_id}: {e}")
            return None

    def extract_site_code(self, hostname: str, primary_ip: str) -> str:
        """Extract site code from hostname - hostname patterns only"""
        if not hostname:
            hostname = ""

        hostname_lower = hostname.lower()

        # Priority 1: Look for patterns with site prefix + number (e.g., us-0548-wap-02)
        # For 2-char prefixes, combine with number for uniqueness
        site_with_number = re.match(r'^([a-z]{2,4})-(\d+)', hostname_lower)
        if site_with_number:
            site_prefix = site_with_number.group(1).upper()
            site_number = site_with_number.group(2)

            # Always combine prefix with number for uniqueness (e.g., US0548)
            return site_prefix + site_number[:4]

        # Priority 2: Look for 3+ character prefixes without numbers (e.g., frc-device, usc-switch)
        # Only accept 3+ char prefixes to avoid ambiguous 2-char codes
        site_prefix_only = re.match(r'^([a-z]{3,4})-', hostname_lower)
        if site_prefix_only:
            site_prefix = site_prefix_only.group(1).upper()
            return site_prefix

        # Fallback: Unknown site
        return 'UNK'
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

            # Validate required fields
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

            # Database transaction
            conn = None
            try:
                conn = self._get_db_connection()
                cursor = conn.cursor()

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
                    1
                ))

                device_id = cursor.lastrowid

                # Insert IP addresses
                for i, ip in enumerate(device.all_ips):
                    if ip and ip.strip():
                        cursor.execute("""
                            INSERT INTO device_ips (
                                device_id, ip_address, ip_type, is_primary, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            device_id,
                            ip,
                            'management' if i == 0 else 'secondary',
                            1 if i == 0 else 0,
                            now,
                            now
                        ))

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

            # Check by device key first
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
        """Update existing device with new information"""
        try:
            if self.dry_run:
                logger.info(f"[DRY RUN] Would update device: {device.device_name} (ID: {existing_id})")
                self.stats['devices_updated'] += 1
                return True

            conn = None
            try:
                conn = self._get_db_connection()
                cursor = conn.cursor()

                cursor.execute("BEGIN IMMEDIATE")

                update_query = """
                    UPDATE devices SET
                        device_name = ?, hostname = ?, fqdn = ?, os_version = ?,
                        device_role = ?, vendor = ?, model = ?, notes = ?,
                        last_updated = ?
                    WHERE id = ?
                """

                now = datetime.now().isoformat()

                cursor.execute(update_query, (
                    device.device_name,
                    device.hostname,
                    device.fqdn,
                    device.os_version,
                    device.device_role,  # Add device_role update
                    device.vendor,  # Add vendor update
                    device.model,  # Add model update
                    device.notes,
                    now,
                    existing_id
                ))

                # Update IP addresses
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

                cursor.execute("COMMIT")

                logger.info(
                    f"Successfully updated device: {device.device_name} (ID: {existing_id}) - Role: {device.device_role}")
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

            # Normalize scan data format FIRST
            scan_data = self.normalize_scan_data(scan_data)

            devices = scan_data.get('devices', {})
            logger.info(f"Found {len(devices)} devices in scan file")

            for device_id, device_data in devices.items():
                self.stats['devices_processed'] += 1

                # Apply filters
                if filters and not self._passes_filters(device_data, filters):
                    self.stats['devices_skipped'] += 1
                    continue

                # Parse device
                device = self.parse_device_from_scan(device_id, device_data)
                if not device:
                    self.stats['devices_skipped'] += 1
                    continue

                # Import device
                self.import_device(device)

                # Small delay
                if not self.dry_run and self.stats['devices_processed'] % 100 == 0:
                    time.sleep(0.01)

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

        # Site filter
        site_filter = filters.get('sites')
        if site_filter:
            hostname = device_data.get('sys_name', '')
            primary_ip = device_data.get('primary_ip', device_data.get('ip_address', ''))
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

    # Initialize importer with fingerprint file
    importer = ScanImporter(args.db_path, fingerprint_file='vendor_fingerprints.yaml', dry_run=args.dry_run)

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