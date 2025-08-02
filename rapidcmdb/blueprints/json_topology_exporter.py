#!/usr/bin/env python3
"""
JSON Topology Exporter - Convert topology map to standard JSON format
Converts the internal topology map format to the standard JSON format used by mapping applications
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class JSONTopologyExporter:
    """
    Exports topology data to the standard JSON format used by mapping applications.

    Converts from internal topology_map format:
    {
        "device_name": {
            "node_details": {"ip": "...", "platform": "..."},
            "peers": {
                "peer_name": {
                    "ip": "...",
                    "platform": "...",
                    "connections": [["local_int", "remote_int"], ...]
                }
            }
        }
    }

    To standard format:
    {
        "device_name": {
            "node_details": {"ip": "...", "platform": "..."},
            "peers": {
                "peer_name": {
                    "ip": "...",
                    "platform": "...",
                    "connections": [["local_int", "remote_int"], ...]
                }
            }
        }
    }
    """

    def __init__(self, include_metadata: bool = True, pretty_print: bool = True):
        """
        Initialize the JSON topology exporter.

        Args:
            include_metadata: Whether to include export metadata in the output
            pretty_print: Whether to format JSON with indentation for readability
        """
        self.include_metadata = include_metadata
        self.pretty_print = pretty_print

    def convert_topology_map(self, topology_map: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert internal topology map to standard JSON format.

        Args:
            topology_map: Internal topology map from build_topology_map()

        Returns:
            Dictionary in standard JSON topology format
        """
        if not topology_map:
            logger.warning("Empty topology map provided for conversion")
            return {}

        logger.info(f"Converting topology map with {len(topology_map)} devices to standard JSON format")

        # The internal format is already very close to the standard format
        # We just need to ensure consistent structure and clean up any issues
        converted_topology = {}

        conversion_stats = {
            'devices_processed': 0,
            'total_connections': 0,
            'peers_processed': 0,
            'empty_devices_skipped': 0
        }

        for device_name, device_data in topology_map.items():
            try:
                # Skip devices with no useful data
                if not device_data or (
                        not device_data.get('node_details') and
                        not device_data.get('peers')
                ):
                    logger.debug(f"Skipping empty device: {device_name}")
                    conversion_stats['empty_devices_skipped'] += 1
                    continue

                # Initialize device entry in standard format
                converted_device = {
                    "node_details": {},
                    "peers": {}
                }

                # Convert node_details
                node_details = device_data.get('node_details', {})
                converted_device["node_details"] = {
                    "ip": str(node_details.get('ip', '')).strip(),
                    "platform": str(node_details.get('platform', '')).strip()
                }

                # Convert peers
                peers = device_data.get('peers', {})
                for peer_name, peer_data in peers.items():
                    if not peer_name or not peer_name.strip():
                        logger.debug(f"Skipping peer with empty name for device {device_name}")
                        continue

                    # Clean peer name
                    clean_peer_name = str(peer_name).strip()

                    # Convert peer data
                    converted_peer = {
                        "ip": str(peer_data.get('ip', '')).strip(),
                        "platform": str(peer_data.get('platform', '')).strip(),
                        "connections": []
                    }

                    # Convert connections
                    connections = peer_data.get('connections', [])
                    if connections:
                        for connection in connections:
                            if isinstance(connection, (list, tuple)) and len(connection) >= 2:
                                # Ensure connection is a list of two strings
                                clean_connection = [
                                    str(connection[0]).strip(),
                                    str(connection[1]).strip()
                                ]
                                converted_peer["connections"].append(clean_connection)
                                conversion_stats['total_connections'] += 1
                            else:
                                logger.warning(
                                    f"Invalid connection format for {device_name} -> {peer_name}: {connection}")

                    converted_device["peers"][clean_peer_name] = converted_peer
                    conversion_stats['peers_processed'] += 1

                converted_topology[device_name] = converted_device
                conversion_stats['devices_processed'] += 1

            except Exception as e:
                logger.error(f"Error converting device {device_name}: {e}")
                continue

        logger.info(f"Topology conversion completed: {conversion_stats}")

        return converted_topology

    def add_export_metadata(self, topology_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add metadata to the exported topology.

        Args:
            topology_data: Converted topology data

        Returns:
            Topology data with metadata added
        """
        if not self.include_metadata:
            return topology_data

        # Calculate statistics
        total_devices = len(topology_data)
        total_connections = sum(
            len(device_data.get('peers', {}))
            for device_data in topology_data.values()
        )
        total_physical_connections = sum(
            sum(len(peer_data.get('connections', [])) for peer_data in device_data.get('peers', {}).values())
            for device_data in topology_data.values()
        )

        # Create metadata
        metadata = {
            "_export_metadata": {
                "format_version": "1.0",
                "export_timestamp": datetime.now().isoformat(),
                "exported_by": "NAPALM CMDB JSON Topology Exporter",
                "source_system": "NAPALM CMDB Web Interface",
                "statistics": {
                    "total_devices": total_devices,
                    "total_peer_relationships": total_connections,
                    "total_physical_connections": total_physical_connections,
                    "average_connections_per_device": round(total_connections / total_devices,
                                                            2) if total_devices > 0 else 0
                },
                "format_description": "Standard JSON topology format compatible with mapping applications",
                "structure": {
                    "device_name": {
                        "node_details": {
                            "ip": "Primary IP address of the device",
                            "platform": "Device platform/model information"
                        },
                        "peers": {
                            "peer_device_name": {
                                "ip": "IP address of the peer device",
                                "platform": "Platform information of the peer",
                                "connections": [
                                    ["local_interface", "remote_interface"],
                                    "Additional connection pairs..."
                                ]
                            }
                        }
                    }
                }
            }
        }

        # Add metadata to the beginning of the dictionary
        result = metadata.copy()
        result.update(topology_data)

        return result

    def export_to_file(self, topology_map: Dict[str, Any], output_path: Path) -> bool:
        """
        Export topology map to JSON file.

        Args:
            topology_map: Internal topology map from build_topology_map()
            output_path: Path where to save the JSON file

        Returns:
            True if export successful, False otherwise
        """
        try:
            logger.info(f"Exporting topology to JSON file: {output_path}")

            # Convert to standard format
            converted_topology = self.convert_topology_map(topology_map)

            if not converted_topology:
                logger.error("No data to export after conversion")
                return False

            # Add metadata if requested
            final_data = self.add_export_metadata(converted_topology)

            # Write to file
            with open(output_path, 'w', encoding='utf-8') as f:
                if self.pretty_print:
                    json.dump(final_data, f, indent=2, ensure_ascii=False, sort_keys=True)
                else:
                    json.dump(final_data, f, ensure_ascii=False, separators=(',', ':'))

            file_size = output_path.stat().st_size
            logger.info(f"Successfully exported {len(converted_topology)} devices to {output_path} ({file_size} bytes)")

            return True

        except Exception as e:
            logger.error(f"Error exporting topology to JSON file: {e}")
            return False

    def export_to_string(self, topology_map: Dict[str, Any]) -> Optional[str]:
        """
        Export topology map to JSON string.

        Args:
            topology_map: Internal topology map from build_topology_map()

        Returns:
            JSON string or None if export failed
        """
        try:
            # Convert to standard format
            converted_topology = self.convert_topology_map(topology_map)

            if not converted_topology:
                logger.error("No data to export after conversion")
                return None

            # Add metadata if requested
            final_data = self.add_export_metadata(converted_topology)

            # Return as JSON string
            if self.pretty_print:
                return json.dumps(final_data, indent=2, ensure_ascii=False, sort_keys=True)
            else:
                return json.dumps(final_data, ensure_ascii=False, separators=(',', ':'))

        except Exception as e:
            logger.error(f"Error exporting topology to JSON string: {e}")
            return None

    def validate_exported_data(self, exported_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate the exported topology data structure.

        Args:
            exported_data: The exported topology data to validate

        Returns:
            Dictionary with validation results
        """
        validation_results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'statistics': {
                'devices_checked': 0,
                'peers_checked': 0,
                'connections_checked': 0
            }
        }

        try:
            # Skip metadata for validation
            topology_data = {k: v for k, v in exported_data.items() if not k.startswith('_')}

            for device_name, device_data in topology_data.items():
                validation_results['statistics']['devices_checked'] += 1

                # Check device structure
                if not isinstance(device_data, dict):
                    validation_results['errors'].append(f"Device {device_name}: Invalid device data structure")
                    validation_results['valid'] = False
                    continue

                # Check node_details
                node_details = device_data.get('node_details', {})
                if not isinstance(node_details, dict):
                    validation_results['errors'].append(f"Device {device_name}: Invalid node_details structure")
                    validation_results['valid'] = False

                # Check peers
                peers = device_data.get('peers', {})
                if not isinstance(peers, dict):
                    validation_results['errors'].append(f"Device {device_name}: Invalid peers structure")
                    validation_results['valid'] = False
                    continue

                for peer_name, peer_data in peers.items():
                    validation_results['statistics']['peers_checked'] += 1

                    if not isinstance(peer_data, dict):
                        validation_results['errors'].append(
                            f"Device {device_name}, Peer {peer_name}: Invalid peer data structure")
                        validation_results['valid'] = False
                        continue

                    # Check connections
                    connections = peer_data.get('connections', [])
                    if not isinstance(connections, list):
                        validation_results['errors'].append(
                            f"Device {device_name}, Peer {peer_name}: Invalid connections structure")
                        validation_results['valid'] = False
                        continue

                    for i, connection in enumerate(connections):
                        validation_results['statistics']['connections_checked'] += 1

                        if not isinstance(connection, list) or len(connection) != 2:
                            validation_results['errors'].append(
                                f"Device {device_name}, Peer {peer_name}, Connection {i}: "
                                f"Invalid connection format - should be [local_interface, remote_interface]"
                            )
                            validation_results['valid'] = False

                        # Check for empty interface names
                        if isinstance(connection, list) and len(connection) == 2:
                            if not connection[0] or not connection[1]:
                                validation_results['warnings'].append(
                                    f"Device {device_name}, Peer {peer_name}, Connection {i}: "
                                    f"Empty interface name(s): {connection}"
                                )

        except Exception as e:
            validation_results['valid'] = False
            validation_results['errors'].append(f"Validation error: {e}")

        return validation_results


def create_sample_topology() -> Dict[str, Any]:
    """Create a sample topology for testing purposes."""
    return {
        "switch-core-01": {
            "node_details": {
                "ip": "10.0.1.1",
                "platform": "Cisco C9300-24T"
            },
            "peers": {
                "switch-access-01": {
                    "ip": "10.0.1.10",
                    "platform": "Cisco C2960X-48FPD-L",
                    "connections": [
                        ["Gi1/0/1", "Gi1/0/49"],
                        ["Gi1/0/2", "Gi1/0/50"]
                    ]
                },
                "router-wan-01": {
                    "ip": "10.0.1.254",
                    "platform": "Cisco ISR4321",
                    "connections": [
                        ["Gi1/0/24", "Gi0/0/0"]
                    ]
                }
            }
        },
        "switch-access-01": {
            "node_details": {
                "ip": "10.0.1.10",
                "platform": "Cisco C2960X-48FPD-L"
            },
            "peers": {
                "switch-core-01": {
                    "ip": "10.0.1.1",
                    "platform": "Cisco C9300-24T",
                    "connections": [
                        ["Gi1/0/49", "Gi1/0/1"],
                        ["Gi1/0/50", "Gi1/0/2"]
                    ]
                }
            }
        },
        "router-wan-01": {
            "node_details": {
                "ip": "10.0.1.254",
                "platform": "Cisco ISR4321"
            },
            "peers": {
                "switch-core-01": {
                    "ip": "10.0.1.1",
                    "platform": "Cisco C9300-24T",
                    "connections": [
                        ["Gi0/0/0", "Gi1/0/24"]
                    ]
                }
            }
        }
    }


if __name__ == "__main__":
    # Example usage and testing
    logging.basicConfig(level=logging.INFO)

    # Create sample topology
    sample_topology = create_sample_topology()

    # Test export to string
    exporter = JSONTopologyExporter(include_metadata=True, pretty_print=True)

    print("=== Sample Topology Export ===")
    json_output = exporter.export_to_string(sample_topology)
    if json_output:
        print(json_output)

    # Test validation
    print("\n=== Validation Results ===")
    converted = exporter.convert_topology_map(sample_topology)
    validation = exporter.validate_exported_data(converted)
    print(f"Valid: {validation['valid']}")
    print(f"Errors: {validation['errors']}")
    print(f"Warnings: {validation['warnings']}")
    print(f"Statistics: {validation['statistics']}")