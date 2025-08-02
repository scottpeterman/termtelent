#!/usr/bin/env python3
"""
Python SNMP Scanner - Optimized with TCP pre-filtering and v3/v2c fallback
Fast network device discovery with SNMP fingerprinting
"""

import asyncio
import json
import yaml
import ipaddress
import argparse
import sys
import time
import socket
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, asdict
from pathlib import Path

# Modern SNMP library
try:
    from pysnmp.hlapi.v3arch.asyncio import *
    from pysnmp.proto.rfc1902 import Counter32, Counter64, Gauge32, TimeTicks
except ImportError:
    print("Error: pysnmp library not found. Install with: pip install pysnmp")
    sys.exit(1)


@dataclass
class SNMPCredentials:
    """SNMP credentials configuration"""
    version: str = "v3"
    community: str = "public"
    communities: List[str] = None  # Multiple community strings for v2c fallback
    username: str = ""
    auth_protocol: str = "SHA"
    auth_key: str = ""
    priv_protocol: str = "AES"
    priv_key: str = ""
    timeout: int = 3  # Reduced from 5 to 3 seconds
    retries: int = 1  # Reduced from 2 to 1
    try_v2c_fallback: bool = True  # Try v2c if v3 fails

    def __post_init__(self):
        if self.communities is None:
            self.communities = ["public", "private"]


@dataclass
class ScanConfig:
    """Scanner configuration"""
    credentials: SNMPCredentials
    fingerprint_rules: str = "vendor_fingerprints.yaml"
    output_format: str = "json"
    concurrent_scans: int = 100  # Increased from 50
    tcp_check_timeout: int = 2  # TCP port check timeout
    tcp_check_ports: List[int] = None  # Will default to [20,21,22,25,53,80,161,443,993,995]
    skip_tcp_check: bool = False  # Option to disable TCP pre-filtering

    def __post_init__(self):
        if self.tcp_check_ports is None:
            # Include printer ports for better device discovery
            self.tcp_check_ports = [20, 21, 22, 25, 53, 80, 161, 443, 515, 631, 993, 995, 9100]


class TCPPortChecker:
    """Fast TCP port connectivity checker"""

    @staticmethod
    async def check_host_responsive(ip_address: str, ports: List[int], timeout: int = 2) -> bool:
        """
        Check if host is responsive on any of the specified ports
        Returns True if any port is open, False otherwise
        """
        if not ports:
            return True  # Skip check if no ports specified

        # Create tasks for all port checks
        tasks = []
        for port in ports:
            task = TCPPortChecker._check_single_port(ip_address, port, timeout)
            tasks.append(task)

        try:
            # Wait for any port to respond positively
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Return True if any port is open
            for result in results:
                if isinstance(result, bool) and result:
                    return True

            return False

        except Exception:
            return False

    @staticmethod
    async def _check_single_port(ip_address: str, port: int, timeout: int) -> bool:
        """Check if a single port is open"""
        try:
            # Create connection with timeout
            future = asyncio.open_connection(ip_address, port)
            reader, writer = await asyncio.wait_for(future, timeout=timeout)

            # Close connection immediately
            writer.close()
            try:
                await writer.wait_closed()
            except:
                pass

            return True

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return False
        except Exception:
            return False


class StandardOIDs:
    """Standard SNMP MIB-II OIDs and vendor-specific OIDs - Always collected"""

    # Core System Information (RFC 1213) - Most critical OIDs first
    SYSTEM_GROUP = {
        "sysDescr": "1.3.6.1.2.1.1.1.0",
        "sysName": "1.3.6.1.2.1.1.5.0",
        "sysObjectID": "1.3.6.1.2.1.1.2.0",
        "sysUpTime": "1.3.6.1.2.1.1.3.0",
        "sysContact": "1.3.6.1.2.1.1.4.0",
        "sysLocation": "1.3.6.1.2.1.1.6.0",
        "sysServices": "1.3.6.1.2.1.1.7.0"
    }

    # Entity MIB (RFC 2737) - Hardware info
    ENTITY_MIB = {
        "entPhysicalDescr": "1.3.6.1.2.1.47.1.1.1.1.2.1",
        "entPhysicalModelName": "1.3.6.1.2.1.47.1.1.1.1.13.1",
        "entPhysicalSerialNum": "1.3.6.1.2.1.47.1.1.1.1.11.1",
        "entPhysicalSoftwareRev": "1.3.6.1.2.1.47.1.1.1.1.10.1",
        "entPhysicalFirmwareRev": "1.3.6.1.2.1.47.1.1.1.1.9.1",
        "entPhysicalHardwareRev": "1.3.6.1.2.1.47.1.1.1.1.8.1",
        "entPhysicalMfgName": "1.3.6.1.2.1.47.1.1.1.1.12.1"
    }

    @classmethod
    def get_priority_oids(cls) -> Dict[str, str]:
        """Get most important OIDs first for faster detection"""
        priority_oids = {}
        priority_oids.update(cls.SYSTEM_GROUP)
        return priority_oids

    @classmethod
    def get_extended_oids(cls) -> Dict[str, str]:
        """Get extended OIDs for detailed info"""
        return cls.ENTITY_MIB


class FingerprintEngine:
    """Enhanced fingerprinting engine with pattern hierarchy"""

    def __init__(self, rules_file: str):
        self.rules = self._load_rules(rules_file)
        self.vendor_priority = self.rules.get('detection_rules', {}).get('priority_order', [])
        # Extract all fingerprint OIDs from YAML for collection
        self.fingerprint_oids = self._extract_fingerprint_oids()

    def fingerprint_device(self, snmp_data: Dict[str, str]) -> Dict[str, Any]:
        """
        Fingerprint device using OID-based detection first, then pattern matching
        Returns Go-compatible result structure
        """
        # First, check for definitive vendor OIDs from YAML config
        vendor_oid_result = self._check_definitive_oids(snmp_data)
        if vendor_oid_result['confidence_score'] > 0:
            return vendor_oid_result

        # Fall back to pattern-based detection
        return self._pattern_based_fingerprint(snmp_data)

    def get_all_fingerprint_oids(self) -> Dict[str, str]:
        """Get ALL fingerprint OIDs for collection, not just priority ones"""
        all_oids = {}
        for oid, config in self.fingerprint_oids.items():
            all_oids[oid] = config['name']
        return all_oids

    def get_priority_fingerprint_oids(self) -> Dict[str, str]:
        """Get high-priority fingerprint OIDs for collection"""
        priority_oids = {}

        # Sort by priority (lower number = higher priority)
        sorted_oids = sorted(
            self.fingerprint_oids.items(),
            key=lambda x: (x[1]['priority'], not x[1]['definitive'])
        )

        # Take top priority OIDs (priority 1-2, or definitive=True)
        for oid, config in sorted_oids:
            if config['priority'] <= 2 or config['definitive']:
                priority_oids[oid] = config['name']

        return priority_oids

    def _load_rules(self, rules_file: str) -> Dict:
        """Load fingerprint rules from YAML file"""
        try:
            with open(rules_file, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading fingerprint rules: {e}")
            return {"vendors": {}}

    def _extract_fingerprint_oids(self) -> Dict[str, Dict[str, Any]]:
        """Extract all fingerprint OIDs from YAML rules for collection"""
        fingerprint_oids = {}

        for vendor_name, vendor_config in self.rules.get('vendors', {}).items():
            fingerprint_oid_list = vendor_config.get('fingerprint_oids', [])

            for oid_config in fingerprint_oid_list:
                oid = oid_config.get('oid', '')
                name = oid_config.get('name', '')
                priority = oid_config.get('priority', 10)
                definitive = oid_config.get('definitive', False)

                if oid and name:
                    fingerprint_oids[oid] = {
                        'name': name,
                        'vendor': vendor_name,
                        'priority': priority,
                        'definitive': definitive,
                        'description': oid_config.get('description', ''),
                        'expected_values': oid_config.get('expected_values', [])
                    }

        return fingerprint_oids

    def _check_definitive_oids(self, snmp_data: Dict[str, str]) -> Dict[str, Any]:
        """Check for definitive vendor OIDs from YAML configuration"""

        # FIXED: Check vendors in priority order, not YAML file order
        for vendor_name in self.vendor_priority:
            if vendor_name not in self.rules.get('vendors', {}):
                continue

            vendor_config = self.rules['vendors'][vendor_name]
            fingerprint_oids = vendor_config.get('fingerprint_oids', [])

            # Look for definitive OIDs (marked as definitive=true)
            definitive_matches = {}
            for oid_config in fingerprint_oids:
                if not oid_config.get('definitive', False):
                    continue

                oid = oid_config.get('oid', '')
                if oid in snmp_data and snmp_data[oid]:
                    name = oid_config.get('name', '').lower()
                    value = snmp_data[oid]

                    # Check expected values if specified
                    expected_values = oid_config.get('expected_values', [])
                    if expected_values and value.lower() not in [v.lower() for v in expected_values]:
                        continue

                    definitive_matches[name] = value

            # If we found definitive OIDs for this vendor, process the result
            if definitive_matches:
                return self._process_definitive_match(vendor_name, vendor_config, definitive_matches, snmp_data)

        # No definitive OIDs found
        return {"confidence_score": 0, "vendor": "", "device_type": ""}

    def _process_definitive_match(self, vendor_name: str, vendor_config: Dict,
                                  definitive_matches: Dict[str, str], snmp_data: Dict[str, str]) -> Dict[str, Any]:
        """Process a definitive OID match and extract device info"""

        # Smart field extraction from ALL collected data
        model, serial, firmware = self._smart_field_extraction(snmp_data, vendor_config)

        # Determine device type using existing rules
        device_type = self._determine_device_type(vendor_config,
                                                  " ".join(definitive_matches.values()).lower())

        # Apply any model/serial/firmware extraction rules if smart extraction didn't find them
        if not model:
            model = self._extract_field(vendor_config, 'model_extraction',
                                        " ".join(snmp_data.values()), device_type)
        if not serial:
            serial = self._extract_field(vendor_config, 'serial_extraction',
                                         " ".join(snmp_data.values()), device_type)
        if not firmware:
            firmware = self._extract_field(vendor_config, 'firmware_extraction',
                                           " ".join(snmp_data.values()), device_type)

        return {
            "vendor": vendor_name,
            "device_type": device_type if device_type != "unknown" else "device",
            "model": model,
            "serial_number": serial,
            "os_version": firmware,
            "confidence_score": 100,
            "detection_method": "definitive_oid_match",
            "matched_oids": list(definitive_matches.keys())
        }

    def _smart_field_extraction(self, snmp_data: Dict[str, str], vendor_config: Dict) -> Tuple[str, str, str]:
        """
        Smart extraction of model, serial, and firmware from ALL OID data
        Analyzes OID names from YAML configuration to identify relevant fields
        """
        model = ""
        serial = ""
        firmware = ""

        # Get all fingerprint OIDs for this vendor to analyze their names
        vendor_fingerprint_oids = vendor_config.get('fingerprint_oids', [])

        # Create mapping of OID -> name for smart analysis
        oid_name_map = {}
        for oid_config in vendor_fingerprint_oids:
            oid = oid_config.get('oid', '')
            name = oid_config.get('name', '').lower()
            if oid and name:
                oid_name_map[oid] = name

        # Analyze collected SNMP data using OID names from YAML
        for oid, value in snmp_data.items():
            if not value or value in ["<nil>", ""]:
                continue

            # Get the descriptive name for this OID from YAML
            oid_name = oid_name_map.get(oid, "").lower()

            # Smart detection based on OID name keywords
            if not model and any(keyword in oid_name for keyword in ["model", "product", "type"]):
                model = value.strip()
            elif not serial and any(keyword in oid_name for keyword in ["serial", "serialnumber", "serial_number"]):
                serial = value.strip()
            elif not firmware and any(
                    keyword in oid_name for keyword in ["firmware", "version", "software", "os", "revision"]):
                firmware = value.strip()

        # Also check standard OID patterns for common fields
        standard_patterns = {
            # Common model OIDs
            "1.3.6.1.2.1.47.1.1.1.1.13.1": "model",  # entPhysicalModelName
            "1.3.6.1.2.1.47.1.1.1.1.7.1": "model",  # entPhysicalName
            # Common serial OIDs
            "1.3.6.1.2.1.47.1.1.1.1.11.1": "serial",  # entPhysicalSerialNum
            # Common firmware OIDs
            "1.3.6.1.2.1.47.1.1.1.1.10.1": "firmware",  # entPhysicalSoftwareRev
            "1.3.6.1.2.1.47.1.1.1.1.9.1": "firmware",  # entPhysicalFirmwareRev
        }

        for oid, field_type in standard_patterns.items():
            if oid in snmp_data and snmp_data[oid] and snmp_data[oid] not in ["<nil>", ""]:
                value = snmp_data[oid].strip()
                if field_type == "model" and not model:
                    model = value
                elif field_type == "serial" and not serial:
                    serial = value
                elif field_type == "firmware" and not firmware:
                    firmware = value

        return model, serial, firmware

    def _pattern_based_fingerprint(self, snmp_data: Dict[str, str]) -> Dict[str, Any]:
        """Original pattern-based fingerprinting as fallback"""
        # Get system description and name
        sys_descr = snmp_data.get("1.3.6.1.2.1.1.1.0", "").lower()
        sys_name = snmp_data.get("1.3.6.1.2.1.1.5.0", "").lower()

        # Combine all SNMP text for pattern matching
        all_text = f"{sys_descr} {sys_name}"
        for oid, value in snmp_data.items():
            if value and value not in ["<nil>", ""]:
                all_text += f" {str(value).lower()}"

        # Test vendors in priority order
        for vendor_name in self.vendor_priority:
            if vendor_name not in self.rules.get('vendors', {}):
                continue

            vendor_rule = self.rules['vendors'][vendor_name]
            result = self._test_vendor(vendor_name, vendor_rule, all_text, snmp_data)

            if result['confidence_score'] > 0:
                return result

        # No vendor detected
        return {
            "vendor": "",
            "device_type": "",
            "model": "",
            "serial_number": "",
            "os_version": "",
            "confidence_score": 30,
            "detection_method": "no_vendor_detected"
        }

    def _test_vendor(self, vendor_name: str, vendor_rule: Dict, all_text: str, snmp_data: Dict) -> Dict:
        """Test if device matches a specific vendor"""

        # Step 1: Check exclusion patterns (immediate disqualification)
        exclusions = vendor_rule.get('exclusion_patterns', [])
        for exclusion in exclusions:
            if exclusion.lower() in all_text:
                return {"confidence_score": 0, "vendor": "", "device_type": ""}

        confidence = 0
        matched_patterns = []
        detection_method = "pattern_match"

        # Step 2: Check definitive patterns (high confidence)
        definitive_patterns = vendor_rule.get('definitive_patterns', [])
        if not definitive_patterns:
            # Fallback to old-style detection patterns
            definitive_patterns = vendor_rule.get('detection_patterns', [])

        definitive_matches = 0
        for pattern in definitive_patterns:
            pattern_str = pattern.get('pattern', pattern) if isinstance(pattern, dict) else pattern
            if pattern_str.lower() in all_text:
                definitive_matches += 1
                matched_patterns.append(pattern_str)
                confidence += 90
                detection_method = "definitive_pattern_match"

        # Must have at least one definitive match for modern rules
        if definitive_patterns and definitive_matches == 0:
            return {"confidence_score": 0, "vendor": "", "device_type": ""}

        if confidence == 0:
            return {"confidence_score": 0, "vendor": "", "device_type": ""}

        # Step 3: Determine device type
        device_type = self._determine_device_type(vendor_rule, all_text)

        # Step 4: Extract fields
        model = self._extract_field(vendor_rule, 'model_extraction', all_text, device_type)
        serial = self._extract_field(vendor_rule, 'serial_extraction', all_text, device_type)
        version = self._extract_field(vendor_rule, 'firmware_extraction', all_text, device_type)

        # Apply confidence cap
        confidence = min(confidence, 100)

        return {
            "vendor": vendor_name,
            "device_type": device_type,
            "model": model,
            "serial_number": serial,
            "os_version": version,
            "confidence_score": confidence,
            "detection_method": detection_method,
            "matched_patterns": matched_patterns
        }

    def _determine_device_type(self, vendor_rule: Dict, all_text: str) -> str:
        """Determine device type based on patterns"""
        device_type_rules = vendor_rule.get('device_type_rules', {})

        best_type = ""
        best_score = 0

        for device_type, type_rule in device_type_rules.items():
            score = 0

            # Check definitive patterns for device type
            definitive_patterns = type_rule.get('definitive_patterns', [])
            for pattern in definitive_patterns:
                if pattern.lower() in all_text:
                    score += 100

            # Check mandatory patterns
            mandatory_patterns = type_rule.get('mandatory_patterns', [])
            mandatory_matches = 0
            for pattern in mandatory_patterns:
                if pattern.lower() in all_text:
                    mandatory_matches += 1
                    score += 50

            # If mandatory patterns exist but none matched, skip this type
            if mandatory_patterns and mandatory_matches == 0:
                continue

            # Check optional patterns
            optional_patterns = type_rule.get('optional_patterns', [])
            for pattern in optional_patterns:
                if pattern.lower() in all_text:
                    score += 20

            # Consider priority (lower number = higher priority)
            priority = type_rule.get('priority', 99)
            score += (100 - priority) * 5

            if score > best_score:
                best_score = score
                best_type = device_type

        return best_type if best_type else "unknown"

    def _extract_field(self, vendor_rule: Dict, field_type: str, all_text: str, device_type: str) -> str:
        """Extract specific field using regex patterns"""
        import re

        extraction_rules = vendor_rule.get(field_type, [])

        for rule in extraction_rules:
            # Check if rule applies to this device type
            device_types = rule.get('device_types', [])
            if device_types and device_type not in device_types:
                continue

            try:
                pattern = rule.get('regex', '')
                if not pattern:
                    continue

                match = re.search(pattern, all_text, re.IGNORECASE)
                if match:
                    capture_group = rule.get('capture_group', 1)
                    if len(match.groups()) >= capture_group:
                        extracted = match.group(capture_group).strip()
                        if extracted:
                            return extracted
            except Exception:
                continue

        return ""


class SNMPCollector:
    """Optimized async SNMP data collector with v3/v2c fallback"""

    def __init__(self, credentials: SNMPCredentials, fingerprint_engine=None):
        self.credentials = credentials
        self.engine = SnmpEngine()
        self.fingerprint_engine = fingerprint_engine

    async def collect_device_data(self, ip_address: str) -> Tuple[Dict[str, str], Dict[str, Any]]:
        """
        Collect SNMP data from device with v3/v2c fallback strategy
        Returns (snmp_data, collection_metadata)
        """
        start_time = time.time()

        snmp_data = {}
        metadata = {
            "collection_timestamp": datetime.now(timezone.utc).isoformat(),
            "snmp_version_attempted": [],
            "snmp_version_successful": "",
            "oids_attempted": [],
            "oids_successful": [],
            "oids_failed": [],
            "collection_method": "optimized_with_fallback"
        }

        # Strategy: Try v3 first if configured, then fallback to v2c communities
        versions_to_try = []

        if self.credentials.version == "v3" and self.credentials.username:
            versions_to_try.append("v3")

        # Always try v2c if fallback is enabled or if v3 is not properly configured
        if (self.credentials.try_v2c_fallback or
                self.credentials.version == "v2c" or
                not self.credentials.username):
            versions_to_try.append("v2c")

        # Try each version until we get a successful response
        for version in versions_to_try:
            metadata["snmp_version_attempted"].append(version)

            try:
                # Create transport target
                target = await UdpTransportTarget.create(
                    (ip_address, 161),
                    timeout=self.credentials.timeout,
                    retries=self.credentials.retries
                )

                if version == "v3":
                    success = await self._try_snmpv3(target, snmp_data, metadata)
                else:  # v2c
                    success = await self._try_snmpv2c(target, snmp_data, metadata)

                if success:
                    metadata["snmp_version_successful"] = version
                    break

            except Exception as e:
                metadata[f"{version}_error"] = str(e)
                continue

        # Calculate response time
        metadata["response_time_ms"] = int((time.time() - start_time) * 1000)
        metadata["oids_collected"] = len(snmp_data)

        return snmp_data, metadata

    async def _try_snmpv3(self, target, snmp_data: Dict[str, str], metadata: Dict) -> bool:
        """Try SNMPv3 authentication"""
        try:
            auth_data = self._create_v3_auth()

            # Test with critical OIDs first
            critical_oids = [
                ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0")),  # sysDescr
                ObjectType(ObjectIdentity("1.3.6.1.2.1.1.5.0"))  # sysName
            ]

            error_indication, error_status, error_index, var_binds = await get_cmd(
                self.engine, auth_data, target, ContextData(), *critical_oids
            )

            if error_indication:
                metadata["v3_error_indication"] = str(error_indication)
                return False

            if error_status:
                metadata["v3_error_status"] = str(error_status)
                return False

            # Process successful v3 response
            success = False
            if var_binds:
                var_bind_list = list(var_binds) if hasattr(var_binds, '__iter__') else [var_binds]
                for oid_obj, value in var_bind_list:
                    if not isinstance(value, (NoSuchObject, NoSuchInstance, EndOfMibView)):
                        snmp_data[str(oid_obj)] = str(value)
                        metadata["oids_successful"].append(str(oid_obj))
                        success = True

            if success:
                # Collect remaining OIDs with v3
                await self._collect_remaining_oids_v3(auth_data, target, snmp_data, metadata)
                return True

            return False

        except Exception as e:
            metadata["v3_exception"] = str(e)
            return False

    async def _try_snmpv2c(self, target, snmp_data: Dict[str, str], metadata: Dict) -> bool:
        """Try SNMPv2c with multiple community strings"""
        communities_to_try = self.credentials.communities.copy()

        # If a specific community was set, try it first
        if self.credentials.community and self.credentials.community not in communities_to_try:
            communities_to_try.insert(0, self.credentials.community)

        for community in communities_to_try:
            try:
                auth_data = CommunityData(community)

                # Test with critical OIDs
                critical_oids = [
                    ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0")),  # sysDescr
                    ObjectType(ObjectIdentity("1.3.6.1.2.1.1.5.0"))  # sysName
                ]

                error_indication, error_status, error_index, var_binds = await get_cmd(
                    self.engine, auth_data, target, ContextData(), *critical_oids
                )

                if error_indication or error_status:
                    metadata[f"v2c_{community}_error"] = str(error_indication or error_status)
                    continue

                # Process successful v2c response
                success = False
                if var_binds:
                    var_bind_list = list(var_binds) if hasattr(var_binds, '__iter__') else [var_binds]
                    for oid_obj, value in var_bind_list:
                        if not isinstance(value, (NoSuchObject, NoSuchInstance, EndOfMibView)):
                            snmp_data[str(oid_obj)] = str(value)
                            metadata["oids_successful"].append(str(oid_obj))
                            success = True

                if success:
                    metadata["successful_community"] = community
                    # Collect remaining OIDs with successful community
                    await self._collect_remaining_oids_v2c(auth_data, target, snmp_data, metadata)
                    return True

            except Exception as e:
                metadata[f"v2c_{community}_exception"] = str(e)
                continue

        return False

    async def _collect_remaining_oids_v3(self, auth_data, target, snmp_data: Dict[str, str], metadata: Dict):
        """Collect remaining standard OIDs with v3"""
        remaining_oids = StandardOIDs.get_priority_oids()

        # Remove already collected OIDs
        for oid in list(snmp_data.keys()):
            oid_name = None
            for name, oid_val in remaining_oids.items():
                if oid_val == oid:
                    oid_name = name
                    break
            if oid_name:
                remaining_oids.pop(oid_name, None)

        await self._collect_standard_oids(auth_data, target, remaining_oids, snmp_data, metadata)

        # Try extended OIDs if we have good response
        if len(snmp_data) >= 2:
            extended_oids = StandardOIDs.get_extended_oids()
            await self._collect_extended_oids(auth_data, target, extended_oids, snmp_data, metadata)

            # Collect vendor-specific fingerprint OIDs from YAML
            if self.fingerprint_engine:
                fingerprint_oids = self.fingerprint_engine.get_all_fingerprint_oids()
                await self._collect_fingerprint_oids(auth_data, target, fingerprint_oids, snmp_data, metadata)

    async def _collect_remaining_oids_v2c(self, auth_data, target, snmp_data: Dict[str, str], metadata: Dict):
        """Collect remaining standard OIDs with v2c"""
        remaining_oids = StandardOIDs.get_priority_oids()

        # Remove already collected OIDs
        for oid in list(snmp_data.keys()):
            oid_name = None
            for name, oid_val in remaining_oids.items():
                if oid_val == oid:
                    oid_name = name
                    break
            if oid_name:
                remaining_oids.pop(oid_name, None)

        await self._collect_standard_oids(auth_data, target, remaining_oids, snmp_data, metadata)

        # Try extended OIDs if we have good response
        if len(snmp_data) >= 2:
            extended_oids = StandardOIDs.get_extended_oids()
            await self._collect_extended_oids(auth_data, target, extended_oids, snmp_data, metadata)

            # Collect vendor-specific fingerprint OIDs from YAML
            if self.fingerprint_engine:
                fingerprint_oids = self.fingerprint_engine.get_all_fingerprint_oids()
                await self._collect_fingerprint_oids(auth_data, target, fingerprint_oids, snmp_data, metadata)

    async def _collect_standard_oids(self, auth_data, target, oids: Dict[str, str],
                                     snmp_data: Dict[str, str], metadata: Dict):
        """Collect standard OIDs efficiently"""
        # Try to collect multiple OIDs at once
        object_types = []
        for name, oid in oids.items():
            if oid not in snmp_data:  # Don't re-collect
                object_types.append(ObjectType(ObjectIdentity(oid)))
                metadata["oids_attempted"].append(oid)

        if not object_types:
            return

        try:
            error_indication, error_status, error_index, var_binds = await get_cmd(
                self.engine, auth_data, target, ContextData(), *object_types
            )

            if not error_indication and not error_status and var_binds:
                var_bind_list = list(var_binds) if hasattr(var_binds, '__iter__') else [var_binds]

                for oid_obj, value in var_bind_list:
                    oid_str = str(oid_obj)
                    if not isinstance(value, (NoSuchObject, NoSuchInstance, EndOfMibView)):
                        snmp_data[oid_str] = str(value)
                        metadata["oids_successful"].append(oid_str)
                    else:
                        metadata["oids_failed"].append(oid_str)

        except Exception as e:
            # Fall back to individual collection for failed batch
            metadata["batch_error"] = str(e)
            await self._individual_collection(auth_data, target, oids, snmp_data, metadata)

    async def _collect_extended_oids(self, auth_data, target, oids: Dict[str, str],
                                     snmp_data: Dict[str, str], metadata: Dict):
        """Collect extended OIDs with more lenient error handling"""
        # Only try a few key extended OIDs to avoid timeouts
        key_extended = {
            "entPhysicalModelName": "1.3.6.1.2.1.47.1.1.1.1.13.1",
            "entPhysicalSerialNum": "1.3.6.1.2.1.47.1.1.1.1.11.1"
        }

        for name, oid in key_extended.items():
            try:
                error_indication, error_status, error_index, var_binds = await get_cmd(
                    self.engine, auth_data, target, ContextData(), ObjectType(ObjectIdentity(oid))
                )

                if not error_indication and not error_status and var_binds:
                    var_bind_list = list(var_binds) if hasattr(var_binds, '__iter__') else [var_binds]

                    for oid_obj, value in var_bind_list:
                        if not isinstance(value, (NoSuchObject, NoSuchInstance, EndOfMibView)):
                            snmp_data[str(oid_obj)] = str(value)
                            metadata["oids_successful"].append(str(oid_obj))
                            break  # Only get first value for table OIDs

            except Exception:
                # Silently skip extended OIDs that fail
                continue

    async def _collect_fingerprint_oids(self, auth_data, target, oids: Dict[str, str],
                                        snmp_data: Dict[str, str], metadata: Dict):
        """Collect vendor fingerprint OIDs from YAML configuration"""
        for oid, oid_name in oids.items():
            try:
                error_indication, error_status, error_index, var_binds = await get_cmd(
                    self.engine, auth_data, target, ContextData(), ObjectType(ObjectIdentity(oid))
                )

                if not error_indication and not error_status and var_binds:
                    var_bind_list = list(var_binds) if hasattr(var_binds, '__iter__') else [var_binds]

                    for oid_obj, value in var_bind_list:
                        if not isinstance(value, (NoSuchObject, NoSuchInstance, EndOfMibView)):
                            snmp_data[str(oid_obj)] = str(value)
                            metadata["oids_successful"].append(str(oid_obj))
                            # Store with descriptive name for easier debugging
                            metadata[f"fingerprint_oid_{oid_name.replace(' ', '_').lower()}"] = str(value)
                            break  # Only get first value for table OIDs

            except Exception:
                # Silently skip fingerprint OIDs that fail
                continue

    async def _individual_collection(self, auth_data, target, oids: Dict[str, str],
                                     snmp_data: Dict[str, str], metadata: Dict):
        """Collect OIDs individually as fallback"""
        for name, oid in oids.items():
            if oid in snmp_data:  # Skip already collected
                continue

            try:
                error_indication, error_status, error_index, var_binds = await get_cmd(
                    self.engine, auth_data, target, ContextData(), ObjectType(ObjectIdentity(oid))
                )

                if not error_indication and not error_status and var_binds:
                    var_bind_list = list(var_binds) if hasattr(var_binds, '__iter__') else [var_binds]

                    for oid_obj, value in var_bind_list:
                        if not isinstance(value, (NoSuchObject, NoSuchInstance, EndOfMibView)):
                            snmp_data[str(oid_obj)] = str(value)
                            metadata["oids_successful"].append(str(oid_obj))
                        else:
                            metadata["oids_failed"].append(str(oid_obj))
                else:
                    metadata["oids_failed"].append(oid)

            except Exception:
                metadata["oids_failed"].append(oid)

    def _create_v3_auth(self):
        """Create SNMPv3 authentication data"""
        auth_protocol_map = {
            "MD5": usmHMACMD5AuthProtocol,
            "SHA": usmHMACSHAAuthProtocol,
            "SHA224": usmHMAC128SHA224AuthProtocol,
            "SHA256": usmHMAC192SHA256AuthProtocol,
            "SHA384": usmHMAC256SHA384AuthProtocol,
            "SHA512": usmHMAC384SHA512AuthProtocol
        }

        priv_protocol_map = {
            "DES": usmDESPrivProtocol,
            "AES": usmAesCfb128Protocol,
            "AES192": usmAesCfb192Protocol,
            "AES256": usmAesCfb256Protocol
        }

        auth_proto = auth_protocol_map.get(self.credentials.auth_protocol, usmHMACSHAAuthProtocol)
        priv_proto = priv_protocol_map.get(self.credentials.priv_protocol, usmAesCfb128Protocol)

        return UsmUserData(
            self.credentials.username,
            authKey=self.credentials.auth_key if self.credentials.auth_key else None,
            privKey=self.credentials.priv_key if self.credentials.priv_key else None,
            authProtocol=auth_proto,
            privProtocol=priv_proto
        )


class DeviceRecord:
    """Device record matching Go schema exactly"""

    def __init__(self, ip_address: str, snmp_data: Dict[str, str],
                 fingerprint_result: Dict[str, Any], metadata: Dict[str, Any]):
        self.ip_address = ip_address
        self.snmp_data = snmp_data
        self.fingerprint_result = fingerprint_result
        self.metadata = metadata

        # Extract basic info from SNMP data
        self.sys_descr = snmp_data.get("1.3.6.1.2.1.1.1.0", "")
        self.sys_name = snmp_data.get("1.3.6.1.2.1.1.5.0", "")

    def to_go_schema(self, scan_id: str) -> Dict[str, Any]:
        """Convert to Go-compatible JSON structure"""

        # Generate device ID
        device_id = self._generate_device_id()

        # Create interfaces structure
        interfaces = {
            f"ip_{self.ip_address.replace('.', '_')}": {
                "name": f"Interface-{self.ip_address}",
                "ip_address": self.ip_address,
                "status": "discovered",
                "type": "data"
            }
        }

        # Prepare SNMP data in Go format
        snmp_data_by_ip = {
            self.ip_address: {}
        }

        # Add standard OIDs with proper names
        standard_oid_mapping = {
            "1.3.6.1.2.1.1.1.0": "sysDescr",
            "1.3.6.1.2.1.1.5.0": "sysName",
            "1.3.6.1.2.1.1.2.0": "sysObjectID",
            "1.3.6.1.2.1.1.3.0": "sysUpTime",
            "1.3.6.1.2.1.1.4.0": "sysContact",
            "1.3.6.1.2.1.1.6.0": "sysLocation",
            "1.3.6.1.2.1.1.7.0": "sysServices"
        }

        for oid, name in standard_oid_mapping.items():
            if oid in self.snmp_data and self.snmp_data[oid]:
                snmp_data_by_ip[self.ip_address][oid] = self.snmp_data[oid]

        # Add extracted fields with Go naming convention
        entity_fields = {
            "1.3.6.1.2.1.47.1.1.1.1.13.1": "Entity Model Name",
            "1.3.6.1.2.1.47.1.1.1.1.11.1": "Entity Serial Number",
            "1.3.6.1.2.1.47.1.1.1.1.8.1": "Entity Hardware Revision"
        }

        for oid, name in entity_fields.items():
            if oid in self.snmp_data and self.snmp_data[oid]:
                snmp_data_by_ip[self.ip_address][name] = self.snmp_data[oid]

        # Add vendor-specific field names based on detected vendor
        vendor = self.fingerprint_result.get('vendor', '')
        if vendor == 'apc':
            if "APC Model Number" not in snmp_data_by_ip[self.ip_address]:
                model = self.fingerprint_result.get('model', '')
                if model:
                    snmp_data_by_ip[self.ip_address]["APC Model Number"] = model
        elif vendor == 'cisco' or vendor == 'ion':
            if "Cisco Model" not in snmp_data_by_ip[self.ip_address]:
                model = self.fingerprint_result.get('model', '')
                if model:
                    snmp_data_by_ip[self.ip_address]["Cisco Model"] = model

        timestamp = datetime.now(timezone.utc).isoformat()

        return {
            "id": device_id,
            "primary_ip": self.ip_address,
            "all_ips": [self.ip_address],
            "mac_addresses": [],
            "interfaces": interfaces,
            "vendor": self.fingerprint_result.get('vendor', ''),
            "device_type": self.fingerprint_result.get('device_type', ''),
            "model": self.fingerprint_result.get('model', ''),
            "serial_number": self.fingerprint_result.get('serial_number', ''),
            "os_version": self.fingerprint_result.get('os_version', ''),
            "sys_descr": self.sys_descr,
            "sys_name": self.sys_name,
            "first_seen": timestamp,
            "last_seen": timestamp,
            "scan_count": 1,
            "last_scan_id": scan_id,
            "identity_method": "basic",
            "identity_confidence": 0,
            "snmp_data_by_ip": snmp_data_by_ip,
            "confidence_score": self.fingerprint_result.get('confidence_score', 0),
            "detection_method": self.fingerprint_result.get('detection_method', ''),
            "snmp_version_used": self.metadata.get('snmp_version_successful', 'unknown')
        }

    def _generate_device_id(self) -> str:
        """Generate device ID following Go convention"""
        vendor = self.fingerprint_result.get('vendor', '')
        device_type = self.fingerprint_result.get('device_type', '')

        # Use system name if available and not empty
        if self.sys_name and self.sys_name.strip():
            # Clean system name for use as ID
            clean_name = self.sys_name.lower().replace('-', '_').replace(' ', '_')
            # Remove any non-alphanumeric characters except underscores
            import re
            clean_name = re.sub(r'[^a-z0-9_]', '', clean_name)
            return f"host_{clean_name}"
        elif vendor and device_type:
            # Use vendor-type-ip format
            ip_suffix = self.ip_address.split('.')[-1]
            return f"host_{vendor}_{device_type}_{ip_suffix}"
        else:
            # Fallback to IP-based ID
            return f"ip_{self.ip_address.replace('.', '_')}"


class OptimizedSNMPScanner:
    """Optimized scanner with TCP pre-filtering and v3/v2c fallback"""

    def __init__(self, config: ScanConfig):
        self.config = config
        self.fingerprint_engine = FingerprintEngine(config.fingerprint_rules)
        # Pass fingerprint engine to collector for OID collection
        self.collector = SNMPCollector(config.credentials, self.fingerprint_engine)
        self.tcp_checker = TCPPortChecker()

    async def scan_network(self, cidr: str) -> Dict[str, Any]:
        """Scan network CIDR with TCP pre-filtering and SNMP version fallback"""

        # Parse CIDR
        try:
            network = ipaddress.ip_network(cidr, strict=False)
            ip_list = [str(ip) for ip in network.hosts()]
        except Exception as e:
            raise ValueError(f"Invalid CIDR: {e}")

        total_hosts = len(ip_list)
        print(f"Scanning {total_hosts} hosts in {cidr}")
        print(f"TCP pre-filter ports: {self.config.tcp_check_ports}")
        print(f"TCP timeout: {self.config.tcp_check_timeout}s")
        print(f"SNMP timeout: {self.config.credentials.timeout}s")
        print(
            f"SNMP strategy: v3 first, then v2c fallback" if self.config.credentials.try_v2c_fallback else f"SNMP version: {self.config.credentials.version}")
        print(f"Concurrent scans: {self.config.concurrent_scans}")
        print("-" * 90)
        print(f"{'IP Address':<15} | {'TCP':<4} | {'SNMP':<5} | {'Vendor':<12} | {'Device Type':<15} | Progress")
        print("-" * 90)

        # Progress tracking
        start_time = time.time()
        completed = 0
        tcp_responsive = 0
        snmp_successful = 0
        tcp_failed = 0
        snmp_failed = 0
        v3_success = 0
        v2c_success = 0
        results = []

        # Create semaphore for concurrent scanning
        semaphore = asyncio.Semaphore(self.config.concurrent_scans)

        # Progress-aware scan function
        async def scan_with_progress(ip):
            nonlocal completed, tcp_responsive, snmp_successful, tcp_failed, snmp_failed, v3_success, v2c_success

            result = await self._scan_single_device_optimized(semaphore, ip)

            # Update progress
            completed += 1

            if result is not None:
                device_record, session_data, tcp_status = result

                if tcp_status == "responsive":
                    tcp_responsive += 1

                    if device_record:
                        snmp_successful += 1
                        vendor = device_record.fingerprint_result.get('vendor', 'unknown')
                        device_type = device_record.fingerprint_result.get('device_type', 'unknown')
                        snmp_version = device_record.metadata.get('snmp_version_successful', 'unk')

                        # Track version success
                        if snmp_version == 'v3':
                            v3_success += 1
                        elif snmp_version == 'v2c':
                            v2c_success += 1

                        print(
                            f"✓ {ip:<15} | {'OK':<4} | {snmp_version:<5} | {vendor:<12} | {device_type:<15} | ({completed}/{total_hosts})")
                        results.append((device_record, session_data))
                    else:
                        snmp_failed += 1
                        print(
                            f"~ {ip:<15} | {'OK':<4} | {'FAIL':<5} | {'snmp_fail':<12} | {'no_response':<15} | ({completed}/{total_hosts})")
                else:
                    tcp_failed += 1
                    print(
                        f"✗ {ip:<15} | {'NO':<4} | {'N/A':<5} | {'no_tcp':<12} | {'not_scanned':<15} | ({completed}/{total_hosts})")
            else:
                tcp_failed += 1
                print(
                    f"✗ {ip:<15} | {'TO':<4} | {'N/A':<5} | {'timeout':<12} | {'not_scanned':<15} | ({completed}/{total_hosts})")

            # Show progress update every 50 devices or at key milestones
            if completed % 50 == 0 or completed in [1, 5, 10, 25] or completed == total_hosts:
                elapsed = time.time() - start_time
                if completed > 0:
                    rate = completed / elapsed
                    eta_seconds = (total_hosts - completed) / rate if rate > 0 else 0
                    eta_str = f"{int(eta_seconds // 60)}m {int(eta_seconds % 60)}s" if eta_seconds > 0 else "complete"

                    progress_pct = (completed / total_hosts) * 100
                    print("-" * 90)
                    print(
                        f"Progress: {progress_pct:.1f}% | TCP OK: {tcp_responsive} | SNMP: {snmp_successful} (v3: {v3_success}, v2c: {v2c_success}) | TCP Failed: {tcp_failed} | ETA: {eta_str}")
                    if completed < total_hosts:
                        print("-" * 90)

            return result

        # Scan all IPs concurrently with progress tracking
        tasks = [scan_with_progress(ip) for ip in ip_list]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Process results into final format
        devices = {}
        sessions = []
        total_devices = 0
        scan_id = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(cidr) & 0xffffffff:08x}"

        print("\n" + "=" * 90)
        print("Processing results...")

        for device_record, session_data in results:
            if device_record:
                device_data = device_record.to_go_schema(scan_id)
                devices[device_data["id"]] = device_data
                total_devices += 1

                if session_data:
                    sessions.append(session_data)

        # Final summary
        total_time = time.time() - start_time
        # print(f"\nScan Complete!")
        print(f"SCAN_COMPLETE: {total_devices} devices found in {int(total_time // 60)}m {int(total_time % 60)}s")

        print(f"Hosts scanned: {total_hosts}")
        print(f"TCP responsive: {tcp_responsive}")
        print(f"SNMP devices found: {total_devices}")
        print(f"  - SNMPv3 successful: {v3_success}")
        print(f"  - SNMPv2c successful: {v2c_success}")
        print(f"TCP non-responsive: {tcp_failed}")
        print(f"SNMP timeouts: {snmp_failed}")
        print(f"Success rate: {(snmp_successful / total_hosts) * 100:.1f}%")
        print(f"TCP filter efficiency: {((tcp_failed) / total_hosts) * 100:.1f}% hosts skipped")

        # Show vendor breakdown
        vendor_counts = {}
        device_type_counts = {}
        for device in devices.values():
            vendor = device.get('vendor', 'unknown')
            device_type = device.get('device_type', 'unknown')
            vendor_counts[vendor] = vendor_counts.get(vendor, 0) + 1
            device_type_counts[device_type] = device_type_counts.get(device_type, 0) + 1

        if vendor_counts:
            print(f"\nVendor breakdown:")
            for vendor, count in sorted(vendor_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"   {vendor:<12}: {count}")

            print(f"\nDevice types:")
            for device_type, count in sorted(device_type_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"   {device_type:<15}: {count}")

        # Build final result in Go schema format
        return {
            "version": "1.0.0",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_devices": total_devices,
            "devices": devices,
            "sessions": sessions,
            "statistics": self._generate_statistics(devices, v3_success, v2c_success),
            "config": {
                "max_sessions": 100,
                "max_devices": 10000,
                "auto_cleanup": True,
                "cleanup_interval": 86400000000000,
                "backup_enabled": True,
                "backup_count": 5,
                "compress_backups": False
            }
        }

    async def _scan_single_device_optimized(self, semaphore: asyncio.Semaphore, ip_address: str) -> Optional[Tuple]:
        """Optimized single device scan with TCP pre-filtering and SNMP fallback"""
        async with semaphore:
            try:
                # Step 1: TCP connectivity check (unless disabled)
                if not self.config.skip_tcp_check:
                    tcp_responsive = await self.tcp_checker.check_host_responsive(
                        ip_address,
                        self.config.tcp_check_ports,
                        self.config.tcp_check_timeout
                    )

                    if not tcp_responsive:
                        # Host not responsive on any TCP ports - skip SNMP
                        return None, None, "not_responsive"
                else:
                    tcp_responsive = True

                # Step 2: SNMP data collection with version fallback
                snmp_data, metadata = await self.collector.collect_device_data(ip_address)

                # Skip if no SNMP response or critical data missing
                if not snmp_data or "1.3.6.1.2.1.1.1.0" not in snmp_data:
                    return None, None, "responsive"

                # Step 3: Fingerprint device
                fingerprint_result = self.fingerprint_engine.fingerprint_device(snmp_data)

                # Step 4: Create device record
                device_record = DeviceRecord(ip_address, snmp_data, fingerprint_result, metadata)

                # Step 5: Create session data
                session_data = {
                    "id": f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(ip_address) & 0xffffffff:08x}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "target_ip": ip_address,
                    "scan_type": "single_device",
                    "devices_found": 1,
                    "new_devices": 0,
                    "updated_devices": 0,
                    "snmp_version_used": metadata.get('snmp_version_successful', 'unknown'),
                    "results": [{
                        "ip_address": ip_address,
                        "vendor": fingerprint_result.get('vendor', ''),
                        "device_type": fingerprint_result.get('device_type', ''),
                        "model": fingerprint_result.get('model', ''),
                        "serial_number": fingerprint_result.get('serial_number', ''),
                        "os_version": fingerprint_result.get('os_version', ''),
                        "sys_descr": snmp_data.get("1.3.6.1.2.1.1.1.0", ""),
                        "sys_name": snmp_data.get("1.3.6.1.2.1.1.5.0", ""),
                        "snmp_data": dict(snmp_data),
                        "confidence_score": fingerprint_result.get('confidence_score', 0),
                        "detection_method": fingerprint_result.get('detection_method', ''),
                        "scan_timestamp": datetime.now(timezone.utc).isoformat(),
                        "snmp_version": metadata.get('snmp_version_successful', 'unknown')
                    }],
                    "duration": "1s"
                }

                return device_record, session_data, "responsive"

            except asyncio.TimeoutError:
                return None, None, "responsive"
            except Exception as e:
                if hasattr(self.config, 'verbose') and self.config.verbose:
                    print(f"Error scanning {ip_address}: {e}")
                return None, None, "responsive"

    def _generate_statistics(self, devices: Dict, v3_success: int, v2c_success: int) -> Dict[str, Any]:
        """Generate statistics section matching Go format with version info"""
        vendor_breakdown = {}
        type_breakdown = {}

        for device in devices.values():
            vendor = device.get('vendor', 'unknown')
            device_type = device.get('device_type', 'unknown')

            vendor_breakdown[vendor] = vendor_breakdown.get(vendor, 0) + 1
            type_breakdown[device_type] = type_breakdown.get(device_type, 0) + 1

        return {
            "total_devices": len(devices),
            "total_sessions": len(devices),
            "vendor_breakdown": vendor_breakdown,
            "type_breakdown": type_breakdown,
            "snmp_version_breakdown": {
                "v3_successful": v3_success,
                "v2c_successful": v2c_success,
                "total_successful": v3_success + v2c_success
            },
            "last_scan_date": datetime.now(timezone.utc).isoformat(),
            "oldest_device": datetime.now(timezone.utc).isoformat(),
            "avg_confidence": sum(d.get('confidence_score', 0) for d in devices.values()) / max(len(devices), 1),
            "devices_per_subnet": {
                "total": len(devices)
            },
            "error_stats": {}
        }


def ensure_output_directory(output_path: str) -> str:
    """
    Ensure the output directory exists, creating it if necessary.
    Returns the absolute path to the output file.
    """
    # Convert to Path object for easier manipulation
    output_file = Path(output_path)

    # Get the directory part
    output_dir = output_file.parent

    # Create directory if it doesn't exist
    if not output_dir.exists():
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            print(f"Created output directory: {output_dir.absolute()}")
        except Exception as e:
            print(f"Warning: Could not create output directory {output_dir}: {e}")
            # Fall back to current directory
            fallback_file = Path.cwd() / output_file.name
            print(f"Using fallback output file: {fallback_file.absolute()}")
            return str(fallback_file)

    return str(output_file.resolve())


async def main():
    """Main CLI function"""
    parser = argparse.ArgumentParser(description="Optimized Python SNMP Scanner with v3/v2c Fallback")
    parser.add_argument("--cidr", required=True, help="Network CIDR to scan (e.g., 192.168.1.0/24)")
    parser.add_argument("--config", default="scanner_config.yaml", help="Configuration file")
    parser.add_argument("--rules", default="vendor_fingerprints.yaml", help="Fingerprint rules file")
    parser.add_argument("--output", default="scan_results.json", help="Output file")
    parser.add_argument("--concurrent", type=int, default=100, help="Concurrent scans")
    parser.add_argument("--tcp-timeout", type=int, default=2, help="TCP port check timeout")
    parser.add_argument("--skip-tcp-check", action="store_true", help="Skip TCP pre-filtering")
    parser.add_argument("--tcp-ports", nargs='+', type=int,
                        default=[20, 21, 22, 25, 53, 80, 161, 443, 993, 995],
                        help="TCP ports to check for responsiveness")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # SNMP credentials - NOTE: version parameter now controls preferred method
    parser.add_argument("--snmp-version", default="v3", choices=["v2c", "v3"],
                        help="Preferred SNMP version (will try fallback automatically)")
    parser.add_argument("--community", default="public", help="SNMP v2c community")
    parser.add_argument("--communities", nargs='+', default=["public", "private"],
                        help="SNMP v2c communities to try (space-separated)")
    parser.add_argument("--username", default="", help="SNMP v3 username")
    parser.add_argument("--auth-protocol", default="SHA", help="SNMP v3 auth protocol")
    parser.add_argument("--auth-key", default="", help="SNMP v3 auth key")
    parser.add_argument("--priv-protocol", default="AES", help="SNMP v3 privacy protocol")
    parser.add_argument("--priv-key", default="", help="SNMP v3 privacy key")
    parser.add_argument("--snmp-timeout", type=int, default=3, help="SNMP timeout in seconds")
    parser.add_argument("--retries", type=int, default=1, help="SNMP retries")
    parser.add_argument("--no-fallback", action="store_true", help="Disable automatic version fallback")

    args = parser.parse_args()

    # Create configuration
    credentials = SNMPCredentials(
        version=args.snmp_version,
        community=args.community,
        communities=args.communities,
        username=args.username,
        auth_protocol=args.auth_protocol,
        auth_key=args.auth_key,
        priv_protocol=args.priv_protocol,
        priv_key=args.priv_key,
        timeout=args.snmp_timeout,
        retries=args.retries,
        try_v2c_fallback=not args.no_fallback
    )

    config = ScanConfig(
        credentials=credentials,
        fingerprint_rules=args.rules,
        concurrent_scans=args.concurrent,
        tcp_check_timeout=args.tcp_timeout,
        tcp_check_ports=args.tcp_ports,
        skip_tcp_check=args.skip_tcp_check
    )
    config.verbose = args.verbose

    # Validate files exist
    if not Path(args.rules).exists():
        print(f"Error: Fingerprint rules file not found: {args.rules}")
        sys.exit(1)

    # Ensure output directory exists and get absolute path
    output_file = ensure_output_directory(args.output)

    # Create scanner and run scan
    scanner = OptimizedSNMPScanner(config)

    print(f"Optimized Python SNMP Scanner v2.2 - with v3/v2c Fallback")
    print(f"CIDR: {args.cidr}")
    print(f"SNMP Strategy: {args.snmp_version} preferred" + (
        ", with fallback" if not args.no_fallback else ", no fallback"))
    if args.snmp_version == "v3" and args.username:
        print(f"SNMPv3 User: {args.username}")
    print(f"SNMPv2c Communities: {args.communities}")
    print(f"Rules: {args.rules}")
    print(f"Output: {output_file}")

    try:
        results = await scanner.scan_network(args.cidr)

        # Output results with proper error handling
        try:
            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\nResults saved to {output_file}")
        except Exception as e:
            # If writing fails, try current directory as fallback
            fallback_filename = f"scan_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            fallback_path = Path.cwd() / fallback_filename

            print(f"Warning: Could not write to {output_file}: {e}")
            print(f"Trying fallback location: {fallback_path}")

            try:
                with open(fallback_path, 'w') as f:
                    json.dump(results, f, indent=2)
                print(f"Results saved to fallback location: {fallback_path}")
            except Exception as fallback_error:
                print(f"ERROR: Could not write results to any location: {fallback_error}")
                # At least print some basic results to console
                print(f"\nScan completed but file write failed. Basic results:")
                print(f"Total devices found: {results.get('total_devices', 0)}")
                if results.get('devices'):
                    print("Sample devices:")
                    for i, (device_id, device) in enumerate(results['devices'].items()):
                        if i >= 3:  # Show max 3 samples
                            break
                        print(
                            f"  - {device_id}: {device.get('vendor', 'unknown')} {device.get('device_type', 'unknown')}")
                sys.exit(1)

        # Quick verification - show a few examples of what was found
        if results['devices']:
            print(f"\nSample devices found:")
            sample_count = 0
            for device_id, device in results['devices'].items():
                if sample_count >= 3:
                    break
                vendor = device.get('vendor', 'unknown')
                device_type = device.get('device_type', 'unknown')
                snmp_version = device.get('snmp_version_used', 'unknown')
                sys_descr = device.get('sys_descr', '')[:50] + '...' if len(
                    device.get('sys_descr', '')) > 50 else device.get('sys_descr', '')
                print(f"   {device_id}: {vendor} {device_type} (via {snmp_version})")
                print(f"      Description: {sys_descr}")
                sample_count += 1

    except Exception as e:
        print(f"SCAN_FAILED: {e}", file=sys.stderr)

        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())