"""
Enhanced Platform-Aware Telemetry Controller with Netmiko Integration
UPDATED: Now uses JSON configuration instead of hardcoded platform commands
FIXED: Route normalization with platform-aware field mapping
"""

import sys
import time
import threading
from dataclasses import dataclass, field, asdict
from io import StringIO
from typing import Dict, List, Optional, Callable, Any, Union
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread, pyqtSlot
import json
import os

from termtel.termtelwidgets.platform_config_manager import PlatformConfigManager

# Netmiko imports
try:
    from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
    from netmiko.exceptions import NetmikoBaseException
    NETMIKO_AVAILABLE = True
except ImportError:
    NETMIKO_AVAILABLE = False
    print("Warning: Netmiko not available, using mock connections")

# TextFSM imports
try:
    import textfsm
    TEXTFSM_AVAILABLE = True
    # Try to import ntc_templates for comparison, but don't require it
    try:
        from ntc_templates.parse import parse_output
        NTC_TEMPLATES_AVAILABLE = True
    except ImportError:
        NTC_TEMPLATES_AVAILABLE = False
        print("Note: NTC Templates library not available, using local templates only")
except ImportError:
    TEXTFSM_AVAILABLE = False
    NTC_TEMPLATES_AVAILABLE = False
    print("Warning: TextFSM not available, using basic parsing")





@dataclass
class NormalizedSystemMetrics:
    """
    Normalized system metrics - TRUE lowest common denominator
    Normalizes DOWN to what Cisco devices actually support
    """
    # === CORE METRICS (what Cisco can actually provide) ===
    cpu_usage_percent: float = 0.0  # Current CPU utilization
    memory_used_percent: float = 0.0  # Memory utilization percentage
    memory_total_mb: int = 0  # Total memory in MB
    memory_used_mb: int = 0  # Used memory in MB
    memory_free_mb: int = 0  # Free memory in MB

    # === METADATA ===
    timestamp: float = field(default_factory=time.time)
    platform: str = ""

    # === OPTIONAL (only if device supports it) ===
    temperature_celsius: float = 0.0  # Some devices have temp sensors
    cpu_1min_avg: float = 0.0  # 1-minute CPU average (Cisco has this)
    cpu_5min_avg: float = 0.0  # 5-minute CPU average (Cisco has this)

    def __post_init__(self):
        """Calculate derived fields after initialization"""
        # Auto-calculate memory fields if missing
        if self.memory_used_mb == 0 and self.memory_total_mb > 0 and self.memory_free_mb > 0:
            self.memory_used_mb = self.memory_total_mb - self.memory_free_mb

        if self.memory_free_mb == 0 and self.memory_total_mb > 0 and self.memory_used_mb > 0:
            self.memory_free_mb = self.memory_total_mb - self.memory_used_mb

        if self.memory_used_percent == 0.0 and self.memory_total_mb > 0 and self.memory_used_mb > 0:
            self.memory_used_percent = (self.memory_used_mb / self.memory_total_mb) * 100.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization/logging"""
        return {
            'cpu_usage_percent': self.cpu_usage_percent,
            'cpu_1min_avg': self.cpu_1min_avg,
            'cpu_5min_avg': self.cpu_5min_avg,
            'memory_used_percent': self.memory_used_percent,
            'memory_total_mb': self.memory_total_mb,
            'memory_used_mb': self.memory_used_mb,
            'memory_free_mb': self.memory_free_mb,
            'temperature_celsius': self.temperature_celsius,
            'timestamp': self.timestamp,
            'platform': self.platform
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NormalizedSystemMetrics':
        """Create from dictionary"""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})

    def get_summary_string(self) -> str:
        """Get human-readable summary"""
        temp_str = f", Temp: {self.temperature_celsius:.1f}°C" if self.temperature_celsius > 0 else ""
        return (f"CPU: {self.cpu_usage_percent:.1f}%, "
                f"Memory: {self.memory_used_percent:.1f}% "
                f"({self.memory_used_mb:,}/{self.memory_total_mb:,} MB){temp_str}")

    def is_valid(self) -> bool:
        """Check if metrics contain valid data"""
        return (self.cpu_usage_percent >= 0.0 and
                self.memory_total_mb > 0 and
                self.platform != "")

    def get_alert_level(self) -> str:
        """Get alert level based on thresholds"""
        cpu_high = self.cpu_usage_percent > 80
        memory_high = self.memory_used_percent > 85
        temp_high = self.temperature_celsius > 70 if self.temperature_celsius > 0 else False

        if cpu_high or memory_high or temp_high:
            return "critical"
        elif self.cpu_usage_percent > 60 or self.memory_used_percent > 70:
            return "warning"
        else:
            return "normal"


# ============ PLATFORM-SPECIFIC CONVERTERS ============

@dataclass
class CiscoCPUMetrics:
    """Cisco CPU metrics (what they actually provide)"""
    cpu_5sec: float = 0.0  # 5-second average
    cpu_1min: float = 0.0  # 1-minute average
    cpu_5min: float = 0.0  # 5-minute average

    def to_normalized(self, platform: str) -> NormalizedSystemMetrics:
        return NormalizedSystemMetrics(
            cpu_usage_percent=self.cpu_5sec,
            cpu_1min_avg=self.cpu_1min,
            cpu_5min_avg=self.cpu_5min,
            platform=platform
        )


@dataclass
class CiscoMemoryMetrics:
    """Cisco memory metrics (bytes)"""
    processor_total: int = 0
    processor_used: int = 0
    processor_free: int = 0

    def to_normalized(self, platform: str) -> NormalizedSystemMetrics:
        total_mb = self.processor_total // (1024 * 1024)
        used_mb = self.processor_used // (1024 * 1024)
        free_mb = self.processor_free // (1024 * 1024)
        used_percent = (self.processor_used / self.processor_total * 100) if self.processor_total > 0 else 0

        return NormalizedSystemMetrics(
            memory_used_percent=used_percent,
            memory_total_mb=total_mb,
            memory_used_mb=used_mb,
            memory_free_mb=free_mb,
            platform=platform
        )


@dataclass
class LinuxSystemMetrics:
    """Linux metrics - map down to Cisco equivalent"""
    cpu_percent: float = 0.0
    load_1min: float = 0.0  # Map to cpu_1min_avg
    load_5min: float = 0.0  # Map to cpu_5min_avg
    memory_total: int = 0  # bytes
    memory_available: int = 0  # bytes
    memory_used: int = 0  # bytes

    def to_normalized(self, platform: str) -> NormalizedSystemMetrics:
        total_mb = self.memory_total // (1024 * 1024)
        used_mb = self.memory_used // (1024 * 1024)
        free_mb = (self.memory_total - self.memory_used) // (1024 * 1024)

        return NormalizedSystemMetrics(
            cpu_usage_percent=self.cpu_percent,
            cpu_1min_avg=self.load_1min,  # Load average as CPU avg approximation
            cpu_5min_avg=self.load_5min,
            memory_total_mb=total_mb,
            memory_used_mb=used_mb,
            memory_free_mb=free_mb,
            platform=platform
        )


@dataclass
class AristaSystemMetrics:
    """Arista metrics - map down to Cisco equivalent"""
    cpu_user: float = 0.0
    cpu_system: float = 0.0
    cpu_idle: float = 0.0
    memory_total_kb: int = 0
    memory_used_kb: int = 0
    memory_free_kb: int = 0

    def to_normalized(self, platform: str) -> NormalizedSystemMetrics:
        cpu_usage = 100.0 - self.cpu_idle  # Convert idle to usage

        return NormalizedSystemMetrics(
            cpu_usage_percent=cpu_usage,
            memory_total_mb=self.memory_total_kb // 1024,
            memory_used_mb=self.memory_used_kb // 1024,
            memory_free_mb=self.memory_free_kb // 1024,
            platform=platform
        )


"""
Updated LocalTemplateParser to use package resources
"""

import os
from io import StringIO
from typing import Optional, List, Dict
from termtel.helpers.resource_manager import resource_manager

try:
    import textfsm

    TEXTFSM_AVAILABLE = True
except ImportError:
    TEXTFSM_AVAILABLE = False


class LocalTemplateParser:
    """
    UPDATED: Parser for local template files using package resources
    """

    def __init__(self, template_dir: Optional[str] = None):
        """
        Initialize template parser

        Args:
            template_dir: Legacy parameter for backwards compatibility
        """
        self.template_dir = template_dir  # Keep for backwards compatibility
        self._template_cache = {}

    def parse(self, platform: str, command: str, data: str) -> Optional[List[Dict]]:
        """
        Parse data using package resource templates

        Args:
            platform: Platform name (e.g., 'cisco_ios')
            command: Command name (e.g., 'show_version')
            data: Raw command output to parse

        Returns:
            List of dictionaries with parsed data or None if parsing fails
        """
        if not TEXTFSM_AVAILABLE:
            print(" TextFSM not available")
            return None

        # Build template filename
        template_name = f"{platform}_{command}.textfsm"

        print(f" Looking for template: {template_name}")

        # Try to get template content using resource manager
        template_content = self._get_template_content(template_name)

        if not template_content:
            print(f" Template not found: {template_name}")
            return None

        try:
            # Create TextFSM template from content
            template_file = StringIO(template_content)
            template = textfsm.TextFSM(template_file)

            # Ensure data is a string
            if isinstance(data, list):
                data = '\n'.join(data)
            elif not isinstance(data, str):
                data = str(data)

            # Parse the data
            parsed_rows = template.ParseText(data)
            headers = template.header

            # Convert to list of dictionaries
            result = []
            for row in parsed_rows:
                result.append(dict(zip(headers, row)))

            print(f" Template parsing successful: {len(result)} entries parsed")
            if result:
                print(f" Fields found: {list(result[0].keys())}")

            return result

        except Exception as e:
            print(f" Template parsing failed for {template_name}: {e}")
            # Show a sample of the data for debugging
            sample_data = data[:200].replace('\n', '\\n') if data else "No data"
            print(f" Sample data: {sample_data}...")
            return None

    def _get_template_content(self, template_name: str) -> Optional[str]:
        """
        Get template content using package resources with caching
        """
        # Check cache first
        if template_name in self._template_cache:
            return self._template_cache[template_name]

        # Try package resources first
        template_content = resource_manager.get_template_content(template_name)

        if template_content:
            print(f" Loaded template from package resources: {template_name}")
            self._template_cache[template_name] = template_content
            return template_content

        # Fallback to file system (for development)
        if self.template_dir:
            template_path = os.path.join(self.template_dir, template_name)
            if os.path.exists(template_path):
                try:
                    with open(template_path, 'r', encoding='utf-8') as f:
                        template_content = f.read()
                    print(f" Loaded template from file system: {template_path}")
                    self._template_cache[template_name] = template_content
                    return template_content
                except Exception as e:
                    print(f" Error reading template file {template_path}: {e}")

        print(f" Template not found: {template_name}")
        return None

    def list_available_templates(self) -> List[str]:
        """
        List all available TextFSM templates

        Returns:
            List of template filenames
        """
        return resource_manager.list_templates()

    def get_template_path(self, template_name: str) -> Optional[str]:
        """
        Get the full path to a template file

        Args:
            template_name: Name of the template file

        Returns:
            Full path to template or None if not found
        """
        return resource_manager.get_template_path(template_name)

    def validate_template(self, template_name: str) -> Dict[str, any]:
        """
        Validate a template file

        Args:
            template_name: Name of the template file

        Returns:
            Dictionary with validation results
        """
        result = {
            'valid': False,
            'exists': False,
            'parseable': False,
            'fields': [],
            'errors': []
        }

        # Check if template exists
        template_content = self._get_template_content(template_name)
        if not template_content:
            result['errors'].append(f"Template file not found: {template_name}")
            return result

        result['exists'] = True

        # Try to parse the template
        if not TEXTFSM_AVAILABLE:
            result['errors'].append("TextFSM library not available")
            return result

        try:
            template_file = StringIO(template_content)
            template = textfsm.TextFSM(template_file)
            result['parseable'] = True
            result['fields'] = template.header
            result['valid'] = True

        except Exception as e:
            result['errors'].append(f"Template parsing error: {str(e)}")

        return result

    def clear_cache(self):
        """Clear the template cache"""
        self._template_cache.clear()
        print(" Template cache cleared")

    def get_cache_info(self) -> Dict[str, any]:
        """Get information about the current cache"""
        return {
            'cached_templates': list(self._template_cache.keys()),
            'cache_size': len(self._template_cache),
            'total_available': len(self.list_available_templates())
        }

@dataclass
class ConnectionCredentials:
    """Device connection credentials"""
    username: str
    password: str
    secret: str = ""  # Enable password
    port: int = 22
    timeout: int = 10
    auth_timeout: int = 10


@dataclass
class DeviceInfo:
    hostname: str
    ip_address: str
    platform: str
    model: str = ""
    version: str = ""
    serial: str = ""
    uptime: str = ""
    connection_status: str = "disconnected"

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert DeviceInfo to dictionary

        Returns:
            Dictionary representation of the DeviceInfo object
        """

        return asdict(self)


@dataclass
class RawCommandOutput:
    """Raw command output from device with parsing metadata"""
    command: str
    output: str
    platform: str
    timestamp: float
    success: bool = True
    error_message: str = ""
    template_used: str = ""
    parsed_successfully: bool = False
    parsed_data: Optional[List[Dict]] = None


@dataclass
class NormalizedNeighborData:
    """Normalized neighbor data structure across all platforms"""
    local_interface: str
    neighbor_device: str
    neighbor_interface: str
    neighbor_ip: str = ""
    neighbor_platform: str = ""
    neighbor_capability: str = ""
    protocol_used: str = ""  # CDP, LLDP, etc.


@dataclass
class NormalizedArpData:
    """Normalized ARP data structure across all platforms"""
    ip_address: str
    mac_address: str
    interface: str
    age: str = ""
    type: str = ""
    state: str = ""


@dataclass
class NormalizedRouteData:
    """Normalized route data structure across all platforms"""
    network: str
    next_hop: str
    protocol: str
    mask: str = ""
    interface: str = ""
    metric: str = ""
    admin_distance: str = ""
    age: str = ""
    vrf: str = "default"


class ConfigDrivenFieldNormalizer:
    """
    UPDATED: Field normalizer that uses platform configuration for mappings
    FIXED: Enhanced route normalization with platform-aware field mapping
    """

    def __init__(self, platform_config_manager):
        self.platform_config = platform_config_manager

        # Keep the original field mappings as fallback
        self.NEIGHBOR_FIELD_MAPPINGS = {
            'local_interface': ['LOCAL_INTERFACE', 'local_interface', 'local_port'],
            'neighbor_device': ['NEIGHBOR_NAME', 'neighbor', 'neighbor_id', 'device_id', 'system_name'],
            'neighbor_interface': ['NEIGHBOR_INTERFACE', 'NEIGHBOR_PORT_ID', 'neighbor_interface', 'neighbor_port', 'remote_port'],
            'neighbor_ip': ['MGMT_ADDRESS', 'neighbor_ip', 'management_ip', 'mgmt_ip'],
            'neighbor_platform': ['PLATFORM', 'platform', 'neighbor_platform', 'system_description'],
            'neighbor_capability': ['CAPABILITIES', 'capabilities', 'capability'],
            'protocol_used': ['protocol']
        }

        self.ARP_FIELD_MAPPINGS = {
            'ip_address': ['IP_ADDRESS', 'address', 'ip', 'ip_address', 'protocol_address'],
            'mac_address': ['MAC_ADDRESS', 'mac', 'mac_address', 'hardware_addr', 'hwaddr'],
            'interface': ['INTERFACE', 'interface', 'intf', 'port'],
            'age': ['AGE', 'age', 'age_min'],
            'type': ['TYPE', 'type', 'encap_type'],
            'state': ['state', 'flags']
        }

        # UPDATED: Enhanced route field mappings that handle platform variations
        self.ROUTE_FIELD_MAPPINGS = {
            'network': ['NETWORK', 'PREFIX', 'DESTINATION', 'DEST', 'network', 'destination'],
            'mask': ['PREFIX_LENGTH', 'MASK', 'NETMASK', 'mask', 'prefix_length'],
            'next_hop': ['NEXTHOP_IP', 'NEXT_HOP', 'VIA', 'GATEWAY', 'nexthop', 'gateway'],
            'interface': ['NEXTHOP_IF', 'INTERFACE', 'INTF', 'PORT', 'DEV', 'interface', 'port'],
            'protocol': ['PROTOCOL', 'ROUTE_TYPE', 'PROTO', 'SOURCE', 'protocol', 'source'],
            'metric': ['METRIC', 'COST', 'DISTANCE', 'metric', 'cost'],
            'admin_distance': ['DISTANCE', 'AD', 'PREFERENCE', 'admin_distance', 'preference'],
            'age': ['UPTIME', 'AGE', 'TIME', 'age', 'uptime'],
            'vrf': ['VRF', 'TABLE', 'ROUTING_TABLE', 'vrf', 'table']
        }

        self.SYSTEM_INFO_FIELD_MAPPINGS = {
            'hostname': ['HOSTNAME', 'hostname', 'device_name'],
            'version': ['VERSION', 'version', 'software_version'],
            'model': ['HARDWARE', 'hardware', 'model', 'platform'],
            'serial': ['SERIAL', 'serial', 'serial_number'],
            'uptime': ['UPTIME', 'uptime'],
            'image': ['SOFTWARE_IMAGE', 'software_image', 'image'],
            'config_register': ['CONFIG_REGISTER', 'config_register']
        }

    def normalize_field_value(self, platform: str, field_type: str, value: str) -> str:
        """Normalize field value using platform-specific mappings from JSON config"""
        field_mapping = self.platform_config.get_field_mapping(platform, field_type)
        return field_mapping.get(value, value)

    def normalize_neighbors(self, parsed_data: List[Dict], platform: str, command_used: str = "") -> List[NormalizedNeighborData]:
        """Normalize neighbor data from parsed template output"""
        normalized = []

        for entry in parsed_data:
            normalized_entry = NormalizedNeighborData(
                local_interface="",
                neighbor_device="",
                neighbor_interface=""
            )

            # Map fields using the field mappings
            for norm_field, possible_fields in self.NEIGHBOR_FIELD_MAPPINGS.items():
                for field in possible_fields:
                    if field in entry and entry[field]:
                        setattr(normalized_entry, norm_field, str(entry[field]).strip())
                        break

            # Set protocol based on command used or platform capabilities
            platform_def = self.platform_config.get_platform(platform)
            if platform_def:
                if not 'arista' in platform_def.name:
                    if 'cdp' in command_used.lower():
                        normalized_entry.protocol_used = "CDP"
                elif 'lldp' in command_used.lower():
                    normalized_entry.protocol_used = "LLDP"
                else:
                    # Use platform's primary neighbor protocol
                    normalized_entry.protocol_used = platform_def.capabilities.neighbor_protocol.upper()
            else:
                # Fallback logic
                if 'cdp' in command_used.lower():
                    normalized_entry.protocol_used = "CDP"
                elif 'lldp' in command_used.lower():
                    normalized_entry.protocol_used = "LLDP"

            normalized.append(normalized_entry)

        return normalized

    def normalize_arp(self, parsed_data: List[Dict], platform: str) -> List[NormalizedArpData]:
        """Normalize ARP data from parsed template output"""
        normalized = []

        for entry in parsed_data:
            normalized_entry = NormalizedArpData(
                ip_address="",
                mac_address="",
                interface=""
            )

            # Map fields using the field mappings
            for norm_field, possible_fields in self.ARP_FIELD_MAPPINGS.items():
                for field in possible_fields:
                    if field in entry and entry[field]:
                        setattr(normalized_entry, norm_field, str(entry[field]).strip())
                        break

            # Platform-specific adjustments using config
            if platform.startswith('linux'):
                # Linux ip neigh format might need state translation
                if normalized_entry.state:
                    # Use config-driven state mapping if available
                    state_mapping = self.platform_config.get_field_mapping(platform, 'arp_states')
                    if state_mapping:
                        normalized_entry.state = state_mapping.get(normalized_entry.state, normalized_entry.state)
                    else:
                        # Fallback mapping
                        state_map = {'REACHABLE': 'Active', 'STALE': 'Incomplete'}
                        normalized_entry.state = state_map.get(normalized_entry.state, normalized_entry.state)
            elif platform.startswith('cisco'):
                # Cisco ARP entries are typically "ARPA" type
                if not normalized_entry.type:
                    normalized_entry.type = "ARPA"

            normalized.append(normalized_entry)

        return normalized

    def normalize_routes(self, parsed_data: List[Dict], platform: str) -> List[NormalizedRouteData]:
        """
        FIXED: Platform-aware route normalization that handles different field names per platform
        Uses both hardcoded mappings AND platform-specific JSON config
        """
        print(f"=== PLATFORM-AWARE ROUTE NORMALIZATION ===")
        print(f"Platform: {platform}")
        print(f"Input data count: {len(parsed_data)}")

        if parsed_data and len(parsed_data) > 0:
            print(f"Sample input entry: {parsed_data[0]}")
            print(f"Available fields: {list(parsed_data[0].keys())}")

        normalized = []

        # Get platform-specific field mappings from JSON config
        platform_field_mappings = self._get_platform_field_mappings(platform)
        print(f"Platform field mappings: {platform_field_mappings}")

        for i, entry in enumerate(parsed_data):
            print(f"\nProcessing entry {i}: {entry}")

            normalized_entry = NormalizedRouteData(
                network="",
                next_hop="",
                protocol=""
            )

            # Platform-aware field extraction
            normalized_entry = self._extract_route_fields(entry, platform, platform_field_mappings)

            # Platform-specific protocol normalization
            if normalized_entry.protocol:
                normalized_entry.protocol = self._normalize_protocol(
                    normalized_entry.protocol, platform
                )

            # Validate and add entry
            if self._is_valid_route_entry(normalized_entry):
                normalized.append(normalized_entry)
                print(f"   Entry added: {normalized_entry.network} via {normalized_entry.next_hop} ({normalized_entry.protocol})")
            else:
                print(f"   Entry rejected - validation failed")
                self._log_validation_failure(normalized_entry)

        print(f"\n=== NORMALIZATION COMPLETE ===")
        print(f"Input entries: {len(parsed_data)}")
        print(f"Output entries: {len(normalized)}")

        return normalized

    def _get_platform_field_mappings(self, platform: str) -> Dict[str, List[str]]:
        """
        Get platform-specific field mappings, combining hardcoded and JSON config
        """
        # Base field mappings (fallback for all platforms)
        base_mappings = self.ROUTE_FIELD_MAPPINGS.copy()

        # Platform-specific overrides
        platform_overrides = {
            'cisco_ios': {
                'network': ['NETWORK', 'network'],
                'mask': ['PREFIX_LENGTH', 'mask'],
                'next_hop': ['NEXTHOP_IP', 'nexthop'],
                'interface': ['NEXTHOP_IF', 'interface'],
                'protocol': ['PROTOCOL', 'protocol'],
                'metric': ['METRIC', 'metric'],
                'admin_distance': ['DISTANCE', 'admin_distance'],
                'age': ['UPTIME', 'age'],
                'vrf': ['VRF', 'vrf']
            },
            'cisco_nxos': {
                'network': ['NETWORK', 'network'],
                'mask': ['PREFIX_LENGTH', 'mask'],
                'next_hop': ['NEXTHOP_IP', 'nexthop'],
                'interface': ['NEXTHOP_IF', 'interface'],
                'protocol': ['PROTOCOL', 'protocol'],
                'metric': ['METRIC', 'metric'],
                'admin_distance': ['DISTANCE', 'admin_distance'],
                'age': ['UPTIME', 'age'],
                'vrf': ['VRF', 'vrf']
            },
            'arista_eos': {
                'network': ['PREFIX', 'NETWORK', 'network'],
                'mask': ['PREFIX_LENGTH', 'MASK', 'mask'],
                'next_hop': ['VIA', 'NEXTHOP_IP', 'nexthop'],
                'interface': ['INTERFACE', 'NEXTHOP_IF', 'interface'],
                'protocol': ['ROUTE_TYPE', 'PROTOCOL', 'protocol'],
                'metric': ['METRIC', 'COST', 'metric'],
                'admin_distance': ['AD', 'DISTANCE', 'admin_distance'],
                'age': ['AGE', 'UPTIME', 'age'],
                'vrf': ['VRF', 'TABLE', 'vrf']
            },
            'linux': {
                'network': ['DESTINATION', 'DST', 'network'],
                'mask': ['PREFIX_LENGTH', 'PREFIXLEN', 'mask'],
                'next_hop': ['GATEWAY', 'VIA', 'nexthop'],
                'interface': ['INTERFACE', 'DEV', 'interface'],
                'protocol': ['PROTO', 'PROTOCOL', 'protocol'],
                'metric': ['METRIC', 'metric'],
                'admin_distance': ['DISTANCE', 'admin_distance'],
                'age': ['AGE', 'age'],
                'vrf': ['TABLE', 'vrf']
            }
        }

        # Use platform-specific mappings if available, otherwise use base
        if platform in platform_overrides:
            return platform_overrides[platform]
        else:
            # Check if platform starts with known prefix
            for known_platform in platform_overrides:
                if platform.startswith(known_platform):
                    return platform_overrides[known_platform]

            return base_mappings

    def _extract_route_fields(self, entry: Dict, platform: str,
                              field_mappings: Dict[str, List[str]]) -> NormalizedRouteData:
        """
        Extract route fields using platform-specific field mappings - FIXED for Arista lists
        """
        result = NormalizedRouteData(network="", next_hop="", protocol="")

        print(f"\n EXTRACTING FIELDS DEBUG:")
        print(f"  Raw entry: {entry}")

        # Extract each field using the mapping priority
        for norm_field, possible_fields in field_mappings.items():
            value = None
            for field_name in possible_fields:
                if field_name in entry and entry[field_name] is not None:
                    raw_value = entry[field_name]

                    print(f"  Processing {norm_field} from {field_name}: {raw_value} (type: {type(raw_value)})")

                    # Handle list values (common in Arista for multi-path routes)
                    if isinstance(raw_value, list):
                        if raw_value:  # Non-empty list
                            if norm_field in ['next_hop', 'interface']:
                                # For next_hop and interface, handle carefully
                                cleaned_values = []
                                for v in raw_value:
                                    v_str = str(v).strip()
                                    # Filter out 'connected' strings for next_hop
                                    if norm_field == 'next_hop':
                                        if v_str and v_str != 'connected' and v_str not in cleaned_values:
                                            cleaned_values.append(v_str)
                                    else:
                                        # For interface, keep all non-empty values
                                        if v_str and v_str not in cleaned_values:
                                            cleaned_values.append(v_str)

                                if cleaned_values:
                                    if len(cleaned_values) == 1:
                                        value = cleaned_values[0]
                                    else:
                                        # Multiple paths - join with separator
                                        value = " | ".join(cleaned_values)
                                    print(f"    List processed to: '{value}'")
                                else:
                                    print(f"    List was empty after cleaning")
                            else:
                                # For other fields, just take the first non-empty value
                                for v in raw_value:
                                    v_str = str(v).strip()
                                    if v_str:
                                        value = v_str
                                        print(f"    List first value: '{value}'")
                                        break
                    else:
                        # Single value
                        value = str(raw_value).strip()
                        print(f"    Single value: '{value}'")

                    if value:  # Only use non-empty values
                        break

            if value:
                setattr(result, norm_field, value)
                print(f"     Set {norm_field} = '{value}'")

        # Special handling for network field combination
        result = self._handle_network_combination(result, entry, platform)

        # FIXED: Use the corrected next hop determination
        result = self._handle_next_hop_determination(result, entry, platform)

        return result

    def _handle_network_combination(self, result: NormalizedRouteData, entry: Dict, platform: str) -> NormalizedRouteData:
        """
        Handle platform-specific network/prefix combination logic
        """
        network = result.network
        mask = result.mask

        print(f"    Network combination: network='{network}', mask='{mask}'")

        # Different platforms handle network/mask differently
        if platform.startswith('cisco'):
            # Cisco: NETWORK='172.16.1.0', PREFIX_LENGTH='24' -> '172.16.1.0/24'
            if network and mask and '/' not in network:
                if mask == '0' and network == '0.0.0.0':
                    result.network = "0.0.0.0/0"  # Default route
                elif mask != '0':
                    result.network = f"{network}/{mask}"

        elif platform.startswith('arista'):
            # Arista might have different format
            if network and mask and '/' not in network:
                result.network = f"{network}/{mask}"

        elif platform.startswith('linux'):
            # Linux might already have CIDR notation
            if network and '/' not in network and mask:
                result.network = f"{network}/{mask}"
            elif network == 'default':
                result.network = "0.0.0.0/0"

        print(f"    Final network: '{result.network}'")
        return result

    def _handle_next_hop_determination(self, result: NormalizedRouteData, entry: Dict,
                                       platform: str) -> NormalizedRouteData:
        """
        Handle platform-specific next hop determination logic - FIXED for Arista
        """
        print(f" NEXT HOP DEBUG:")
        print(f"  Platform: {platform}")
        print(f"  Current next_hop: '{result.next_hop}'")
        print(f"  Current interface: '{result.interface}'")
        print(f"  Raw entry keys: {list(entry.keys())}")

        # Check DIRECT field for Arista
        direct_value = entry.get('DIRECT', '')
        print(f"  DIRECT field: '{direct_value}'")

        # Only set to "Directly Connected" if:
        # 1. DIRECT field explicitly says "directly" AND
        # 2. We don't already have a valid next_hop
        if direct_value == 'directly':
            if not result.next_hop or result.next_hop in ['', 'connected']:
                result.next_hop = "Directly Connected"
                print(f"     Set to 'Directly Connected' (DIRECT='directly')")
            else:
                print(f"     DIRECT='directly' but already have next_hop: '{result.next_hop}'")

        # If we have a valid next_hop, keep it
        elif result.next_hop and result.next_hop not in ['', 'connected']:
            print(f"     Keeping existing next_hop: '{result.next_hop}'")

        # If no next_hop but we have an interface, it might be directly connected
        elif not result.next_hop and result.interface:
            # For Cisco Connected/Local routes
            if platform.startswith('cisco') and result.protocol in ['C', 'Connected', 'L', 'Local']:
                result.next_hop = "Directly Connected"
                print(f"     Cisco connected route, set to 'Directly Connected'")
            # For other platforms, be more conservative
            elif result.protocol in ['Connected', 'C']:
                result.next_hop = "Directly Connected"
                print(f"     Connected protocol, set to 'Directly Connected'")
            else:
                result.next_hop = "Interface Only"
                print(f"    No next_hop but has interface, set to 'Interface Only'")

        # Last resort
        elif not result.next_hop:
            result.next_hop = "Unspecified"
            print(f"     No next_hop found, set to 'Unspecified'")

        print(f"    Final next_hop: '{result.next_hop}'")
        return result

    # In netmiko_controller.py, update the _normalize_protocol method in ConfigDrivenFieldNormalizer:

    def _normalize_protocol(self, protocol: str, platform: str) -> str:
        """
        Normalize protocol codes using platform configuration - ENHANCED VERSION
        """
        print(f" CONTROLLER DEBUG: Normalizing protocol '{protocol}' for platform '{platform}'")

        # Get protocol mapping from platform config first
        protocol_mapping = self.platform_config.get_field_mapping(platform, 'protocols')

        if protocol_mapping and protocol in protocol_mapping:
            result = protocol_mapping[protocol]
            print(f"   Platform config mapping: '{protocol}' -> '{result}'")
            return result

        # Enhanced fallback platform-specific mappings (same as template editor)
        fallback_mappings = {
            'arista_eos': {
                "S": "Static",
                "S*": "Static Default",
                "C": "Connected",
                "O": "OSPF",
                "OI": "OSPF Inter-Area",
                "OE": "OSPF External",
                "ON": "OSPF NSSA",
                "B": "BGP",
                "BI": "BGP Internal",
                "BE": "BGP External",
                "I": "ISIS",
                "i": "ISIS",
                "L1": "ISIS Level-1",
                "L2": "ISIS Level-2",
                "K": "Kernel",
                "D": "EIGRP",
                "R": "RIP",
                "M": "Mobile",
                "E": "EIGRP",  # Add this - sometimes shows as E
                "static": "Static",
                "connected": "Connected",
                "ospf": "OSPF",
                "bgp": "BGP",
                "isis": "ISIS",
                "kernel": "Kernel",
                "rip": "RIP"
            },
            'cisco_ios': {
                'S': 'Static', 'S*': 'Static Default', 'C': 'Connected', 'L': 'Local',
                'O': 'OSPF', 'OI': 'OSPF Inter-Area', 'OE': 'OSPF External', 'ON': 'OSPF NSSA',
                'B': 'BGP', 'D': 'EIGRP', 'R': 'RIP', 'I': 'IGRP', 'M': 'Mobile', 'N': 'NAT'
            },
            'cisco_nxos': {
                'S': 'Static', 'C': 'Connected', 'L': 'Local',
                'O': 'OSPF', 'OI': 'OSPF Inter-Area', 'OE': 'OSPF External',
                'B': 'BGP', 'D': 'EIGRP', 'E': 'EIGRP', 'R': 'RIP', 'I': 'ISIS'
            },
            'linux': {
                'static': 'Static', 'connected': 'Connected',
                'kernel': 'Kernel', 'ospf': 'OSPF', 'bgp': 'BGP'
            }
        }

        # Check platform family
        platform_map = None
        for platform_family, mapping in fallback_mappings.items():
            if platform.startswith(platform_family):
                platform_map = mapping
                break

        if not platform_map:
            platform_map = fallback_mappings.get('cisco_ios', {})

        print(f"  Using fallback mappings for platform family, available codes: {list(platform_map.keys())}")

        # Clean the protocol string
        protocol_clean = protocol.strip()

        # Try exact match
        if protocol_clean in platform_map:
            result = platform_map[protocol_clean]
            print(f"   Exact match: '{protocol_clean}' -> '{result}'")
            return result

        # Try case-insensitive match
        for code, name in platform_map.items():
            if code.lower() == protocol_clean.lower():
                result = name
                print(f"   Case-insensitive match: '{protocol_clean}' -> '{result}'")
                return result

        # Try without flags
        protocol_base = protocol_clean.rstrip('*%+')
        if protocol_base in platform_map:
            base_name = platform_map[protocol_base]
            if '*' in protocol_clean:
                result = f"{base_name} Default"
            else:
                result = base_name
            print(f"   Base match: '{protocol_clean}' -> '{result}'")
            return result

        # For already spelled-out protocols (case insensitive)
        protocol_upper = protocol_clean.upper()
        if protocol_upper in ['BGP', 'OSPF', 'EIGRP', 'ISIS', 'RIP', 'STATIC', 'CONNECTED', 'KERNEL']:
            result = protocol_clean.title()
            print(f"   Spelled-out match: '{protocol_clean}' -> '{result}'")
            return result

        # Return original if no mapping found
        print(f"   No mapping found for '{protocol_clean}', returning as-is")
        return protocol_clean
    def _is_valid_route_entry(self, entry: NormalizedRouteData) -> bool:
        """
        Validate if route entry has minimum required fields
        """
        # Must have a network
        if not entry.network or entry.network.strip() == "":
            return False

        # Must have either next_hop or interface (be more lenient)
        # Some routes might not have explicit next hop but still be valid
        return True

    def _log_validation_failure(self, entry: NormalizedRouteData):
        """
        Log why a route entry failed validation
        """
        reasons = []
        if not entry.network:
            reasons.append("missing network")
        if not entry.next_hop and not entry.interface:
            reasons.append("missing next_hop and interface")

        print(f"    Validation failed: {', '.join(reasons)}")
        print(f"    Entry: network='{entry.network}', next_hop='{entry.next_hop}', interface='{entry.interface}'")

    def normalize_system_info(self, parsed_data: List[Dict], platform: str) -> Dict:
        """Normalize system information using platform-specific field mappings from JSON config"""
        print(f" DEBUG normalize_system_info (config-driven):")
        print(f"  Input parsed_data: {parsed_data}")
        print(f"  Platform: {platform}")

        if not parsed_data:
            print(f"   No parsed data provided")
            return {}

        # Take the first entry (should only be one for show version)
        entry = parsed_data[0]
        print(f"  Processing entry: {entry}")

        normalized = {}

        # Get platform-specific field mappings from JSON config
        system_info_mappings = self.platform_config.get_field_mapping(platform, 'system_info_fields')
        print(f"  Platform-specific mappings: {system_info_mappings}")

        if system_info_mappings:
            # Use platform-specific mappings from JSON
            for template_field, normalized_field in system_info_mappings.items():
                if template_field in entry and entry[template_field]:
                    value = str(entry[template_field]).strip()
                    normalized[normalized_field] = value
                    print(f"     Found {normalized_field} = '{value}' from template field '{template_field}'")
        else:
            # Fallback to hardcoded mappings
            print(f"  No platform-specific mappings found, using fallback mappings")

            # Fallback field mappings
            fallback_mappings = {
                'hostname': ['HOSTNAME', 'hostname', 'device_name'],
                'version': ['VERSION', 'version', 'software_version', 'IMAGE', 'HW_VERSION'],
                'model': ['HARDWARE', 'hardware', 'model', 'platform', 'MODEL'],
                'serial': ['SERIAL', 'serial', 'serial_number', 'SERIAL_NUMBER'],
                'uptime': ['UPTIME', 'uptime'],
                'software_version': ['SOFTWARE_IMAGE', 'software_image', 'image', 'IMAGE'],
                'config_register': ['CONFIG_REGISTER', 'config_register']
            }

            for norm_field, possible_fields in fallback_mappings.items():
                found_value = None
                for field in possible_fields:
                    if field in entry and entry[field]:
                        found_value = str(entry[field]).strip()
                        normalized[norm_field] = found_value
                        print(f"       Found {norm_field} = '{found_value}' from field '{field}'")
                        break

                if not found_value:
                    print(f"      No value found for {norm_field}")

        # Handle list fields (like SERIAL, HARDWARE in some templates)
        for field_name in ['serial', 'model']:
            if field_name in normalized and isinstance(normalized[field_name], list):
                if normalized[field_name]:
                    normalized[field_name] = ', '.join(str(x) for x in normalized[field_name])
                else:
                    normalized[field_name] = ""

        print(f"  Final normalized result: {normalized}")
        return normalized
class NetmikoConnectionManager:
    """UPDATED: Connection manager that uses platform configuration"""

    def __init__(self, platform_config_manager=None):
        self.connections: Dict[str, ConnectHandler] = {}
        self.connection_params: Dict[str, Dict] = {}
        self.platform_config = platform_config_manager

    def create_connection(self, device_info: DeviceInfo, credentials: ConnectionCredentials) -> bool:
        """Create a new netmiko connection using platform configuration"""
        if not NETMIKO_AVAILABLE:
            print("Netmiko not available, cannot create real connection")
            return False

        connection_key = f"{device_info.ip_address}:{credentials.port}"

        # Get netmiko configuration from platform config
        if self.platform_config:
            netmiko_config = self.platform_config.get_netmiko_config(device_info.platform)
            if netmiko_config:
                netmiko_platform = netmiko_config.device_type
                fast_cli = netmiko_config.fast_cli
                timeout = netmiko_config.timeout
                auth_timeout = netmiko_config.auth_timeout
                print(f"Using config-driven netmiko settings: {netmiko_platform}, fast_cli={fast_cli}")
            else:
                print(f"No netmiko configuration found for platform: {device_info.platform}")
                return False
        else:
            # Fallback to old hardcoded mapping if config not available
            print("Warning: Using fallback hardcoded platform mapping")
            platform_mapping = {
                'cisco_ios_xe': 'cisco_xe',
                'cisco_ios': 'cisco_ios',
                'cisco_nxos': 'cisco_nxos',
                'arista_eos': 'arista_eos',
                'aruba_aos_s': 'aruba_os',
                'aruba_aos_cx': 'aruba_os',
                'linux_rhel': 'linux',
                'linux_ubuntu': 'linux'
            }
            netmiko_platform = platform_mapping.get(device_info.platform, 'cisco_ios')
            fast_cli = False
            timeout = 30
            auth_timeout = 10

        connection_params = {
            'device_type': netmiko_platform,
            'host': device_info.ip_address,
            'username': credentials.username,
            'password': credentials.password,
            'secret': credentials.secret,
            'port': credentials.port,
            'timeout': timeout,
            'auth_timeout': auth_timeout,
            'fast_cli': fast_cli,
        }

        try:
            print(f"Connecting to {device_info.hostname} ({device_info.ip_address}) via netmiko...")
            connection = ConnectHandler(**connection_params)

            # Test connection with a simple command
            if netmiko_platform.startswith('cisco'):
                test_output = connection.send_command("show clock")
            elif netmiko_platform == 'arista_eos':
                test_output = connection.send_command("show clock")
            elif netmiko_platform == 'linux':
                test_output = connection.send_command("date")
            else:
                test_output = connection.send_command("show version", read_timeout=10)

            if test_output:
                self.connections[connection_key] = connection
                self.connection_params[connection_key] = connection_params
                print(f"Successfully connected to {device_info.hostname}")
                return True
            else:
                print(f"Connection test failed for {device_info.hostname}")
                connection.disconnect()
                return False

        except NetmikoAuthenticationException as e:
            print(f"Authentication failed for {device_info.hostname}: {e}")
            return False
        except NetmikoTimeoutException as e:
            print(f"Connection timeout for {device_info.hostname}: {e}")
            return False
        except NetmikoBaseException as e:
            print(f"Netmiko error connecting to {device_info.hostname}: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error connecting to {device_info.hostname}: {e}")
            return False

    def execute_command(self, device_ip: str, port: int, command: str) -> tuple[bool, str]:
        """Execute command on connected device"""
        connection_key = f"{device_ip}:{port}"

        if connection_key not in self.connections:
            return False, "No active connection found"

        try:
            connection = self.connections[connection_key]
            output = connection.send_command(command, read_timeout=30)
            return True, output
        except Exception as e:
            print(f"Error executing command '{command}': {e}")
            return False, str(e)

    def disconnect(self, device_ip: str, port: int = 22):
        """Disconnect from device"""
        connection_key = f"{device_ip}:{port}"

        if connection_key in self.connections:
            try:
                self.connections[connection_key].disconnect()
                del self.connections[connection_key]
                del self.connection_params[connection_key]
                print(f"Disconnected from {device_ip}")
            except Exception as e:
                print(f"Error disconnecting from {device_ip}: {e}")

    def disconnect_all(self):
        """Disconnect from all devices"""
        for connection_key in list(self.connections.keys()):
            device_ip = connection_key.split(':')[0]
            port = int(connection_key.split(':')[1])
            self.disconnect(device_ip, port)


class EnhancedPlatformAwareTelemetryController(QObject):
    """
    UPDATED: Enhanced controller with JSON-driven platform configuration
    FIXED: Route normalization with platform-aware field mapping
    """

    # Signals for raw command outputs
    raw_cdp_output = pyqtSignal(RawCommandOutput)
    raw_arp_output = pyqtSignal(RawCommandOutput)
    raw_interface_output = pyqtSignal(RawCommandOutput)
    raw_route_output = pyqtSignal(RawCommandOutput)
    raw_vrf_list_output = pyqtSignal(RawCommandOutput)
    raw_log_output = pyqtSignal(RawCommandOutput)
    raw_system_info_output = pyqtSignal(RawCommandOutput)
    raw_cpu_output = pyqtSignal(RawCommandOutput)
    raw_memory_output = pyqtSignal(RawCommandOutput)

    # Signals for normalized data
    normalized_neighbors_ready = pyqtSignal(list)  # List[NormalizedNeighborData]
    normalized_arp_ready = pyqtSignal(list)  # List[NormalizedArpData]
    normalized_routes_ready = pyqtSignal(list)  # List[NormalizedRouteData]
    normalized_system_ready = pyqtSignal(object)  # NormalizedSystemData
    normalized_logs_ready = pyqtSignal(list)
    normalized_system_metrics_ready = pyqtSignal(object)  # NormalizedSystemMetrics

    # === NEW SYSTEM METRICS SIGNALS ===
    normalized_cpu_ready = pyqtSignal(object)  # CPU-specific data
    normalized_memory_ready = pyqtSignal(object)  # Memory-specific data
    normalized_temperature_ready = pyqtSignal(object)  # Temperature data

    # Raw system command signals (for debugging/template editing)
    raw_temperature_output = pyqtSignal(RawCommandOutput)
    # Status signals
    device_info_updated = pyqtSignal(DeviceInfo)
    connection_status_changed = pyqtSignal(str, str)  # device_ip, status
    theme_changed = pyqtSignal(str)

    def __init__(self, theme_library=None):
        super().__init__()
        self.theme_library = theme_library
        self.current_theme = "cyberpunk"
        self.device_info = None
        self.platform = "unknown"

        # UPDATED: Load platform configuration
        self.platform_config = PlatformConfigManager('config/platforms')
        print(f"Loaded {len(self.platform_config.get_available_platforms())} platform configurations")

        # UPDATED: Pass platform config to connection manager
        self.connection_manager = NetmikoConnectionManager(self.platform_config)
        self.credentials = None
        self.is_connected = False

        # UPDATED: Use config-driven field normalizer
        self.field_normalizer = ConfigDrivenFieldNormalizer(self.platform_config)
        self.local_template_parser = LocalTemplateParser() if TEXTFSM_AVAILABLE else None

        # Data collection timer
        self.data_collection_timer = QTimer()
        self.data_collection_timer.timeout.connect(self.collect_telemetry_data)



    def get_available_platforms(self) -> List[str]:
        """Get list of available platforms from configuration"""
        return self.platform_config.get_available_platforms()

    # Debug the get_platform_command method to see why it's returning "#"

    def get_platform_command(self, command_type: str, **kwargs) -> str:
        """UPDATED: Get platform-specific command from JSON configuration with debugging"""
        print(f"\n=== GET_PLATFORM_COMMAND DEBUG ===")
        print(f"Command type: '{command_type}'")
        print(f"Current platform: '{self.platform}'")
        print(f"Kwargs: {kwargs}")

        # Check if platform config exists
        if not self.platform_config:
            print(f" No platform_config available")
            return f"# No platform config available"

        # Check available platforms
        available_platforms = self.platform_config.get_available_platforms()
        print(f"Available platforms: {available_platforms}")

        # Check if current platform is in available platforms
        if self.platform not in available_platforms:
            print(f" Platform '{self.platform}' not in available platforms")
            return f"# Platform '{self.platform}' not supported"

        # Try to get the command
        try:
            command = self.platform_config.format_command(self.platform, command_type, **kwargs)
            print(f"Command lookup result: '{command}'")

            if command is None:
                print(f" format_command returned None")

                # Debug: Check what's in the platform definition
                platform_def = self.platform_config.get_platform(self.platform)
                if platform_def:
                    print(f"Platform definition exists: {platform_def.name}")
                    print(f"Available commands: {list(platform_def.commands.keys())}")

                    if command_type in platform_def.commands:
                        cmd_def = platform_def.commands[command_type]
                        print(f"Command definition: {cmd_def.command}")
                        print(f"Template: {cmd_def.template}")
                    else:
                        print(f" Command type '{command_type}' not found in platform commands")
                else:
                    print(f" Platform definition not found")

                return f"# No command configured for {self.platform}.{command_type}"

            print(f" Command found: '{command}'")
            return command

        except Exception as e:
            print(f" Exception in format_command: {e}")
            print(f"Exception type: {type(e).__name__}")
            return f"# Error getting command: {str(e)}"


    # Debug method to check platform configuration specifically
    def debug_platform_config(self):
        """Debug the platform configuration to see what's available"""
        print(f"\n" + "=" * 50)
        print(f"PLATFORM CONFIGURATION DEBUG")
        print(f"=" * 50)

        print(f"1. Current platform: '{self.platform}'")

        if not self.platform_config:
            print(f" No platform_config object")
            return

        # Check available platforms
        available = self.platform_config.get_available_platforms()
        print(f"2. Available platforms: {available}")

        # Check if current platform exists
        platform_def = self.platform_config.get_platform(self.platform)
        if not platform_def:
            print(f" Platform '{self.platform}' definition not found")
            return

        print(f"3. Platform definition found: {platform_def.display_name}")
        print(f"4. Available commands in platform:")
        for cmd_name, cmd_def in platform_def.commands.items():
            print(f"   - {cmd_name}: {cmd_def.command}")

        # Check specifically for route_table command
        if 'route_table' in platform_def.commands:
            route_cmd = platform_def.commands['route_table']
            print(f"5. Route table command found:")
            print(f"   Command: {route_cmd.command}")
            print(f"   Template: {route_cmd.template}")
            print(f"   Timeout: {route_cmd.timeout}")
        else:
            print(f" 'route_table' command not found in platform")

        # Test the format_command method directly
        try:
            formatted = self.platform_config.format_command(self.platform, 'route_table')
            print(f"6. format_command result: '{formatted}'")
        except Exception as e:
            print(f" format_command error: {e}")

        print(f"=" * 50)

    # Check what platform is actually being set during connection
    def connect_to_device(self, hostname: str, ip_address: str, platform: str,
                          credentials: ConnectionCredentials) -> bool:
        """UPDATED: Establish connection with platform validation and debugging"""
        print(f"\n=== CONNECTION DEBUG ===")
        print(f"Connecting to {hostname} ({ip_address}) - Platform: {platform}")

        # Check if platform is supported
        available_platforms = self.platform_config.get_available_platforms()
        print(f"Available platforms: {available_platforms}")

        if platform not in available_platforms:
            print(f" Unsupported platform: {platform}")
            print(f"Available platforms: {available_platforms}")
            return False

        self.device_info = DeviceInfo(
            hostname=hostname,
            ip_address=ip_address,
            platform=platform,
            connection_status="connecting"
        )

        # THIS IS CRITICAL - make sure self.platform is set correctly
        self.platform = platform
        print(f" Set self.platform to: '{self.platform}'")

        # Verify platform configuration exists for this platform
        platform_def = self.platform_config.get_platform(platform)
        if platform_def:
            print(f" Platform configuration found for '{platform}'")
            print(f"Available commands: {list(platform_def.commands.keys())}")
        else:
            print(f" No platform configuration found for '{platform}'")
            return False

        self.credentials = credentials

        # Emit status update
        self.connection_status_changed.emit(ip_address, "connecting")

        # Try to establish connection
        success = self.connection_manager.create_connection(self.device_info, credentials)

        if success:
            self.is_connected = True
            self.device_info.connection_status = "connected"
            self.connection_status_changed.emit(ip_address, "connected")

            # Collect initial system info
            self._collect_system_info()

            # Start periodic data collection
            self.data_collection_timer.start(30000)  # Every 10 seconds

            self.device_info_updated.emit(self.device_info)
            print(f" Successfully connected to {hostname}")

            # Debug: Verify platform is still set correctly after connection
            print(f" After connection, self.platform = '{self.platform}'")

            return True
        else:
            self.is_connected = False
            self.device_info.connection_status = "failed"
            self.connection_status_changed.emit(ip_address, "failed")
            self.device_info_updated.emit(self.device_info)
            print(f" Failed to connect to {hostname}")
            return False

    # Quick fix method to check and fix platform issues
    def fix_platform_issue(self):
        """Quick method to diagnose and potentially fix platform issues"""
        print(f"\n PLATFORM ISSUE DIAGNOSTIC ")

        # Check 1: Is platform set?
        print(f"1. Current platform: '{getattr(self, 'platform', 'NOT SET')}'")

        # Check 2: Is platform_config available?
        if hasattr(self, 'platform_config') and self.platform_config:
            print(f"2.  Platform config available")
            available = self.platform_config.get_available_platforms()
            print(f"   Available platforms: {available}")
        else:
            print(f"2.  No platform config")
            return

        # Check 3: Does current platform have route_table command?
        if hasattr(self, 'platform') and self.platform:
            try:
                cmd = self.get_platform_command('route_table')
                print(f"3. Route command: '{cmd}'")

                if cmd.startswith('#'):
                    print(f"    Command lookup failed")

                    # Try to fix by checking available platforms
                    available = self.platform_config.get_available_platforms()
                    if 'cisco_ios' in available:
                        print(f"    Trying to fix by setting platform to 'cisco_ios'")
                        self.platform = 'cisco_ios'
                        cmd = self.get_platform_command('route_table')
                        print(f"   Fixed command: '{cmd}'")

                else:
                    print(f"    Command lookup successful")

            except Exception as e:
                print(f"3.  Error getting route command: {e}")
        else:
            print(f"3.  No platform set")


    def _collect_system_info(self):
        """UPDATED: Collect system info using JSON configuration"""
        if not self.is_connected:
            return

        sys_info_cmd = self.get_platform_command('system_info')
        if sys_info_cmd.startswith("#"):  # Unknown command
            print(f"No system_info command configured for platform {self.platform}")
            return

        success, output = self.connection_manager.execute_command(
            self.device_info.ip_address,
            self.credentials.port,
            sys_info_cmd
        )

        if success:
            # Get template info from configuration
            template_info = self.platform_config.get_template_info(self.platform, 'system_info')
            if template_info:
                template_platform, template_file = template_info
                template_command = template_file.replace('.textfsm', '').replace(f'{template_platform}_', '')
                parsed_data = self._parse_with_template(output, template_platform, template_command)
            else:
                parsed_data = None

            # Update device info with parsed data
            if parsed_data and isinstance(parsed_data, list) and len(parsed_data) > 0:
                normalized_sys_info = self.field_normalizer.normalize_system_info(parsed_data, self.platform)

                # Update device info with normalized data
                if 'hostname' in normalized_sys_info:
                    self.device_info.hostname = normalized_sys_info['hostname']
                if 'version' in normalized_sys_info:
                    self.device_info.version = normalized_sys_info['version']
                if 'model' in normalized_sys_info:
                    self.device_info.model = normalized_sys_info['model']
                if 'serial' in normalized_sys_info:
                    self.device_info.serial = normalized_sys_info['serial']
                if 'uptime' in normalized_sys_info:
                    self.device_info.uptime = normalized_sys_info['uptime']

            self.raw_system_info_output.emit(RawCommandOutput(
                command=sys_info_cmd,
                output=output,
                platform=self.platform,
                timestamp=time.time(),
                template_used=template_info[1] if template_info else 'none',
                parsed_successfully=bool(parsed_data)
            ))

    def _parse_with_template(self, output: str, platform: str, command: str) -> Optional[List[Dict]]:
        """Parse command output using local TextFSM templates"""
        if not TEXTFSM_AVAILABLE or not self.local_template_parser:
            print(f"TextFSM not available for parsing {platform} {command}")
            return None

        try:
            print(f"Attempting to parse: platform='{platform}', command='{command}'")
            print(f"Output length: {len(output)} characters")

            # Use our local template parser
            parsed_data = self.local_template_parser.parse(platform, command, output)

            if parsed_data:
                print(f" Local template parsing successful! Got {len(parsed_data)} entries")
                if len(parsed_data) > 0:
                    print(f"  First entry fields: {list(parsed_data[0].keys())}")
            else:
                print(f" Local template parsing returned empty result")

            return parsed_data

        except FileNotFoundError as e:
            print(f" Template file not found: {e}")
            return None

        except Exception as e:
            print(f" Local template parsing failed for {platform} {command}: {e}")
            sample_output = output[:200].replace('\n', '\\n')
            print(f"  Sample output: {sample_output}...")
            return None

    def execute_command_and_parse(self, command_type: str, **kwargs) -> tuple[bool, str, Optional[List[Dict]]]:
        """UPDATED: Execute command and parse using JSON configuration"""
        if not self.is_connected:
            return False, "Not connected to device", None

        command = self.get_platform_command(command_type, **kwargs)
        print(f"SSH COMMAND:")
        if command.startswith("#"):  # Error/unknown command
            return False, f"Unknown command type: {command_type}", None

        success, output = self.connection_manager.execute_command(
            self.device_info.ip_address,
            self.credentials.port,
            command
        )

        parsed_data = None
        if success and output:
            # Get template info from configuration
            template_info = self.platform_config.get_template_info(self.platform, command_type)
            if template_info:
                template_platform, template_file = template_info
                # Convert template filename to command name for parser
                template_command = template_file.replace('.textfsm', '').replace(f'{template_platform}_', '')
                parsed_data = self._parse_with_template(output, template_platform, template_command)

        return success, output, parsed_data

    def collect_telemetry_data(self):
        """Collect telemetry data using platform-specific commands with template parsing"""
        if not self.is_connected:
            return

        print(f"Collecting telemetry data from {self.platform}...")

        # CDP/LLDP neighbors with normalization
        success, output, parsed_data = self.execute_command_and_parse('cdp_neighbors')
        if success:
            command_used = self.get_platform_command('cdp_neighbors')
            self.raw_cdp_output.emit(RawCommandOutput(
                command=command_used,
                output=output,
                platform=self.platform,
                timestamp=time.time(),
                parsed_successfully=bool(parsed_data)
            ))

            if parsed_data:
                normalized_neighbors = self.field_normalizer.normalize_neighbors(
                    parsed_data, self.platform, command_used
                )
                self.normalized_neighbors_ready.emit(normalized_neighbors)

        # ARP table with normalization
        success, output, parsed_data = self.execute_command_and_parse('arp_table')
        if success:
            self.raw_arp_output.emit(RawCommandOutput(
                command=self.get_platform_command('arp_table'),
                output=output,
                platform=self.platform,
                timestamp=time.time(),
                parsed_successfully=bool(parsed_data)
            ))

            if parsed_data:
                normalized_arp = self.field_normalizer.normalize_arp(parsed_data, self.platform)
                self.normalized_arp_ready.emit(normalized_arp)

        # Route table with enhanced normalization
        success, output, parsed_data = self.execute_command_and_parse('route_table')
        if success:
            self.raw_route_output.emit(RawCommandOutput(
                command=self.get_platform_command('route_table'),
                output=output,
                platform=self.platform,
                timestamp=time.time(),
                parsed_successfully=bool(parsed_data)
            ))

            if parsed_data:
                normalized_routes = self.field_normalizer.normalize_routes(parsed_data, self.platform)
                self.normalized_routes_ready.emit(normalized_routes)

        # VRF list collection
        success, output, parsed_data = self.execute_command_and_parse('vrf_list')
        if success:
            self.raw_vrf_list_output.emit(RawCommandOutput(
                command=self.get_platform_command('vrf_list'),
                output=output,
                platform=self.platform,
                timestamp=time.time(),
                parsed_successfully=bool(parsed_data)
            ))

        # === NEW: CPU UTILIZATION DATA COLLECTION ===
        success, output, parsed_data = self.execute_command_and_parse('cpu_utilization')
        if success:
            print(f" CPU command executed successfully")

            # Create a CPU-specific signal if it doesn't exist, or use existing one
            cpu_raw_output = RawCommandOutput(
                command=self.get_platform_command('cpu_utilization'),
                output=output,
                platform=self.platform,
                timestamp=time.time(),
                parsed_successfully=bool(parsed_data)
            )
            if parsed_data:
                cpu_raw_output.parsed_data = parsed_data

            if parsed_data:
                normalized_cpu_data = self._normalize_cpu_data(parsed_data)
                if normalized_cpu_data:
                    self.normalized_system_ready.emit(normalized_cpu_data)

            # Emit to existing signal or create new one
            if hasattr(self, 'raw_cpu_output'):
                self.raw_cpu_output.emit(cpu_raw_output)
            else:
                # Use system info signal as fallback
                self.raw_system_info_output.emit(cpu_raw_output)

            print(f"CPU parsed data: {parsed_data}")

        # === ENHANCED: SYSTEM METRICS COLLECTION ===
        self._collect_system_metrics()
        # === NEW: MEMORY UTILIZATION DATA COLLECTION ===
        success, output, parsed_data = self.execute_command_and_parse('memory_utilization')
        if success:
            print(f" Memory command executed successfully")

            memory_raw_output = RawCommandOutput(
                command=self.get_platform_command('memory_utilization'),
                output=output,
                platform=self.platform,
                timestamp=time.time(),
                parsed_successfully=bool(parsed_data)
            )
            if parsed_data:
                memory_raw_output.parsed_data = parsed_data
            # Emit to memory signal or fallback
            if hasattr(self, 'raw_memory_output'):
                self.raw_memory_output.emit(memory_raw_output)
            else:
                # Use system info signal as fallback
                self.raw_system_info_output.emit(memory_raw_output)

            print(f"Memory parsed data: {parsed_data}")

        # === NEW: LOGS DATA COLLECTION ===
        success, output, parsed_data = self.execute_command_and_parse('logs')
        if success:
            print(f" Logs command executed successfully")

            self.raw_log_output.emit(RawCommandOutput(
                command=self.get_platform_command('logs'),
                output=output,
                platform=self.platform,
                timestamp=time.time(),
                parsed_successfully=bool(parsed_data)
            ))

    def _collect_system_metrics(self):
        """Collect and normalize system metrics - LOWEST COMMON DENOMINATOR"""
        print(f" Collecting basic system metrics for platform: {self.platform}")

        metrics = NormalizedSystemMetrics()
        metrics.platform = self.platform
        metrics.timestamp = time.time()

        # CPU utilization - REQUIRED
        cpu_success, cpu_output, cpu_parsed = self.execute_command_and_parse('cpu_utilization')
        if cpu_success and cpu_parsed:
            cpu_percent = self._normalize_cpu_utilization(cpu_parsed)
            if cpu_percent is not None:
                metrics.cpu_usage_percent = cpu_percent
                print(f" CPU: {cpu_percent}%")

                # Optional: Try to extract load averages if available
                cpu_entry = cpu_parsed[0]
                if 'GLOBAL_LOAD_AVERAGE_1_MINUTES' in cpu_entry:
                    metrics.load_1min = float(cpu_entry['GLOBAL_LOAD_AVERAGE_1_MINUTES'])
                if 'GLOBAL_LOAD_AVERAGE_5_MINUTES' in cpu_entry:
                    metrics.load_5min = float(cpu_entry['GLOBAL_LOAD_AVERAGE_5_MINUTES'])

        # Memory utilization - REQUIRED
        mem_success, mem_output, mem_parsed = self.execute_command_and_parse('memory_utilization')
        if mem_success and mem_parsed:
            memory_metrics = self._normalize_memory_utilization(mem_parsed)
            if memory_metrics:
                metrics.memory_used_percent = memory_metrics['used_percent']
                metrics.memory_total_mb = memory_metrics['total_mb']
                metrics.memory_free_mb = memory_metrics['free_mb']
                metrics.memory_used_mb = memory_metrics['used_mb']
                print(
                    f" Memory: {metrics.memory_used_percent}% ({metrics.memory_used_mb}/{metrics.memory_total_mb} MB)")

        # Temperature - OPTIONAL (skip if not supported)
        platform_def = self.platform_config.get_platform(self.platform)
        if platform_def and platform_def.capabilities.supports_temperature:
            temp_success, temp_output, temp_parsed = self.execute_command_and_parse('temperature')
            if temp_success and temp_parsed:
                temp_celsius = self._normalize_temperature(temp_parsed)
                if temp_celsius is not None:
                    metrics.temperature_celsius = temp_celsius
                    print(f" Temperature: {temp_celsius}°C")

        # Process counts - OPTIONAL (from CPU command if available)
        if cpu_parsed and len(cpu_parsed) > 0:
            cpu_entry = cpu_parsed[0]
            if 'GLOBAL_TASKS_TOTAL' in cpu_entry:
                metrics.process_count_total = int(cpu_entry['GLOBAL_TASKS_TOTAL'])
            if 'GLOBAL_TASKS_RUNNING' in cpu_entry:
                metrics.process_count_running = int(cpu_entry['GLOBAL_TASKS_RUNNING'])

        # Emit SIMPLE normalized metrics
        self.normalized_system_metrics_ready.emit(metrics)
        print(f" Basic system metrics normalized and emitted")
        print(f"   CPU: {metrics.cpu_usage_percent}%, Memory: {metrics.memory_used_percent}%")

    def _normalize_cpu_utilization(self, parsed_data) -> Optional[float]:
        """Normalize CPU utilization - LOWEST COMMON DENOMINATOR approach"""
        if not parsed_data or len(parsed_data) == 0:
            return None

        cpu_entry = parsed_data[0]
        print(f" Normalizing CPU data: {list(cpu_entry.keys())}")

        # Platform-specific CPU field mapping - NORMALIZE DOWN to simple percentage
        if self.platform.startswith('cisco'):
            # Cisco: Simple CPU usage fields
            for field in ['CPU_USAGE_5_SEC', 'CPU_5_SEC', 'CPU_USAGE']:
                if field in cpu_entry:
                    return float(cpu_entry[field])

        elif self.platform.startswith('arista'):
            # Arista: Rich CPU data - REDUCE to simple total usage
            if 'GLOBAL_CPU_PERCENT_IDLE' in cpu_entry:
                idle_percent = float(cpu_entry['GLOBAL_CPU_PERCENT_IDLE'])
                return 100.0 - idle_percent  # Simple total usage
            elif 'GLOBAL_CPU_PERCENT_USER' in cpu_entry and 'GLOBAL_CPU_PERCENT_SYSTEM' in cpu_entry:
                user_percent = float(cpu_entry['GLOBAL_CPU_PERCENT_USER'])
                system_percent = float(cpu_entry['GLOBAL_CPU_PERCENT_SYSTEM'])
                # IGNORE nice, iowait, irq details - just user + system for compatibility
                return user_percent + system_percent

        elif self.platform.startswith('linux'):
            # Linux: May have detailed breakdown, reduce to simple usage
            for field in ['CPU_PERCENT', 'CPU_USAGE', 'USER_PERCENT']:
                if field in cpu_entry:
                    return float(cpu_entry[field])

        print(f" No CPU field found in: {list(cpu_entry.keys())}")
        return None

    def _normalize_memory_utilization(self, parsed_data) -> Optional[Dict]:
        """Normalize memory utilization - LOWEST COMMON DENOMINATOR approach"""
        if not parsed_data or len(parsed_data) == 0:
            return None

        print(f" Normalizing memory data: {len(parsed_data)} entries")

        if self.platform.startswith('cisco'):
            # Cisco: Simple memory pools
            for entry in parsed_data:
                if entry.get('POOL') == 'Processor':
                    try:
                        total_bytes = int(entry['TOTAL'])
                        used_bytes = int(entry['USED'])
                        free_bytes = int(entry['FREE'])

                        used_percent = (used_bytes / total_bytes) * 100
                        total_mb = total_bytes // (1024 * 1024)
                        used_mb = used_bytes // (1024 * 1024)
                        free_mb = free_bytes // (1024 * 1024)

                        return {
                            'used_percent': used_percent,
                            'total_mb': total_mb,
                            'used_mb': used_mb,
                            'free_mb': free_mb
                        }
                    except (ValueError, KeyError) as e:
                        print(f" Error parsing Cisco memory: {e}")
                        continue

        elif self.platform.startswith('arista'):
            # Arista: Rich memory data - REDUCE to basic total/used/free
            entry = parsed_data[0]
            try:
                if 'GLOBAL_MEM_TOTAL' in entry:
                    # Get the unit
                    mem_unit = entry.get('GLOBAL_MEM_UNIT', 'KiB')

                    total_value = float(entry['GLOBAL_MEM_TOTAL'])
                    used_value = float(entry.get('GLOBAL_MEM_USED', 0))
                    free_value = float(entry.get('GLOBAL_MEM_FREE', 0))

                    # Convert to MB based on unit - NORMALIZE to MB
                    if mem_unit.lower() in ['kib', 'k']:
                        total_mb = int(total_value // 1024)
                        used_mb = int(used_value // 1024)
                        free_mb = int(free_value // 1024)
                    elif mem_unit.lower() in ['mib', 'm']:
                        total_mb = int(total_value)
                        used_mb = int(used_value)
                        free_mb = int(free_value)
                    elif mem_unit.lower() in ['gib', 'g']:
                        total_mb = int(total_value * 1024)
                        used_mb = int(used_value * 1024)
                        free_mb = int(free_value * 1024)
                    else:
                        # Default to KiB
                        total_mb = int(total_value // 1024)
                        used_mb = int(used_value // 1024)
                        free_mb = int(free_value // 1024)

                    if used_mb == 0 and free_mb > 0:
                        used_mb = total_mb - free_mb

                    used_percent = (used_mb / total_mb) * 100 if total_mb > 0 else 0

                    # IGNORE buffers, cached, swap details for compatibility
                    return {
                        'used_percent': used_percent,
                        'total_mb': total_mb,
                        'used_mb': used_mb,
                        'free_mb': free_mb
                    }
            except (ValueError, KeyError) as e:
                print(f" Error parsing Arista memory: {e}")

        elif self.platform.startswith('linux'):
            # Linux: Reduce to basic memory info
            entry = parsed_data[0]
            try:
                for total_field in ['MEM_TOTAL', 'TOTAL_MEMORY', 'TOTAL']:
                    if total_field in entry:
                        total_mb = int(entry[total_field])
                        used_mb = int(entry.get('MEM_USED', entry.get('USED_MEMORY', 0)))
                        free_mb = int(entry.get('MEM_FREE', entry.get('FREE_MEMORY', 0)))

                        if used_mb == 0 and free_mb > 0:
                            used_mb = total_mb - free_mb

                        used_percent = (used_mb / total_mb) * 100 if total_mb > 0 else 0

                        return {
                            'used_percent': used_percent,
                            'total_mb': total_mb,
                            'used_mb': used_mb,
                            'free_mb': free_mb
                        }
            except (ValueError, KeyError) as e:
                print(f" Error parsing Linux memory: {e}")

        print(f" No memory fields found for platform: {self.platform}")
        return None

    def _normalize_temperature(self, parsed_data) -> Optional[float]:
        """Normalize temperature data across platforms"""
        if not parsed_data or len(parsed_data) == 0:
            return None

        entry = parsed_data[0]

        # Common temperature field names
        for field in ['TEMPERATURE', 'TEMP', 'TEMP_CELSIUS', 'INLET_TEMP', 'CPU_TEMP']:
            if field in entry:
                try:
                    temp_str = str(entry[field])
                    # Extract numeric value (remove 'C', '°C', etc.)
                    import re
                    temp_match = re.search(r'(\d+\.?\d*)', temp_str)
                    if temp_match:
                        return float(temp_match.group(1))
                except (ValueError, TypeError):
                    continue

        return None

    def get_route_table_for_vrf(self, vrf_name: str):
        """Get route table for specific VRF"""
        if not self.is_connected:
            return

        success, output, parsed_data = self.execute_command_and_parse('route_table_vrf', vrf_name=vrf_name)
        if success:
            self.raw_route_output.emit(RawCommandOutput(
                command=self.get_platform_command('route_table_vrf', vrf_name=vrf_name),
                output=output,
                platform=self.platform,
                timestamp=time.time(),
                parsed_successfully=bool(parsed_data)
            ))

            if parsed_data:
                normalized_routes = self.field_normalizer.normalize_routes(parsed_data, self.platform)
                self.normalized_routes_ready.emit(normalized_routes)

    def disconnect_from_device(self):
        """Disconnect from current device"""
        if self.is_connected and self.device_info:
            self.data_collection_timer.stop()
            self.connection_manager.disconnect(self.device_info.ip_address, self.credentials.port)
            self.is_connected = False
            self.device_info.connection_status = "disconnected"
            self.connection_status_changed.emit(self.device_info.ip_address, "disconnected")
            self.device_info_updated.emit(self.device_info)

    def set_theme(self, theme_name: str):
        """Change the current theme and notify all widgets"""
        if self.current_theme == theme_name:
            return
        self.current_theme = theme_name
        self.theme_changed.emit(theme_name)

    def __del__(self):
        """Cleanup connections on destruction"""
        if hasattr(self, 'connection_manager'):
            self.connection_manager.disconnect_all()