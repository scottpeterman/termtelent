import math
import re
from pathlib import Path

import socket
import traceback
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Set, List
from queue import Queue
import logging
from pathlib import Path
import json
import signal
from functools import wraps
import errno

import networkx as nx
import numpy as np
from PyQt6.QtWidgets import QMessageBox
from func_timeout import func_timeout, FunctionTimedOut
from matplotlib import pyplot as plt

from rapidcmdb.enh_int_normalizer import InterfaceNormalizer
from rapidcmdb.diagrams import create_network_diagrams
from rapidcmdb.driver_discovery import DriverDiscovery, DeviceInfo

import threading

# from rapidcmdb.util import get_db_path

from rapidcmdb.logger_manager import logger_manager
from rapidcmdb.tfsm_fire import TextFSMAutoEngine


def timeout_handler():
    raise TimeoutError("Operation timed out")

def run_with_timeout(func, timeout, *args, **kwargs):
    """Timeout wrapper using func-timeout"""
    try:
        return func_timeout(timeout, func, args=args, kwargs=kwargs)
    except FunctionTimedOut:
        raise TimeoutError(f"Operation timed out after {timeout} seconds")

@dataclass
class DiscoveryConfig:
    seed_ip: str
    username: str
    password: str
    alternate_username: str
    alternate_password: str
    domain_name: str = ""
    exclude_string: str = ""
    output_dir: Path = Path("./output")
    timeout: int = 30
    max_devices: int = 100
    save_debug_info: bool = False
    map_name: str = ""
    layout_algo: str = "kk"


    def to_dict(self) -> Dict:
        data = asdict(self)
        data['output_dir'] = str(data['output_dir'])
        return data

@dataclass
class DeviceConnection:
    local_port: str
    remote_port: str
    protocol: str
    neighbor_ip: Optional[str] = None
    neighbor_platform: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

@dataclass
class NetworkDevice:
    hostname: str
    ip: str
    platform: str
    serial: str
    connections: Dict[str, List[DeviceConnection]] = field(default_factory=dict)

    def get_neighbor_info(self, ip: str) -> Optional[Dict]:
        for neighbor_id, connections in self.connections.items():
            for conn in connections:
                if conn.neighbor_ip == ip:
                    return {
                        'neighbor_id': neighbor_id,
                        'platform': conn.neighbor_platform,
                        'protocol': conn.protocol
                    }
        return None

    def __iter__(self):
        data = self.to_dict()
        for key, value in data.items():
            yield key, value
    def to_dict(self) -> Dict:
        data = asdict(self)
        if 'connections' not in data:
            data['connections'] ={}

        data['connections'] = {
            key: [conn.to_dict() for conn in value]
            for key, value in self.connections.items()
        }
        return data

def timeout(seconds=60):
    def decorator(func):
        def _handle_timeout(signum, frame):
            print(f"Global Timeout Hit...")
            raise TimeoutError(f"Function call timed out after {seconds} seconds")

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Set the timeout handler
            signal.signal(signal.SIGALRM, _handle_timeout)
            signal.alarm(seconds)
            try:
                result = func(*args, **kwargs)
            finally:
                # Disable the alarm
                signal.alarm(0)
            return result
        return wrapper
    return decorator

class NetworkDiscovery:

    def __init__(self, config: DiscoveryConfig):
        self.processed_hostnames = set()
        self.config = config
        self.progress_callback = None
        self.log_callback = None
        self.stats = {
            'devices_discovered': 0,
            'devices_failed': 0,
            'devices_queued': 0
        }
        self.driver_discovery = DriverDiscovery()
        self.queue: Queue = Queue()
        self.visited: Set[str] = set()
        self.visited_ips: Set[str] = set()  # Track visited IPs
        self.visited_hostnames: Set[str] = set()  # Track visited hostnames

        self.failed_devices: Set[str] = set()
        self.unreachable_hosts: Set[str] = set()
        self.network_map: Dict[str, NetworkDevice] = {}

        # Logger setup with the manager
        try:
            self.logger = logger_manager.get_logger(callback=self._handle_log)
        except Exception as e:
            traceback.print_exc()
        # Additional initialization
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_devices = config.max_devices
        self.layout_algo = config.layout_algo

    def set_log_callback(self, callback):
        """Set callback for log messages"""
        self.log_callback = callback

    def _handle_log(self, message):
        """Handle log messages from logger"""
        if self.log_callback:
            self.log_callback(message)
    def _check_port_open(self, host: str, port: int = 22, timeout: int = 5) -> bool:
        """Quick check if port is open on host."""
        if host in self.unreachable_hosts:  # Skip if already known unreachable
            return False

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()

            if result != 0:
                self.unreachable_hosts.add(host)  # Add to unreachable set
                self.logger.warning(f"SSH port not reachable on {host}")
                return False
            return True

        except socket.error as e:
            self.unreachable_hosts.add(host)  # Add to unreachable set
            self.logger.warning(f"Socket check failed for {host}:{port} - {str(e)}")
            return False

    def _map_neighbor_fields(self, entry: Dict) -> Dict:
        """Map TextFSM parsed fields to intermediate schema for NetworkDevice creation."""
        mapped_data = {
            'ip': '',
            'platform': 'ios',  # Default platform
            'connections': []
        }

        # For IP address, try MGMT_ADDRESS first, then INTERFACE_IP
        if entry.get('MGMT_ADDRESS'):
            mapped_data['ip'] = entry['MGMT_ADDRESS']
        elif entry.get('INTERFACE_IP'):
            mapped_data['ip'] = entry['INTERFACE_IP']

        # Map platform from PLATFORM field - keep original ios/eos mapping
        if 'PLATFORM' in entry:
            platform_str = entry['PLATFORM'].lower()
            if 'eos' in platform_str:
                mapped_data['platform'] = 'eos'
            else:
                mapped_data['platform'] = 'ios'

        # Keep original interface names - normalization happens in transform_map
        if 'LOCAL_INTERFACE' in entry and 'NEIGHBOR_INTERFACE' in entry:
            local_int = entry['LOCAL_INTERFACE']
            neighbor_int = entry['NEIGHBOR_INTERFACE']
            if local_int and neighbor_int:
                mapped_data['connections'].append([local_int, neighbor_int])

        return mapped_data

    def _is_visited(self, device: DeviceInfo) -> bool:
        """Check if device already connected to, queued, failed, or successfully processed"""
        visited = device.ip in self.visited
        queued = any(device.ip == item.ip for item in list(self.queue.queue))
        failed = device.ip in self.failed_devices
        processed = device.hostname in self.processed_hostnames

        if visited or queued or failed or processed:
            self.logger.debug(
                f"Device {device.ip} visited: {visited}, queued: {queued}, failed: {failed}, processed: {processed}")
        return visited or queued or failed or processed
    def _mark_visited(self, device: DeviceInfo) -> None:
        """Mark that we've connected to this device"""
        self.visited.add(device.ip)
        self.logger.debug(f"Marked {device.ip} as visited. Total visited: {len(self.visited)}")

    def crawl(self):
        """Run network discovery process."""
        # Initialize with seed device
        seed_device = DeviceInfo(
            hostname=self.config.seed_ip,
            ip=self.config.seed_ip,
            username=self.config.username,
            password=self.config.password,
            timeout=self.config.timeout
        )
        self.logger.info(
            f"Queueing seed device: {self.config.seed_ip} - in visited_ips: {self.config.seed_ip in self.visited_ips}, "
            f"in unreachable: {self.config.seed_ip in self.unreachable_hosts}, "
            f"in network_map: {self.config.seed_ip in [d.ip for d in self.network_map.values()]}"
        )

        self.queue.put(seed_device)
        processing_seed_device = True

        while not self.queue.empty() and self.stats['devices_discovered'] < self.max_devices - 1:

            current_device = self.queue.get()
            try:
                self.logger.info(
                    f"Dequeued device {current_device.hostname} (IP: {current_device.ip}). Queue size: {self.queue.qsize()}")
                if self._is_visited(current_device):
                    self.logger.info(
                        f"skipping previously visited device {current_device.hostname} (IP: {current_device.ip}). Queue size: {self.queue.qsize()}")
                    continue
                try:
                    # Update stats for queue before processing
                    self.stats = {
                        'devices_discovered': len(self.network_map),
                        'devices_failed': len(self.failed_devices),
                        'devices_queued': self.queue.qsize(),
                        'devices_visited': len(self.visited_ips),
                        'unreachable_hosts': len(self.unreachable_hosts)
                    }
                    self.logger.info(f"Starting processing of {current_device.hostname} (IP: {current_device.ip})")
                    self.logger.debug(f"Current visited IPs: {self.visited_ips}")
                    self.logger.debug(f"Current network_map devices: {list(self.network_map.keys())}")

                    if self._is_visited(current_device):
                        self.logger.debug(f"Already processed device: {current_device.hostname} ({current_device.ip})")
                        continue

                    self.emit_device_discovered(current_device.hostname, "processing")

                    # device.hostname check here
                    exclude_patterns = self.config.exclude_string.split(',') if self.config.exclude_string else []
                    if exclude_patterns and any(
                            pattern.lower() in current_device.hostname.lower() for pattern in exclude_patterns):
                        self.logger.info(f"Skipping excluded device: {current_device.hostname}")
                        continue
                    # Check if device is reachable
                    if not self._check_port_open(current_device.hostname):
                        self.logger.warning(f"Device unreachable: {current_device.hostname} (IP: {current_device.ip})")
                        self.failed_devices.add(current_device.hostname)
                        self.emit_device_discovered(current_device.hostname, "failed")
                        continue

                    # Discover device capabilities and neighbors
                    try:
                        if processing_seed_device:
                            # self.logger.setLevel(logging.INFO)
                            self.logger.info("Discovering seed device...")
                            # self.logger.setLevel(logging.WARNING)
                            processing_seed_device = False

                        exclude_patterns = self.config.exclude_string.split(',') if self.config.exclude_string else []
                        if exclude_patterns and any(
                                pattern.lower() in current_device.hostname.lower() for pattern in exclude_patterns):
                            self.logger.info(f"Skipping excluded device: {current_device.hostname}")
                            continue

                        try:
                            capabilities = run_with_timeout(
                                self.driver_discovery.get_device_capabilities,
                                60,  # 30 second timeout
                                current_device,
                                config=self.config
                            )
                            # capabilities = run_with_timeout(device_discovery_logic, 60)  # 30 second timeout
                        except TimeoutError as e:
                            self.logger.error(f"Timeout discovering capabilities for {current_device.hostname}: {str(e)}")
                            continue
                        except Exception as e:
                            self.logger.error(f"Error discovering capabilities for {current_device.hostname}: {str(e)}")
                            continue

                        if capabilities:
                            # Process neighbors and connections
                            device = self._process_device(current_device, capabilities)
                            if device:
                                neighbors = capabilities.get('neighbors', {})

                                if capabilities['platform'] == "ios":
                                    self.get_ios_cdp(current_device, capabilities)
                                self.logger.info(f"Processing {len(neighbors)} neighbors for {device.hostname}")
                                self._process_neighbors(device, neighbors)
                                self.network_map[device.hostname] = device
                                self.processed_hostnames.add(device.hostname)
                                self.emit_device_discovered(current_device.hostname, "success")

                    except Exception as e:
                        self.logger.error(f"Failed to process device {current_device.hostname}: {str(e)}")
                        self.failed_devices.add(current_device.hostname)
                        self.emit_device_discovered(current_device.hostname, "failed")
                        traceback.print_exc()

                    self._mark_visited(current_device)

                except Exception as e:
                    self.logger.error(f"Error in discovery loop for device {current_device.hostname}: {str(e)}")
                    traceback.print_exc()


            except Exception as e:
                self.logger.error(f"Error in crawl loop for device {current_device.hostname}: {str(e)}")
                traceback.print_exc()
        try:
            self.stats = {
                'devices_discovered': len(self.network_map),
                'devices_failed': len(self.failed_devices),
                'devices_queued': self.queue.qsize(),
                'devices_visited': len(self.visited_ips),
                'unreachable_hosts': len(self.unreachable_hosts)
            }
            self.emit_device_discovered(None, "complete")

            # Save transformed and enriched map
            transformed_map = self.transform_map(self.network_map)
            enriched_map = self.enrich_peer_data(transformed_map)
            self._save_map_files(enriched_map)

            return enriched_map
        except Exception as e:
            traceback.print_exc()
            with open("error_dump_network_map.json", "w") as fhe:
                fhe.write(json.dumps(self.network_map, indent=2))
            self.logger.error("Failure generating map")
    def get_ios_cdp(self, device, capabilities):
        """
        Get CDP neighbors for IOS devices using TextFSM for accuracy while preserving capabilities schema.
        This is here because napalm was not parsing correctly and only returned partial neighbor info
        Args:
            device: The network device info object
            capabilities: Device capabilities dictionary containing the driver connection
        """
        try:
            from netmiko import ConnectHandler

            # Create Netmiko connection using device info
            net_connect = ConnectHandler(
                device_type="cisco_ios",
                host=device.ip,
                username=device.username,
                password=device.password,
                timeout=device.timeout,
                **device.optional_args
            )

            # Get raw CDP output
            net_connect.send_command("term len 0")  # Disable pagination
            cdp_output = net_connect.send_command("show cdp neighbors detail")
            net_connect.disconnect()

            # Use TextFSMAutoEngine to parse CDP data
            engine = TextFSMAutoEngine("secure_cartography/tfsm_templates.db")
            template_name, parsed_data, score = engine.find_best_template(cdp_output, "cdp_neighbors_detail")

            if parsed_data and score > 0:
                # Convert parsed data into capabilities CDP schema
                cdp_neighbors = {}

                for entry in parsed_data:
                    hostname = entry['NEIGHBOR_NAME'].split('.')[0]  # Remove domain if present

                    # Initialize neighbor entry if we haven't seen it before
                    if hostname not in cdp_neighbors:
                        cdp_neighbors[hostname] = {
                            'ip': entry['MGMT_ADDRESS'],
                            'platform': 'ios' if 'cisco' in entry['PLATFORM'].lower() else 'unknown',
                            'connections': []
                        }

                    # Add connection pair to the list
                    connection = [entry['LOCAL_INTERFACE'], entry['NEIGHBOR_INTERFACE']]
                    if connection not in cdp_neighbors[hostname]['connections']:
                        cdp_neighbors[hostname]['connections'].append(connection)

                # Update capabilities maintaining its schema
                if 'neighbors' not in capabilities:
                    capabilities['neighbors'] = {}
                capabilities['neighbors']['cdp'] = cdp_neighbors
                self.logger.info(f"Successfully parsed {len(cdp_neighbors)} CDP neighbors using TextFSM")

            else:
                self.logger.warning("No suitable template found or parsing failed for CDP output")

        except Exception as e:
            self.logger.error(f"Error getting CDP neighbors for device: {e}")
            return None
        finally:
            if 'net_connect' in locals() and net_connect.is_alive():
                net_connect.disconnect()

        return capabilities
    def _normalize_hostname(self, hostname: str) -> str:
        """Normalize hostname by removing domain and whitespace."""
        if not hostname:
            return hostname
        return hostname.split('.')[0].strip()

    def _check_known_device(self, hostname: str, ip: str) -> bool:
        """Check if a device is known by either hostname or IP."""
        if not ip:
            self.logger.warning(f"Empty IP provided for hostname {hostname}")
            return True  # Treat empty IPs as known

        normalized_hostname = self._normalize_hostname(hostname)
        existing_ips = [d.ip for d in self.network_map.values()]

        is_known = (
                ip in self.visited_ips or
                normalized_hostname in self.visited_hostnames or
                ip in self.unreachable_hosts or
                ip in existing_ips or
                normalized_hostname in [self._normalize_hostname(d.hostname) for d in self.network_map.values()] or
                any(ip == item.ip for item in list(self.queue.queue))
        )

        if is_known:
            self.logger.debug(
                f"Device {hostname} ({ip}) known via:\n"
                f"  - visited_ips: {ip in self.visited_ips}\n"
                f"  - visited_hostnames: {normalized_hostname in self.visited_hostnames}\n"
                f"  - unreachable_hosts: {ip in self.unreachable_hosts}\n"
                f"  - network_map_ips: {ip in existing_ips}\n"
                f"  - network_map_hostnames: {normalized_hostname in [self._normalize_hostname(d.hostname) for d in self.network_map.values()]}\n"
                f"  - queue: {any(ip == item.ip for item in list(self.queue.queue))}"
            )
        return is_known

    def _process_neighbors(self, device: NetworkDevice, neighbors: Dict) -> None:
        """Process neighbors for both CDP and LLDP with correct peer mapping."""
        self.logger.info(f"Starting neighbor processing for device {device.hostname}")
        self.logger.debug(f"Raw neighbor data: {neighbors}")

        for protocol in ['cdp', 'lldp']:
            protocol_neighbors = neighbors.get(protocol, {})
            self.logger.info(f"Processing {len(protocol_neighbors)} {protocol.upper()} neighbors for {device.hostname}")

            for neighbor_id, data in protocol_neighbors.items():
                self.logger.debug(f"{protocol.upper()}: Processing neighbor {neighbor_id}")

                # Normalize the neighbor hostname early
                normalized_neighbor_id = self._normalize_hostname(neighbor_id)

                # Get neighbor IP and validate
                neighbor_ip = data.get('ip', '')
                if not neighbor_ip:
                    self.logger.warning(f"No IP found for neighbor {neighbor_id}. Connection data: {data}")
                    # Still process the connection but without IP-based queuing

                self.logger.info(f"{protocol.upper()}: Processing neighbor {normalized_neighbor_id} ({neighbor_ip})")

                # Check exclusion patterns using the normalized neighbor ID
                exclude_patterns = self.config.exclude_string.split(',') if self.config.exclude_string else []
                if exclude_patterns and any(
                        pattern.lower() in normalized_neighbor_id.lower() for pattern in exclude_patterns):
                    self.logger.info(f"Skipping excluded device: {normalized_neighbor_id}")
                    continue

                # Process each connection for this neighbor
                for connection in data.get('connections', []):
                    self.logger.debug(
                        f"{protocol.upper()}: Processing connection {connection} for {normalized_neighbor_id}")

                    # Normalize interface names immediately
                    local_port = InterfaceNormalizer.normalize(connection[0]) if len(connection) > 0 else 'unknown'
                    remote_port = InterfaceNormalizer.normalize(connection[1]) if len(connection) > 1 else 'unknown'

                    # Add connection info using normalized neighbor ID as the key
                    connection_data = {
                        'local_port': local_port,
                        'remote_port': remote_port,
                        'ip': neighbor_ip,
                        'platform': data.get('platform', 'unknown')
                    }

                    # Always add the connection using the normalized neighbor hostname as the key
                    self.logger.debug(f"Adding connection for {normalized_neighbor_id}: {local_port} -> {remote_port}")
                    self._add_neighbor(device, normalized_neighbor_id, connection_data, protocol)

                    # Queue the device for discovery if it has an IP and hasn't been processed
                    if neighbor_ip and not self._is_known_device(neighbor_ip):
                        neighbor_device = DeviceInfo(
                            hostname=neighbor_ip,  # Use IP for initial connection
                            ip=neighbor_ip,
                            username=self.config.username,
                            password=self.config.password,
                            timeout=self.config.timeout,
                            platform=data.get('platform', '')
                        )

                        self.logger.info(
                            f"Queueing new device: {neighbor_ip} (will be known as {normalized_neighbor_id})")
                        self.queue.put(neighbor_device)
                    else:
                        if neighbor_ip:
                            self.logger.debug(
                                f"Device {neighbor_ip} ({normalized_neighbor_id}) already known, skipping queue")
                        else:
                            self.logger.debug(f"No IP for {normalized_neighbor_id}, cannot queue for discovery")

        self.logger.info(f"Completed neighbor processing for {device.hostname}")
        self.logger.info(f"Current queue size: {self.queue.qsize()}")

    def _is_known_device(self, ip: str) -> bool:
        """Check if a device IP is already known, queued, or unreachable."""
        if not ip:
            self.logger.warning("Empty IP provided to _is_known_device")
            return True  # Treat empty IPs as known to prevent queuing

        known = (
                ip in self.visited_ips or
                ip in self.unreachable_hosts or
                ip in [d.ip for d in self.network_map.values()] or
                any(ip == item.ip for item in list(self.queue.queue))
        )

        self.logger.debug(
            f"Known device check for {ip}:\n"
            f"  - In visited_ips: {ip in self.visited_ips}\n"
            f"  - In unreachable_hosts: {ip in self.unreachable_hosts}\n"
            f"  - In network_map: {ip in [d.ip for d in self.network_map.values()]}\n"
            f"  - In queue: {any(ip == item.ip for item in list(self.queue.queue))}\n"
            f"Final result: {known}"
        )
        return known

    def _enhance_lldp_data(self, parsed_lldp, platform='ios'):
        """Convert parsed LLDP data to the required neighbor format."""
        enhanced_lldp = {}

        # Define field mappings for different platforms
        field_mappings = {
            'ios': {
                'device_id': 'NEIGHBOR_NAME',
                'mgmt_ip': 'MGMT_ADDRESS',
                'local_interface': 'LOCAL_INTERFACE',
                'remote_interface': 'NEIGHBOR_PORT_ID'
            },
            'eos': {
                'device_id': 'NEIGHBOR_NAME',
                'mgmt_ip': 'MGMT_ADDRESS',
                'local_interface': 'LOCAL_INTERFACE',
                'remote_interface': 'NEIGHBOR_INTERFACE'
            },
            'nxos_ssh': {
                'device_id': 'NEIGHBOR_NAME',
                'mgmt_ip': 'MGMT_ADDRESS',
                'local_interface': 'LOCAL_INTERFACE',
                'remote_interface': 'NEIGHBOR_PORT_ID'
            }
        }

        # Get the appropriate field mapping with fallback to IOS
        fields = field_mappings.get(platform, field_mappings['ios'])

        for entry in parsed_lldp:
            # Get and normalize device ID
            device_id = entry.get(fields['device_id'], '')
            if not device_id:
                device_id = entry.get('CHASSIS_ID', '').replace(':', '').lower()

            # if not device_id or not self._is_valid_device_id(device_id):
            #     self.logger.debug(f"LLDP: Skipping invalid device ID: {device_id}")
            #     continue

            # Normalize the device ID
            normalized_device_id = self._normalize_hostname(device_id)

            # Get management IP with fallback
            ip_address = entry.get(fields['mgmt_ip'], '')
            if not ip_address:
                ip_address = entry.get('INTERFACE_IP', '')

            self.logger.info(f"LLDP: Processing neighbor {normalized_device_id} with IP {ip_address}")

            # Initialize device entry if needed
            if normalized_device_id not in enhanced_lldp:
                enhanced_lldp[normalized_device_id] = {
                    'ip': ip_address,
                    'platform': self._determine_platform_from_capabilities(
                        entry.get('CAPABILITIES', entry.get('NEIGHBOR_DESCRIPTION', ''))
                    ),
                    'connections': []
                }

            # Process connection information
            local_port = entry.get(fields['local_interface'])
            remote_port = entry.get(fields['remote_interface'])
            if local_port and remote_port:
                connection = [local_port, remote_port]
                if connection not in enhanced_lldp[normalized_device_id]['connections']:
                    enhanced_lldp[normalized_device_id]['connections'].append(connection)
                    self.logger.debug(f"LLDP: Added connection {connection} for {normalized_device_id}")

            # Handle device queueing
            if ip_address:
                self.logger.info(f"LLDP: Evaluating {normalized_device_id} ({ip_address}) for queuing")
                self.logger.debug(f"LLDP Queue state for {ip_address}:")
                self.logger.debug(f"  - In visited IPs: {ip_address in self.visited_ips}")
                self.logger.debug(f"  - In visited hostnames: {normalized_device_id in self.visited_hostnames}")
                self.logger.debug(f"  - In unreachable: {ip_address in self.unreachable_hosts}")

                if not self._is_visited(DeviceInfo(hostname=ip_address, ip=ip_address, password="", username="")):
                    new_device = DeviceInfo(
                        hostname=ip_address,
                        ip=ip_address,
                        username=self.config.username,
                        password=self.config.password,
                        timeout=self.config.timeout,
                        platform=enhanced_lldp[normalized_device_id]['platform']
                    )

                    exclude_patterns = self.config.exclude_string.split(
                        ',') if self.config.exclude_string else []
                    if exclude_patterns and any(
                            pattern.lower() in device_id.hostname.lower() for pattern in exclude_patterns):
                        self.logger.info(f"Skipping excluded device: {device_id}")
                        continue
                    self.logger.info(f"Queueing new device: {device_id}")
                    self.queue.put(new_device)
                else:
                    self.logger.info(f"LLDP: Skipping known device {ip_address} ({normalized_device_id})")

        return enhanced_lldp

    def _determine_platform_from_capabilities(self, capabilities_str: str) -> str:
        """Determine platform based on LLDP capabilities or description."""
        if not capabilities_str:
            return 'unknown'

        capabilities_str = capabilities_str.lower()

        # Check for explicit platform indicators
        if 'nx-os' in capabilities_str:
            return 'nxos_ssh'
        elif 'eos' in capabilities_str or 'arista' in capabilities_str:
            return 'eos'
        elif 'ios' in capabilities_str or 'cisco' in capabilities_str:
            return 'ios'

        # Platform inference from capabilities
        if 'router' in capabilities_str or 'switch' in capabilities_str:
            if 'cisco' in capabilities_str:
                return 'ios'  # Default Cisco platform
            elif 'arista' in capabilities_str:
                return 'eos'
            elif 'juniper' in capabilities_str:
                return 'junos'

        return 'ios'  # Default platform if unable to determine

    def create_multipartite_layout(self, G, subset_key='layer', min_layer_dist=1.0, min_node_dist=0.2):
        """Creates a multipartite layout with customizable spacing."""
        # Group nodes by layer
        layers = {}
        for node in G.nodes():
            layer = G.nodes[node][subset_key]
            if layer not in layers:
                layers[layer] = []
            layers[layer].append(node)

        # Sort layers by number
        sorted_layers = sorted(layers.keys())
        pos = {}

        # Position nodes layer by layer
        for layer_idx, layer in enumerate(sorted_layers):
            nodes = layers[layer]

            # Distribute nodes evenly in vertical space
            if len(nodes) > 1:
                y_positions = np.linspace(0, 1, len(nodes))
            else:
                y_positions = [0.5]  # Center single nodes

            # Position nodes within layer
            for node_idx, node in enumerate(sorted(nodes)):
                x = layer_idx * min_layer_dist
                y = y_positions[node_idx]
                pos[node] = (x, y)

        # Scale horizontal positions to [0,1]
        max_x = max(x for x, y in pos.values())
        if max_x > 0:
            for node in pos:
                x, y = pos[node]
                pos[node] = (x / max_x, y)

        # Add padding
        padding = 0.05
        for node in pos:
            x, y = pos[node]
            pos[node] = (x * (1 - 2 * padding) + padding,
                         y * (1 - 2 * padding) + padding)

        return pos

    def create_network_svg(self, map_data: dict, output_path: Path, min_layer_dist=1.0, min_node_dist=0.2,
                           dark_mode=True):
        """
        Create an SVG visualization of the network map using balloon layout.
        """
        # Create NetworkX graph
        G = nx.Graph()

        # Add nodes and edges
        added_edges = set()  # Track which edges have been added
        for node, data in map_data.items():
            # Add node with its attributes
            G.add_node(node,
                       ip=data['node_details'].get('ip', ''),
                       platform=data['node_details'].get('platform', ''))

            # Add edges from peer connections
            for peer, peer_data in data['peers'].items():
                if peer in map_data:  # Only add edge if peer exists
                    edge_key = tuple(sorted([node, peer]))
                    if edge_key not in added_edges:
                        # Get connection information
                        connections = peer_data.get('connections', [])
                        if connections:
                            local_port, remote_port = connections[0]
                            label = f"{local_port} - {remote_port}"
                        else:
                            label = ""
                        G.add_edge(node, peer, connection=label)
                        added_edges.add(edge_key)

        # Set up colors based on mode
        if dark_mode:
            bg_color = '#1C1C1C'
            edge_color = '#FFFFFF'
            node_color = '#4B77BE'  # Medium blue
            font_color = 'white'
            node_edge_color = '#FFFFFF'
        else:
            bg_color = 'white'
            edge_color = 'gray'
            node_color = 'lightblue'
            font_color = 'black'
            node_edge_color = 'black'

        # Create figure with larger size
        plt.figure(figsize=(20, 15))

        # Set figure background
        plt.gca().set_facecolor(bg_color)
        plt.gcf().set_facecolor(bg_color)

        # Calculate balloon layout using internal method
        pos = self._calculate_balloon_layout(G)

        # Draw edges with labels
        for edge in G.edges():
            node1, node2 = edge
            pos1 = pos[node1]
            pos2 = pos[node2]

            # Draw edge
            plt.plot([pos1[0], pos2[0]],
                     [pos1[1], pos2[1]],
                     color=edge_color,
                     linewidth=1.0,
                     alpha=0.6)

            # Add edge label at midpoint
            connection = G.edges[edge].get('connection', '')
            if connection:
                mid_x = (pos1[0] + pos2[0]) / 2
                mid_y = (pos1[1] + pos2[1]) / 2
                plt.text(mid_x, mid_y,
                         connection,
                         horizontalalignment='center',
                         verticalalignment='center',
                         fontsize=6,
                         color=font_color,
                         bbox=dict(facecolor=bg_color, edgecolor='none', alpha=0.7, pad=0.2),
                         zorder=1)

        # Draw nodes with rectangles
        node_width = 0.1
        node_height = 0.03
        for node, (x, y) in pos.items():
            plt.gca().add_patch(plt.Rectangle((x - node_width / 2, y - node_height / 2),
                                              node_width, node_height,
                                              facecolor=node_color,
                                              edgecolor=node_edge_color,
                                              linewidth=1.0,
                                              zorder=2))

            # Add node labels
            plt.text(x, y,
                     node,
                     horizontalalignment='center',
                     verticalalignment='center',
                     fontsize=8,
                     color=font_color,
                     bbox=dict(facecolor=node_color, edgecolor='none', pad=0.5),
                     zorder=3)

        # Remove axes
        plt.axis('off')

        # Adjust plot limits
        margin = 0.1
        x_values = [x for x, y in pos.values()]
        y_values = [y for x, y in pos.values()]
        plt.xlim(min(x_values) - margin, max(x_values) + margin)
        plt.ylim(min(y_values) - margin, max(y_values) + margin)

        # Save as SVG
        plt.savefig(output_path,
                    format='svg',
                    bbox_inches='tight',
                    pad_inches=0.1,
                    facecolor=bg_color,
                    edgecolor='none',
                    transparent=False)
        plt.close()

        return G
    def _calculate_balloon_layout(self, G, scale=1.0):
        """Helper method to calculate balloon layout positions."""
        # Find root node (core switch/router)
        core_nodes = [node for node in G.nodes() if 'core' in node.lower()]
        if core_nodes:
            root = max(core_nodes, key=lambda x: G.degree(x))
        else:
            # Fall back to highest degree node
            # failure here
            root = max(G.nodes(), key=lambda x: G.degree(x))

        # Initialize positions
        pos = {}
        pos[root] = (0, 0)

        # Position hub nodes
        hub_nodes = {node for node in G.nodes() if G.degree(node) >= 2 and node != root}
        angle_increment = 2 * math.pi / max(1, len(hub_nodes))

        # Position hubs in a circle around root
        hub_radius = 1.0 * scale
        for i, hub in enumerate(hub_nodes):
            angle = i * angle_increment
            pos[hub] = (
                hub_radius * math.cos(angle),
                hub_radius * math.sin(angle)
            )

        # Position leaf nodes around their hubs
        leaf_radius = 0.5 * scale
        leaf_nodes = set(G.nodes()) - {root} - hub_nodes
        for hub in hub_nodes:
            children = [n for n in G.neighbors(hub) if n in leaf_nodes]
            if children:
                child_angle_increment = 2 * math.pi / len(children)
                for j, child in enumerate(children):
                    angle = j * child_angle_increment
                    pos[child] = (
                        pos[hub][0] + leaf_radius * math.cos(angle),
                        pos[hub][1] + leaf_radius * math.sin(angle)
                    )
                    leaf_nodes.remove(child)

        # Position any remaining nodes
        remaining_radius = 1.5 * hub_radius
        if leaf_nodes:
            angle_increment = 2 * math.pi / len(leaf_nodes)
            for i, node in enumerate(leaf_nodes):
                angle = i * angle_increment
                pos[node] = (
                    remaining_radius * math.cos(angle),
                    remaining_radius * math.sin(angle)
                )

        return pos

    def _save_map_files(self, map_data: Dict):
        """Save network map data to files with hostname normalization."""
        # Normalize and merge hostnames
        normalized_map = self._normalize_hostnames(map_data)

        output_dir = self.config.output_dir
        map_name = self.config.map_name

        # Save transformed map
        map_path = output_dir / f"{map_name}.json"
        with open(map_path, "w") as fh:
            json.dump(normalized_map, indent=2, fp=fh)

        # Create the diagram files
        create_network_diagrams(normalized_map, output_dir, map_name, self.layout_algo)  # Using 'kk' as default layout

        # Create SVG preview
        svg_path = output_dir / f"{map_name}.svg"
        self.create_network_svg(normalized_map, svg_path, min_layer_dist=1.0, min_node_dist=0.2)

        self.logger.info(f"Created network map files in {output_dir}:")
        self.logger.info(f" - <font color='orange'>{map_name}.json</font>")
        self.logger.info(f" - <font color='orange'>{map_name}.graphml</font>")
        self.logger.info(f" - <font color='orange'>{map_name}.drawio</font>")

    def _normalize_hostnames(self, map_data: Dict) -> Dict:
        """
        This method should now be much simpler since hostnames are already normalized.
        Just handle any edge cases or additional cleanup.
        """
        # Since hostnames should already be normalized, this mainly handles
        # any final cleanup or merging of edge cases

        normalized_hosts = {}

        for hostname, host_data in map_data.items():
            # Double-check normalization (should be a no-op in most cases)
            final_hostname = self._normalize_hostname(hostname)

            if final_hostname not in normalized_hosts:
                normalized_hosts[final_hostname] = host_data
            else:
                # Merge data if somehow we have duplicates
                existing = normalized_hosts[final_hostname]

                # Merge node details
                if not existing['node_details'].get('ip') and host_data['node_details'].get('ip'):
                    existing['node_details']['ip'] = host_data['node_details']['ip']

                if not existing['node_details'].get('platform') and host_data['node_details'].get('platform'):
                    existing['node_details']['platform'] = host_data['node_details']['platform']

                # Merge peers
                for peer, peer_data in host_data['peers'].items():
                    if peer not in existing['peers']:
                        existing['peers'][peer] = peer_data
                    else:
                        # Merge connections
                        existing_connections = set(
                            tuple(conn) for conn in existing['peers'][peer].get('connections', []))
                        new_connections = set(tuple(conn) for conn in peer_data.get('connections', []))
                        combined_connections = list(existing_connections.union(new_connections))
                        existing['peers'][peer]['connections'] = [list(conn) for conn in combined_connections]

        return normalized_hosts

    def transform_map(self, network_map: Dict[str, NetworkDevice]) -> Dict:
        """Transform NetworkDevice objects into the format required by the mapping utility."""
        transformed_map = {}

        # Process each device in the network map
        for hostname, device in network_map.items():
            # Device hostname should already be normalized from _process_device
            normalized_hostname = hostname

            # Add base device information
            transformed_map[normalized_hostname] = {
                "node_details": {
                    "ip": device.ip,
                    "platform": device.platform
                },
                "peers": {}
            }

            # Process each peer connection
            for peer_id, connections in device.connections.items():
                # peer_id should already be normalized from _process_neighbors
                normalized_peer = peer_id

                # Find peer IP from connections
                peer_ip = ""
                peer_platform = ""

                if connections:
                    # Get IP and platform from the first connection
                    peer_ip = connections[0].neighbor_ip or ""
                    peer_platform = connections[0].neighbor_platform or ""

                # Initialize peer entry
                transformed_map[normalized_hostname]["peers"][normalized_peer] = {
                    "ip": peer_ip,
                    "platform": peer_platform,
                    "connections": []
                }

                # Add all connections for this peer (interfaces should already be normalized)
                for conn in connections:
                    connection_pair = [conn.local_port, conn.remote_port]
                    if connection_pair not in transformed_map[normalized_hostname]["peers"][normalized_peer][
                        "connections"]:
                        transformed_map[normalized_hostname]["peers"][normalized_peer]["connections"].append(
                            connection_pair)

        return transformed_map


    def enrich_peer_data(self, data):
        """
        Enrich peer platform information using the top-level node details.
        If a peer device matches a top-level node, update its platform from the node_details.
        If the platform is 'ios' or 'eos', set it to an empty string.
        """
        # Create a lookup for top-level node details
        node_details_lookup = {
            node: details["node_details"]["platform"]
            for node, details in data.items()
        }

        # Iterate through each node and update peer platform information
        for node, details in data.items():
            for peer, peer_info in details["peers"].items():
                if peer in node_details_lookup:
                    # Update peer platform using the node details if available
                    peer_info["platform"] = node_details_lookup[peer]

                # Set platform to blank if it's 'ios' or 'eos'
                if peer_info["platform"].lower() in ["ios", "eos"]:
                    peer_info["platform"] = ""

        return data

    def process_device(self, ip):
        """
        Process a single device - connect to it and gather information
        Returns a dict with device details and peer information
        """
        device_info = {
            'node_details': {
                'ip': ip,
                'platform': '',
                'hostname': ''
            },
            'peers': {}
        }

        try:
            # Attempt connection with primary credentials
            connected = self.try_connection(ip, self.config.username, self.config.password)

            if not connected and self.config.alternate_username:
                # Try alternate credentials if primary fails
                connected = self.try_connection(ip, self.config.alternate_username, self.config.alternate_password)

            if not connected:
                raise Exception(f"Could not connect to device {ip}")

            # Get basic device info
            device_info['node_details'] = self.get_device_details(ip)

            # Get neighbor/peer information
            device_info['peers'] = self.get_peer_information(ip)

            # Update discovery progress
            self.emit_device_discovered(ip, "success")

        except Exception as e:
            self.emit_device_discovered(ip, "failed")
            raise e

        return device_info

    def try_connection(self, ip, username, password):
        """Attempt to connect to a device with given credentials"""
        try:
            # Implement your connection logic here
            # This could use SSH, Telnet, SNMP, etc. depending on your needs
            # Return True if connection succeeds, False otherwise
            return True
        except Exception:
            return False

    def get_device_details(self, ip):
        """Gather basic information about the device"""
        # Implement device information gathering
        # This could include hostname, platform, version, etc.
        return {
            'ip': ip,
            'platform': 'unknown',
            'hostname': f'device_{ip.replace(".", "_")}'
        }

    def get_peer_information(self, ip):
        """Gather information about device peers/neighbors"""
        # Implement peer discovery logic
        # This could use CDP, LLDP, routing tables, etc.
        return {}

    def emit_device_discovered(self, ip, status):
        """Helper method to emit device discovery status"""
        if self.progress_callback:
            self.progress_callback({
                'ip': ip,
                'status': status,
                'devices_discovered': self.stats['devices_discovered'],
                'devices_failed': self.stats['devices_failed'],
                'devices_queued': self.stats['devices_queued']
            })

    def _process_device(self, device_info: DeviceInfo, capabilities: Dict) -> Optional[NetworkDevice]:
        """Process device information with enhanced hostname handling."""
        facts = capabilities['facts']
        discovered_hostname = facts.get('hostname', device_info.hostname)

        # Handle potential Nexus device detected as IOS
        if discovered_hostname == 'Kernel' or discovered_hostname == 'Unknown':
            try:
                # Try to reconnect with nxos_ssh if it was detected as IOS
                if device_info.platform == 'ios':
                    self.logger.debug(
                        f"Possible Nexus device detected as IOS, retrying with NXOS for {device_info.hostname}")
                    alternate_device = DeviceInfo(
                        hostname=device_info.hostname,
                        username=device_info.username,
                        password=device_info.password,
                        timeout=device_info.timeout,
                        platform='nxos_ssh',
                        ip=device_info.hostname
                    )

                    # Get capabilities with nxos_ssh platform
                    alternate_capabilities = run_with_timeout(
                        self.driver_discovery.get_device_capabilities,
                        30,
                        alternate_device,
                        config=self.config
                    )

                    if alternate_capabilities and 'facts' in alternate_capabilities:
                        facts = alternate_capabilities['facts']
                        discovered_hostname = facts.get('hostname')
                        capabilities = alternate_capabilities
                        device_info.platform = 'nxos_ssh'

                        # If still no valid hostname, generate one
                        if not discovered_hostname or discovered_hostname in ['Kernel', 'Unknown']:
                            discovered_hostname = f"nx-{device_info.hostname.replace('.', '_')}"

            except Exception as e:
                self.logger.error(f"Failed to retry as NXOS device: {str(e)}")
                discovered_hostname = f"nx-{device_info.hostname.replace('.', '_')}"

        # Normalize the discovered hostname
        normalized_hostname = self._normalize_hostname(discovered_hostname)

        # Check if we already have this device (by normalized hostname)
        if normalized_hostname in self.network_map:
            self.logger.info(f"Device {normalized_hostname} already exists in network map, updating...")
            existing_device = self.network_map[normalized_hostname]

            # Update IP if the existing device doesn't have one or has a different one
            if not existing_device.ip or existing_device.ip != device_info.ip:
                existing_device.ip = device_info.ip

            return existing_device

        # Create new device with normalized hostname
        device = NetworkDevice(
            hostname=normalized_hostname,  # Use normalized hostname
            ip=device_info.ip,  # Use the actual IP we connected to
            platform=facts.get('model', 'unknown'),
            serial=facts.get('serial_number', 'unknown'),
        )

        self.logger.info(f"Created new device: {normalized_hostname} (IP: {device_info.ip})")
        return device

    def _add_neighbor(self, device: NetworkDevice, neighbor_id: str, data: Dict, protocol: str) -> None:
        """Add neighbor to device connections."""
        if not hasattr(device, 'connections'):
            device.connections = {}

        # Normalize the neighbor_id
        normalized_neighbor_id = self._normalize_hostname(neighbor_id)
        self.logger.debug(f"Normalized neighbor ID: {neighbor_id} -> {normalized_neighbor_id}")

        if normalized_neighbor_id not in device.connections:
            device.connections[normalized_neighbor_id] = []

        # Create the connection object
        connection = DeviceConnection(
            local_port=data.get('local_port', 'unknown'),
            remote_port=data.get('remote_port', 'unknown'),
            protocol=protocol,
            neighbor_ip=data.get('ip', ''),
            neighbor_platform=data.get('platform', 'unknown')
        )

        # Enhanced duplicate check
        is_duplicate = False
        for existing_connection in device.connections[normalized_neighbor_id]:
            if (existing_connection.local_port == connection.local_port and
                    existing_connection.remote_port == connection.remote_port):
                is_duplicate = True



        # Add the connection if it's not a duplicate
        if not is_duplicate:

            device.connections[normalized_neighbor_id].append(connection)
            self.logger.info(
                f"Added connection: {connection.local_port} -> {connection.remote_port} "
                f"for neighbor {normalized_neighbor_id}. Protocol: {protocol}, IP: {connection.neighbor_ip}"
            )
        else:
            self.logger.info(
                f"Skipped adding duplicate connection: {connection.local_port} -> {connection.remote_port} "
                f"for neighbor {normalized_neighbor_id}"
            )



    # def _add_neighbor(self, device: NetworkDevice, neighbor_id: str, data: Dict, protocol: str) -> None:
    #     """Add neighbor to device connections."""
    #     if not hasattr(device, 'connections'):
    #         device.connections = {}
    #
    #     # Normalize the neighbor_id
    #     normalized_neighbor_id = self._normalize_hostname(neighbor_id)
    #     self.logger.debug(f"Normalized neighbor ID: {neighbor_id} -> {normalized_neighbor_id}")
    #
    #     if normalized_neighbor_id not in device.connections:
    #         device.connections[normalized_neighbor_id] = []
    #
    #     # Create the connection object
    #     connection = DeviceConnection(
    #         local_port=data.get('local_port', 'unknown'),
    #         remote_port=data.get('remote_port', 'unknown'),
    #         protocol=protocol,
    #         neighbor_ip=data.get('ip', ''),
    #         neighbor_platform=data.get('platform', 'unknown')
    #     )
    #
    #     # Enhanced duplicate check
    #     is_duplicate = False
    #     for existing_connection in device.connections[normalized_neighbor_id]:
    #         if (existing_connection.local_port == connection.local_port and
    #                 existing_connection.remote_port == connection.remote_port):
    #             self.logger.debug(
    #                 f"Duplicate connection detected: {connection.local_port} -> {connection.remote_port} "
    #                 f"for neighbor {normalized_neighbor_id}. Protocol: {protocol}"
    #             )
    #             # Update IP/platform if they're empty
    #             if not existing_connection.neighbor_ip:
    #                 existing_connection.neighbor_ip = connection.neighbor_ip
    #             if not existing_connection.neighbor_platform or existing_connection.neighbor_platform == 'unknown':
    #                 existing_connection.neighbor_platform = connection.neighbor_platform
    #             is_duplicate = True
    #             break
    #
    #     # Add the connection if it's not a duplicate
    #     if not is_duplicate:
    #         device.connections[normalized_neighbor_id].append(connection)
    #         self.logger.info(
    #             f"Added connection: {connection.local_port} -> {connection.remote_port} "
    #             f"for neighbor {normalized_neighbor_id}. Protocol: {protocol}, IP: {connection.neighbor_ip}"
    #         )
    #     else:
    #         self.logger.info(
    #             f"Skipped adding duplicate connection: {connection.local_port} -> {connection.remote_port} "
    #             f"for neighbor {normalized_neighbor_id}"
    #         )

    def _is_excluded(self, device_id: str) -> bool:
        if not self.config.exclude_string:
            return False
        return any(exc in device_id for exc in self.config.exclude_string.split(','))

    def _save_debug_info(self) -> None:
        debug_info = {
            'visited': list(self.visited),
            'failed': list(self.failed_devices),
            'network_map': {
                hostname: device.to_dict()
                for hostname, device in self.network_map.items()
            }
        }
        debug_file = self.config.output_dir / "discovery_debug.json"
        debug_file.write_text(json.dumps(debug_info, indent=2))

    def get_discovery_stats(self) -> Dict:
        """Include unreachable hosts in statistics."""
        return {
            'devices_discovered': len(self.network_map),
            'devices_visited': len(self.visited),
            'devices_failed': len(self.failed_devices),
            'unreachable_hosts': len(self.unreachable_hosts),
            'queue_remaining': self.queue.qsize()
        }

    def set_progress_callback(self, callback):
        """Set callback for progress updates"""
        self.progress_callback = callback

    def update_progress(self):
        """Update progress stats"""
        if self.progress_callback:
            self.progress_callback(self.stats.copy())  # Send copy to avoid reference issues

