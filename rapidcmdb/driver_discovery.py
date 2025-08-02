import json
import logging
import os
import socket
import traceback
from typing import Optional, Dict, List
from dataclasses import dataclass, field, asdict
from napalm import get_network_driver

from rapidcmdb.ssh_client_pysshpass import ssh_client
from rapidcmdb.tfsm_fire import TextFSMAutoEngine
from rapidcmdb.interface_normalizer import InterfaceNormalizer
from rapidcmdb.util import get_db_path

logger = logging.getLogger('netmiko')

@dataclass
class DeviceInfo:
    hostname: str
    ip: str
    username: str
    password: str
    timeout: int = 20
    optional_args: Dict = field(default_factory=dict)
    platform: Optional[str] = None

    def to_dict(self) -> Dict:
        return {k: v for k, v in asdict(self).items() if k != 'platform'}


class DriverDiscovery:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.supported_drivers = ['nxos_ssh', 'ios', 'eos', 'procurve']
        self.napalm_neighbor_capable = ['procurve']

        self._platform_cache = {}
        db_path = get_db_path()
        self.parser = TextFSMAutoEngine(db_path)
    def _check_port_open(self, host: str, port: int = 22, timeout: int = 5) -> bool:
        """Quick check if port is open on host."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except socket.error as e:
            self.logger.debug(f"Socket check failed for {host}:{port} - {str(e)}")
            return False

    def check_nxos_platform(self, device):
        """Check if device is running NX-OS using direct SSH."""
        try:
            # Set up commands - we need terminal length and show version
            # commands = "enable,term len 0,show version"

            output = ssh_client(
                host=device.hostname,
                user=device.username,
                password=device.password,
                cmds="show version",
                invoke_shell=False,
                prompt="#",  # Match either # or >
                prompt_count=5,  # Wait for 3 prompts (initial, after term len, after show ver)
                timeout=5,
                disable_auto_add_policy=False,
                look_for_keys=False,
                inter_command_time=1,  # Give commands time to complete
                connect_only=False
            )


            # Check output for NXOS indicators
            if 'Nexus' in output or 'NX-OS' in output:
                return True
            return False

        except Exception as e:
            self.logger.error(f"Error checking NX-OS platform for {device.hostname}: {str(e)}")
            return False

    def detect_platform(self, device: DeviceInfo, retry=False, config=None) -> Optional[str]:
        """Detect device platform with strict validation of returned facts."""
        if device.hostname in self._platform_cache:
            return self._platform_cache[device.hostname]

        if not self._check_port_open(device.hostname):
            self.logger.debug(f"SSH port not reachable on {device.hostname}")
            return None

        # Try procurve/arubaoss detection first
        try:
            driver = get_network_driver('procurve')
            device_dict = device.to_dict()
            device_dict.pop('ip', None)

            with driver(**device_dict) as device_conn:
                facts = device_conn.get_facts()
                if (facts and
                        ('Hewlett-Packard' in facts.get('vendor', '') or
                         'Aruba' in facts.get('model', ''))):
                    self._platform_cache[device.hostname] = 'procurve'
                    return 'procurve'
        except Exception as e:
            self.logger.debug(f"Procurve detection failed: {str(e)}")

        # Handle credential retry
        if retry and config:
            device.username = config.alternate_username
            device.password = config.alternate_password

        # Pre-check for NXOS using SSH client
        try:
            is_nxos = self.check_nxos_platform(device)
        except Exception as e:
            self.logger.error(f"Platform pre-check failed for {device.hostname}: {str(e)}")
            is_nxos = False

        # Optimize driver sequence based on pre-check
        driver_sequence = ['nxos_ssh', 'ios', 'eos'] if is_nxos else ['ios', 'eos', 'procurve', 'nxos_ssh']

        for driver_name in driver_sequence:
            try:
                driver = get_network_driver(driver_name)
                device_dict = device.to_dict()
                device_dict.pop('ip', None)  # Remove IP if present

                # Configure driver-specific options
                if driver_name == 'nxos_ssh':
                    device.optional_args = {
                        'transport': 'ssh',
                        'port': 22
                    }
                    driver.port = 22
                elif driver_name == 'eos':
                    device.optional_args = {
                        'transport': 'ssh',
                        'use_eapi': False
                    }
                # print(f"NAPALM connecting to: {device_dict}")
                # Attempt connection and fact gathering
                if driver_name == 'eos':
                    device_dict['optional_args'] ={
                        'transport': 'ssh',
                        'use_eapi': False
                    }
                with driver(**device_dict) as device_conn:
                    try:
                        facts = device_conn.get_facts()
                        if facts['hostname'] == 'Unknown' and facts['os_version'] == 'Unknown':
                            # this is not ios
                            continue
                        if facts and self._validate_device_facts(facts, driver_name):
                            self._platform_cache[device.hostname] = driver_name
                            self.logger.info(f"Successfully detected {driver_name} for {device.hostname}")
                            return driver_name
                        self.logger.debug(f"Facts validation failed for {driver_name} on {device.hostname}")
                    except Exception as e:
                        self.logger.debug(f"Failed to get facts with {driver_name}: {str(e)}")
                        continue

            except Exception as e:
                self.logger.debug(f"Failed to initialize {driver_name} driver: {str(e)}")
                traceback.print_exc()
                # if eos is older, you may have to hack napalms eos.py file and force older version support
                # if self._eos_version < EOSVersio
                continue

        self.logger.warning(f"No valid platform detected for {device.hostname}")
        return None

    def _normalize_napalm_neighbors(self, napalm_neighbors: Dict) -> Dict:
        """Normalize NAPALM LLDP neighbor data"""
        normalized = {}

        for interface, neighbors in napalm_neighbors.items():
            for neighbor in neighbors:
                device_id = neighbor.get('hostname', '').split('.')[0]

                # Skip empty hostnames or MAC-only entries
                if not device_id or ':' in device_id:
                    continue

                if not self._is_valid_device_id(device_id):
                    continue

                # For Aruba/Procurve, normalize port IDs
                remote_port = neighbor.get('port', '')
                if ':' in remote_port:  # It's a MAC address
                    remote_port = f"Port-{interface}"  # Use local port number as fallback

                if device_id not in normalized:
                    normalized[device_id] = {
                        'ip': neighbor.get('management_ip', ''),
                        'platform': self._detect_platform_from_desc(
                            neighbor.get('system_description', '')
                        ),
                        'connections': []
                    }

                connection = [str(interface), remote_port]
                if connection not in normalized[device_id]['connections']:
                    normalized[device_id]['connections'].append(connection)

        return normalized

    def _validate_device_facts(self, facts: dict, driver_name: str) -> bool:
        """
        Strictly validate device facts to ensure correct platform detection.
        Returns True only if we're confident about the platform match.
        """
        # Check for required fields
        required_fields = {'vendor', 'model', 'os_version', 'hostname'}
        if not all(field in facts for field in required_fields):
            return False

        # Check for "Unknown" values in critical fields
        critical_fields = {'vendor', 'model', 'os_version'}
        if any(facts.get(field) == 'Unknown' for field in critical_fields):
            return False

        # Specific platform validations
        if driver_name == 'nxos_ssh':
            return (
                    'Cisco' in facts['vendor'] and
                    ('Nexus' in facts['model'] or 'NX-OS' in facts['os_version'])
            )
        elif driver_name == 'ios':
            return (
                    'Cisco' in facts['vendor'] and
                    'Version' in facts['os_version'] and
                    'Nexus' not in facts['model'] and
                    'NX-OS' not in facts['os_version']
            )
        elif driver_name == 'eos':
            return (
                    'Arista' in facts['vendor'] or
                    'vEOS' in facts['model'] or
                    'EOS' in facts['os_version']
            )

        return False

    def _verify_platform(self, driver_name: str, facts: Dict) -> bool:
        if driver_name == 'eos':
            return (
                    "vEOS" in facts.get("model", "") or
                    "EOS" in facts.get("os_version", "") or
                    "Arista" in facts.get("vendor", "")
            )
        elif driver_name == 'ios':
            return "Cisco" in facts.get("vendor", "")
        elif driver_name == 'nxos':
            return all(key in facts.get("vendor", "") for key in ["Cisco", "NX-OS"])
        return False

    def get_device_capabilities(self, device: DeviceInfo, config=None) -> Dict:
        """Get device capabilities with Aruba/Procurve support"""
        if not device.platform:
            device.platform = self.detect_platform(device, config=config)
            if not device.platform:
                raise ValueError(f"Unable to detect platform for {device.hostname}")
        if device.platform == "unknown":
            device.platform = self.detect_platform(device, config=config)
            if not device.platform:
                raise ValueError(f"Unable to detect platform for {device.hostname}")

        if device.platform == 'eos':
            device.optional_args = {'transport': 'ssh', 'use_eapi': False}

        driver = get_network_driver(device.platform)
        device_dict = device.to_dict()
        device_dict.pop('ip', None)  # Remove ip key if it exists

        with driver(**device_dict) as device_conn:
            try:
                interfaces = device_conn.get_interfaces()
            except Exception as e:
                print(f"Napalm failure to get interfaces on: {device_conn.hostname}")
                print(e)
                interfaces = {}

            # Get standard Napalm data
            capabilities = {
                'facts': device_conn.get_facts(),
                'interfaces': interfaces,
                'driver_connection': device_conn,  # Pass the connection object
                'platform': device.platform
            }

            if device.platform == 'procurve':
                try:
                    # Initialize neighbors dict
                    neighbors = {'cdp': {}, 'lldp': {}}

                    # First get basic LLDP data from NAPALM
                    raw_lldp = device_conn.get_lldp_neighbors()
                    normalized_lldp = self._normalize_napalm_neighbors(raw_lldp)

                    # Get detailed LLDP info via CLI
                    command = 'show lldp info remote-device detail'
                    cli_output = device_conn.cli([command])
                    lldp_detail = cli_output[command]

                    best_template, parsed_detail, score = self.parser.find_best_template(
                        lldp_detail, 'hp_procurve_show_lldp_info_remote_detail'
                    )

                    if parsed_detail and score > 10:
                        for entry in parsed_detail:
                            # Get device ID, prioritizing NEIGHBOR_NAME
                            device_id = entry.get('NEIGHBOR_NAME', '').split('.')[0].lower()

                            # Skip if no valid device ID
                            if not device_id or ':' in device_id:
                                continue

                            if not self._is_valid_device_id(device_id):
                                continue

                            # Find this device in our normalized data
                            if device_id in normalized_lldp:
                                # Update IP address if available (skip link-local IPv6)
                                if entry.get('MGMT_ADDRESS') and not entry['MGMT_ADDRESS'].startswith('fe80:'):
                                    normalized_lldp[device_id]['ip'] = entry['MGMT_ADDRESS']

                                # Update platform information if available
                                if entry.get('NEIGHBOR_DESCRIPTION'):
                                    desc = entry['NEIGHBOR_DESCRIPTION']
                                    if 'Aruba' in desc or 'HP' in desc or 'ProCurve' in desc:
                                        normalized_lldp[device_id]['platform'] = 'procurve'
                                    elif 'Cisco' in desc:
                                        if 'NX-OS' in desc:
                                            normalized_lldp[device_id]['platform'] = 'nxos'
                                        else:
                                            normalized_lldp[device_id]['platform'] = 'ios'
                                    elif 'Arista' in desc:
                                        normalized_lldp[device_id]['platform'] = 'eos'

                                # Normalize port names
                                normalized_ports = []
                                for conn in normalized_lldp[device_id]['connections']:
                                    local_port = conn[0]
                                    remote_port = entry.get('NEIGHBOR_INTERFACE_DESCRIPTION') or entry.get(
                                        'NEIGHBOR_INTERFACE', '')
                                    if ':' in remote_port or " " in remote_port:  # If it's a MAC address
                                        remote_port = f"Port-{entry['LOCAL_INTERFACE']}"
                                    normalized_ports.append([local_port, remote_port])

                                normalized_lldp[device_id]['connections'] = normalized_ports

                    neighbors['lldp'] = normalized_lldp
                    capabilities['neighbors'] = neighbors

                except Exception as e:
                    self.logger.error(f"Error getting LLDP neighbors for {device.hostname}: {str(e)}")
                    capabilities['neighbors'] = {'lldp': {}, 'cdp': {}}
            else:
                try:
                # Use enhanced neighbor discovery for other platforms
                    capabilities['neighbors'] = self._get_enhanced_neighbors(device_conn, device.platform)
                except Exception as e:
                    print(f"enhanced cdp extract failed")
            # print(json.dumps(capabilities['neighbors'], indent=2))
            return capabilities

    def _get_neighbors(self, device_conn, platform: str) -> Dict:
        neighbors = {'cdp': {}, 'lldp': {}}

        if platform != 'eos':
            cdp_output = device_conn._netmiko_device.send_command('show cdp neighbors detail')
            # self.logger.info(f"CDP raw output:\n{cdp_output}")
            best_cdp_template, parsed_cdp, score = self.parser.find_best_template(cdp_output, 'show_cdp_neighbors_detail')
            print(f"[{device_conn.hostname}] Best CDP Template Selected: {best_cdp_template}")
            if parsed_cdp and score > 0:  # Only use results with decent score
                neighbors['cdp'] = self._normalize_cdp_output(parsed_cdp, platform)

        lldp_output = device_conn._netmiko_device.send_command('show lldp neighbors detail')
        # self.logger.info(f"LLDP raw output:\n{lldp_output}")

        best_lldp_template, parsed_lldp, score = self.parser.find_best_template(lldp_output, 'show_lldp_neighbors_detail')
        print(f"[{device_conn.hostname}] Best LLDP Template Selected: {best_lldp_template} Score: {score}")
        print(parsed_lldp)
        if parsed_lldp and score > 0:  # Only use results with decent score
            neighbors['lldp'] = self._normalize_lldp_output(parsed_lldp, platform)

        return neighbors

    def _normalize_cdp_output(self, parsed_data: List[Dict], local_platform: str) -> Dict:
        neighbors = {}
        for entry in parsed_data:
            device_id = entry['NEIGHBOR_NAME'].split('.')[0]
            if not self._is_valid_device_id(device_id):
                continue

            local_int, remote_int = InterfaceNormalizer.normalize_pair(
                entry['LOCAL_INTERFACE'],
                entry['NEIGHBOR_INTERFACE'],
                local_platform,
                'ios'  # Platform is always Cisco since this is CDP
            )

            self._add_unique_connection(neighbors, device_id, {
                'ip': entry['MGMT_ADDRESS'],
                'platform': 'ios' if 'cisco' in entry['PLATFORM'].lower() else 'unknown',
                'local_port': local_int,
                'remote_port': remote_int
            })
        return neighbors

    def _map_neighbor_fields(self, entry: Dict, protocol: str) -> Dict:
        """Map TextFSM fields to our schema format.

        Our schema format:
        {
            'ip': str,              # Management IP address
            'platform': str,        # Platform identifier
            'connections': [        # List of interface pairs
                [local_port, remote_port],
            ]
        }
        """
        mapped = {
            'ip': '',
            'platform': 'unknown',
            'connections': []
        }

        # Get IP address
        if 'MGMT_ADDRESS' in entry:
            mapped['ip'] = entry['MGMT_ADDRESS']

        # Get platform info
        if protocol == 'cdp':
            # CDP specific mapping
            if 'PLATFORM' in entry:
                mapped['platform'] = self._detect_platform_from_desc(entry['PLATFORM'])
            elif 'NEIGHBOR_DESCRIPTION' in entry:
                mapped['platform'] = self._detect_platform_from_desc(entry['NEIGHBOR_DESCRIPTION'])

            # Get interface pairs
            if 'LOCAL_INTERFACE' in entry and 'NEIGHBOR_INTERFACE' in entry:
                local_port = entry['LOCAL_INTERFACE']
                remote_port = entry['NEIGHBOR_INTERFACE']
                if local_port and remote_port:
                    mapped['connections'].append([local_port, remote_port])

        else:  # LLDP
            # LLDP specific mapping
            if 'NEIGHBOR_DESCRIPTION' in entry:
                mapped['platform'] = self._detect_platform_from_desc(entry['NEIGHBOR_DESCRIPTION'])
            elif 'PLATFORM' in entry:
                mapped['platform'] = self._detect_platform_from_desc(entry['PLATFORM'])

            # Get interface pairs - LLDP can have different field names
            local_port = entry.get('LOCAL_INTERFACE', '')
            remote_port = entry.get('NEIGHBOR_INTERFACE', '') or entry.get('NEIGHBOR_PORT_ID', '')
            if local_port and remote_port:
                mapped['connections'].append([local_port, remote_port])

        return mapped

    def _get_enhanced_neighbors(self, device_conn, platform: str) -> Dict:
        """Get enhanced neighbor information using direct SSH and TextFSM parsing."""
        neighbors = {'cdp': {}, 'lldp': {}}
        db_path = get_db_path()
        parser = TextFSMAutoEngine(db_path)
        # parser = TextFSMAutoEngine('tfsm_templates.db')
        parsed_cdp = []
        parsed_lldp = []
        device_id = None

        try:
            # Get device hostname for logging
            hostname = device_conn.hostname if hasattr(device_conn, 'hostname') else 'unknown'

            # CDP Processing
            if platform != 'eos':
                try:
                    cdp_output = ssh_client(
                        host=hostname,
                        user=device_conn._netmiko_device.username,
                        password=device_conn._netmiko_device.password,
                        cmds="show cdp neighbor detail",
                        invoke_shell=False,
                        prompt="#",
                        prompt_count=1,
                        timeout=5,
                        disable_auto_add_policy=False,
                        look_for_keys=False,
                        inter_command_time=.5
                    )

                    self.logger.debug(f"Raw CDP Output:\n{cdp_output}")

                    best_template, parsed_cdp, score = parser.find_best_template(cdp_output,
                                                                                 'show_cdp_neighbor')
                    self.logger.info(f"CDP Template: {best_template}, Score: {score}")
                    self.logger.debug(f"Parsed CDP Data:\n{json.dumps(parsed_cdp, indent=2)}")

                    if parsed_cdp and score > 10:
                        for entry in parsed_cdp:
                            device_id = entry['NEIGHBOR_NAME'].split('.')[0]

                            if not self._is_valid_device_id(device_id):
                                self.logger.debug(f"Skipping invalid CDP device ID: {device_id}")
                                continue

                            mapped_data = self._map_neighbor_fields(entry, 'cdp')
                            self.logger.debug(f"Mapped CDP data for {device_id}: {json.dumps(mapped_data, indent=2)}")
                            neighbors['cdp'][device_id] = mapped_data

                except Exception as e:
                    self.logger.error(f"Error getting CDP neighbors: {str(e)}")
                    self.logger.debug("CDP Exception details:", exc_info=True)

            # LLDP Processing
            try:
                lldp_output = ssh_client(
                    host=hostname,
                    user=device_conn._netmiko_device.username,
                    password=device_conn._netmiko_device.password,
                    cmds="show lldp neighbor detail",
                    invoke_shell=False,
                    prompt="#",
                    prompt_count=3,
                    timeout=3,
                    disable_auto_add_policy=False,
                    look_for_keys=False,
                    inter_command_time=.5
                )

                self.logger.debug(f"Raw LLDP Output:\n{lldp_output}")
                show_command = "show_lldp_neighbor"
                if platform == 'eos':
                    show_command = 'arista_eos_show_lldp_neighbors_detail'
                if platform == 'ios':
                    show_command = 'cisco_ios_show_lldp_neighbors_detail'
                if platform == 'nxos_ssh':
                    show_command = 'cisco_nxos_show_lldp_neighbors_detail'

                best_template, parsed_lldp, score = parser.find_best_template(lldp_output, show_command)
                self.logger.info(f"LLDP Template: {best_template}, Score: {score}")
                self.logger.debug(f"Parsed LLDP Data:\n{json.dumps(parsed_lldp, indent=2)}")

                if parsed_lldp and score > 0:
                    for entry in parsed_lldp:
                        temp_device_id = entry.get('NEIGHBOR_NAME', '').split('.')[0]
                        if not temp_device_id:
                            temp_device_id = entry.get('CHASSIS_ID', '').replace(':', '').lower()

                        if not self._is_valid_device_id(temp_device_id):
                            self.logger.debug(f"Skipping invalid LLDP device ID: {temp_device_id}")
                            continue

                        device_id = temp_device_id
                        mapped_data = self._map_neighbor_fields(entry, 'lldp')
                        self.logger.debug(f"Mapped LLDP data for {device_id}: {json.dumps(mapped_data, indent=2)}")
                        neighbors['lldp'][device_id] = mapped_data

            except Exception as e:
                self.logger.error(f"Error getting LLDP neighbors: {str(e)}")
                self.logger.debug("LLDP Exception details:", exc_info=True)

            # Save the data to files
            output_dir = os.path.join('.', 'output')
            os.makedirs(output_dir, exist_ok=True)

            host = device_id if device_id else hostname

            # Save CDP data
            try:
                with open(os.path.join(output_dir, f"{host}_cdp.json"), "w") as fhc:
                    fhc.write(json.dumps(parsed_cdp, indent=2))
            except Exception as e:
                self.logger.error(f"Unable to save CDP neighbor data for {host}: {str(e)}")

            # Save LLDP data
            try:
                with open(os.path.join(output_dir, f"{host}_lldp.json"), "w") as fhl:
                    fhl.write(json.dumps(parsed_lldp, indent=2))
            except Exception as e:
                self.logger.error(f"Unable to save LLDP neighbor data for {host}: {str(e)}")

            # Save combined neighbors data
            try:
                with open(os.path.join(output_dir, f"{host}_neighbors.json"), "w") as fhn:
                    fhn.write(json.dumps(neighbors, indent=2))
            except Exception as e:
                self.logger.error(f"Unable to save topology data for {host}: {str(e)}")

            return neighbors

        except Exception as e:
            self.logger.error(f"Error in _get_enhanced_neighbors: {str(e)}")
            return neighbors

    def _normalize_lldp_output(self, parsed_data: List[Dict], local_platform: str) -> Dict:
        neighbors = {}
        for entry in parsed_data:
            system_name = entry.get('NEIGHBOR_NAME', '').split('.')[0]

            if not self._is_valid_device_id(system_name):
                continue

            platform = 'unknown'
            if desc := entry.get('NEIGHBOR_DESCRIPTION', ''):
                if 'arista' in desc.lower():
                    platform = 'eos'
                elif 'cisco' in desc.lower():
                    platform = 'ios'

            local_int, remote_int = InterfaceNormalizer.normalize_pair(
                entry['LOCAL_INTERFACE'],
                entry['NEIGHBOR_INTERFACE'] or entry['NEIGHBOR_PORT_ID'],
                local_platform,
                platform
            )

            self._add_unique_connection(neighbors, system_name, {
                'ip': entry.get('MGMT_ADDRESS', 'unknown'),
                'platform': platform,
                'local_port': local_int,
                'remote_port': remote_int
            })
        return neighbors
    def _is_valid_device_id(self, device_id: str) -> bool:
        """Check if device ID is valid."""
        return (len(device_id) > 1 and  # Skip single characters
                not device_id.startswith(('Entry', 'Device', 'System')) and  # Skip headers
                not all(c in '.-_/:,' for c in device_id))  # Skip punctuation-only

    def _add_unique_connection(self, neighbors: Dict, device_id: str, connection: Dict) -> None:
        """Add connection only if unique."""
        if device_id not in neighbors:
            neighbors[device_id] = {'ip': connection['ip'],
                                    'platform': connection['platform'],
                                    'connections': [[connection['local_port'],
                                                     connection['remote_port']]]}
            return

        existing = neighbors[device_id]
        new_connection = [connection['local_port'], connection['remote_port']]

        # Add connection if ports are unique
        if 'connections' not in existing:
            existing['connections'] = []
        if new_connection not in existing['connections']:
            existing['connections'].append(new_connection)

    # Only add if ports are different

    def _detect_platform_from_desc(self, description: str) -> str:
        """Detect platform from device description string."""
        description = description.lower()
        if any(term in description for term in ['arista', 'eos']):
            return 'eos'
        elif any(term in description for term in ['juniper', 'junos']):
            return 'junos'
        elif any(term in description for term in ['cisco', 'ios']):
            return 'ios'
        elif 'nx-os' in description:
            return 'nxos'
        return 'ios'  # default to ios if unknown

    def validate_credentials(self, device: DeviceInfo) -> bool:
        try:
            if platform := self.detect_platform(device):
                device.platform = platform
                self.get_device_capabilities(device)
                return True
        except Exception:
            pass
        return False
