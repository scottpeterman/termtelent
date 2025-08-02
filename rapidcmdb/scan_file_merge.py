#!/usr/bin/env python3
"""
SNMP Scan File Merger

This script merges multiple SNMP scan files (SNMPv2/v3) with intelligent deduplication.
Preference is given to SNMPv3 scans when conflicts arise.
"""

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime
import re


class SNMPScanMerger:
    def __init__(self):
        self.snmpv3_priority = True  # Prefer v3 over v2

    def detect_snmp_version(self, filename: str) -> str:
        """Detect SNMP version from filename or content analysis"""
        filename_lower = filename.lower()
        if 'v3' in filename_lower or 'snmpv3' in filename_lower:
            return 'v3'
        elif 'v2' in filename_lower or 'snmpv2' in filename_lower:
            return 'v2'
        else:
            # Default assumption - could be enhanced with content analysis
            return 'v2'

    def load_scan_file(self, filepath: Path) -> Tuple[Dict[str, Any], str]:
        """Load and parse a scan file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            version = self.detect_snmp_version(filepath.name)
            print(f"Loaded {filepath.name} (detected as SNMP{version}) - {data.get('total_devices', 0)} devices")

            return data, version

        except Exception as e:
            print(f"Error loading {filepath}: {e}")
            return None, None

    def get_device_key(self, device: Dict[str, Any]) -> str:
        """Generate a unique key for device identification"""
        # Use sys_name if available, otherwise primary IP
        if device.get('sys_name'):
            return device['sys_name'].lower()
        elif device.get('primary_ip'):
            return device['primary_ip']
        else:
            return device.get('id', 'unknown')

    def get_device_priority_score(self, device: Dict[str, Any], snmp_version: str) -> int:
        """Calculate priority score for device selection"""
        score = 0

        # SNMP version preference
        if snmp_version == 'v3':
            score += 100

        # Confidence score
        score += device.get('confidence_score', 0)

        # Detection method quality
        detection_method = device.get('detection_method', '')
        if 'enhanced' in detection_method:
            score += 20
        elif 'definitive' in detection_method:
            score += 15
        elif 'oid_match' in detection_method:
            score += 10

        # Prefer devices with more data
        if device.get('vendor'):
            score += 5
        if device.get('device_type'):
            score += 5
        if device.get('serial_number'):
            score += 5
        if device.get('sys_descr'):
            score += 3

        # More recent scans get slight preference
        try:
            last_seen = device.get('last_seen', '')
            if last_seen:
                # Simple recency boost - could be more sophisticated
                score += 1
        except:
            pass

        return score

    def merge_device_data(self, existing_device: Dict[str, Any], new_device: Dict[str, Any]) -> Dict[str, Any]:
        """Merge data from two device records"""
        merged = existing_device.copy()

        # Merge IP addresses
        all_ips = set(existing_device.get('all_ips', []))
        all_ips.update(new_device.get('all_ips', []))
        merged['all_ips'] = sorted(list(all_ips))

        # Merge MAC addresses
        all_macs = set(existing_device.get('mac_addresses', []))
        all_macs.update(new_device.get('mac_addresses', []))
        merged['mac_addresses'] = sorted(list(all_macs))

        # Merge interfaces
        merged_interfaces = existing_device.get('interfaces', {}).copy()
        merged_interfaces.update(new_device.get('interfaces', {}))
        merged['interfaces'] = merged_interfaces

        # Merge SNMP data
        merged_snmp = existing_device.get('snmp_data_by_ip', {}).copy()
        for ip, data in new_device.get('snmp_data_by_ip', {}).items():
            if ip in merged_snmp:
                merged_snmp[ip].update(data)
            else:
                merged_snmp[ip] = data
        merged['snmp_data_by_ip'] = merged_snmp

        # Take better values for scalar fields
        for field in ['vendor', 'device_type', 'serial_number', 'sys_descr', 'sys_name', 'os_version']:
            if not merged.get(field) and new_device.get(field):
                merged[field] = new_device[field]

        # Update scan tracking
        merged['scan_count'] = existing_device.get('scan_count', 0) + new_device.get('scan_count', 0)

        # Keep the most recent last_seen
        if new_device.get('last_seen'):
            if not merged.get('last_seen') or new_device['last_seen'] > merged.get('last_seen', ''):
                merged['last_seen'] = new_device['last_seen']
                merged['last_scan_id'] = new_device.get('last_scan_id', '')

        return merged

    def merge_statistics(self, scan_files_data: List[Tuple[Dict[str, Any], str]]) -> Dict[str, Any]:
        """Merge statistics from all scan files"""
        merged_stats = {
            'total_devices': 0,
            'total_sessions': 0,
            'vendor_breakdown': {},
            'type_breakdown': {},
            'last_scan_date': '',
            'oldest_device': '',
            'avg_confidence': 0,
            'devices_per_subnet': {},
            'error_stats': {},
            'snmp_version_breakdown': {'v2': 0, 'v3': 0}
        }

        total_confidence = 0
        device_count = 0

        for data, version in scan_files_data:
            stats = data.get('statistics', {})

            # Count sessions
            merged_stats['total_sessions'] += stats.get('total_sessions', 0)

            # Merge vendor breakdown
            for vendor, count in stats.get('vendor_breakdown', {}).items():
                merged_stats['vendor_breakdown'][vendor] = merged_stats['vendor_breakdown'].get(vendor, 0) + count

            # Merge type breakdown
            for device_type, count in stats.get('type_breakdown', {}).items():
                merged_stats['type_breakdown'][device_type] = merged_stats['type_breakdown'].get(device_type, 0) + count

            # Track SNMP versions
            merged_stats['snmp_version_breakdown'][version] += len(data.get('devices', {}))

            # Update last scan date
            last_scan = stats.get('last_scan_date', '')
            if last_scan and (not merged_stats['last_scan_date'] or last_scan > merged_stats['last_scan_date']):
                merged_stats['last_scan_date'] = last_scan

            # Update oldest device
            oldest = stats.get('oldest_device', '')
            if oldest and (not merged_stats['oldest_device'] or oldest < merged_stats['oldest_device']):
                merged_stats['oldest_device'] = oldest

            # Merge subnet breakdown
            for subnet, count in stats.get('devices_per_subnet', {}).items():
                merged_stats['devices_per_subnet'][subnet] = merged_stats['devices_per_subnet'].get(subnet, 0) + count

        return merged_stats

    def merge_sessions(self, scan_files_data: List[Tuple[Dict[str, Any], str]]) -> List[Dict[str, Any]]:
        """Merge session data from all scan files"""
        all_sessions = []

        for data, version in scan_files_data:
            sessions = data.get('sessions', [])
            # Add version info to sessions for tracking
            for session in sessions:
                session_copy = session.copy()
                session_copy['snmp_version'] = version
                all_sessions.append(session_copy)

        # Sort by timestamp
        all_sessions.sort(key=lambda x: x.get('timestamp', ''))

        return all_sessions

    def merge_scan_files(self, file_paths: List[Path]) -> Dict[str, Any]:
        """Main method to merge multiple scan files"""
        if not file_paths:
            raise ValueError("No scan files provided")

        print(f"Merging {len(file_paths)} scan files...")

        # Load all scan files
        scan_files_data = []
        for filepath in file_paths:
            data, version = self.load_scan_file(filepath)
            if data and version:
                scan_files_data.append((data, version))

        if not scan_files_data:
            raise ValueError("No valid scan files could be loaded")

        # Initialize merged result with structure from first file
        base_data = scan_files_data[0][0]
        merged_result = {
            'version': base_data.get('version', '1.0.0'),
            'last_updated': datetime.now().isoformat(),
            'total_devices': 0,
            'devices': {},
            'sessions': [],
            'statistics': {},
            'config': base_data.get('config', {}),
            'merge_info': {
                'source_files': [str(p) for p in file_paths],
                'merge_timestamp': datetime.now().isoformat(),
                'snmp_versions_merged': []
            }
        }

        # Track devices by key for deduplication
        device_registry = {}  # key -> (device_data, snmp_version, priority_score)

        print("\nProcessing devices for deduplication...")

        # Process all devices from all files
        for data, version in scan_files_data:
            merged_result['merge_info']['snmp_versions_merged'].append(version)

            devices = data.get('devices', {})
            for device_id, device in devices.items():
                device_key = self.get_device_key(device)
                priority_score = self.get_device_priority_score(device, version)

                if device_key in device_registry:
                    existing_device, existing_version, existing_score = device_registry[device_key]

                    if priority_score > existing_score:
                        # New device has higher priority - replace
                        print(
                            f"  Replacing {device_key} (SNMP{existing_version}, score {existing_score}) with SNMP{version} (score {priority_score})")
                        merged_device = self.merge_device_data(device, existing_device)
                        device_registry[device_key] = (merged_device, version, priority_score)
                    else:
                        # Existing device has higher priority - merge data
                        print(
                            f"  Merging data for {device_key} (keeping SNMP{existing_version}, score {existing_score} > {priority_score})")
                        merged_device = self.merge_device_data(existing_device, device)
                        device_registry[device_key] = (merged_device, existing_version, existing_score)
                else:
                    # New device
                    print(f"  Adding {device_key} (SNMP{version}, score {priority_score})")
                    device_registry[device_key] = (device, version, priority_score)

        # Add deduplicated devices to result
        for device_key, (device_data, version, score) in device_registry.items():
            merged_result['devices'][device_data['id']] = device_data

        merged_result['total_devices'] = len(merged_result['devices'])

        # Merge sessions and statistics
        merged_result['sessions'] = self.merge_sessions(scan_files_data)
        merged_result['statistics'] = self.merge_statistics(scan_files_data)
        merged_result['statistics']['total_devices'] = merged_result['total_devices']

        # Calculate final average confidence
        if merged_result['devices']:
            total_confidence = sum(device.get('confidence_score', 0) for device in merged_result['devices'].values())
            merged_result['statistics']['avg_confidence'] = total_confidence / len(merged_result['devices'])

        print(f"\nMerge completed:")
        print(f"  Total devices after deduplication: {merged_result['total_devices']}")
        print(f"  Total sessions: {len(merged_result['sessions'])}")
        print(f"  Average confidence: {merged_result['statistics']['avg_confidence']:.1f}")
        print(f"  SNMP version breakdown: {merged_result['statistics']['snmp_version_breakdown']}")

        return merged_result

    def save_merged_file(self, merged_data: Dict[str, Any], output_path: Path):
        """Save merged data to file"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(merged_data, f, indent=2, ensure_ascii=False)
            print(f"\nMerged scan file saved to: {output_path}")
        except Exception as e:
            print(f"Error saving merged file: {e}")
            raise


def main():
    parser = argparse.ArgumentParser(
        description='Merge SNMP scan files with deduplication, preferring SNMPv3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python snmp_merger.py scan1.json scan2.json -o merged_scan.json
  python snmp_merger.py *.json -o all_scans_merged.json
  python snmp_merger.py 10.202.88.json 10.202.88_v3.json
        """
    )

    parser.add_argument('files', nargs='+', type=Path,
                        help='SNMP scan files to merge (JSON format)')
    parser.add_argument('-o', '--output', type=Path, default='merged_scan.json',
                        help='Output file path (default: merged_scan.json)')
    parser.add_argument('--no-v3-preference', action='store_true',
                        help='Disable SNMPv3 preference (use confidence scores only)')

    args = parser.parse_args()

    # Validate input files
    valid_files = []
    for file_path in args.files:
        if not file_path.exists():
            print(f"Warning: File not found: {file_path}")
            continue
        if not file_path.is_file():
            print(f"Warning: Not a file: {file_path}")
            continue
        valid_files.append(file_path)

    if not valid_files:
        print("Error: No valid input files found")
        sys.exit(1)

    try:
        # Create merger and process files
        merger = SNMPScanMerger()
        if args.no_v3_preference:
            merger.snmpv3_priority = False

        merged_data = merger.merge_scan_files(valid_files)
        merger.save_merged_file(merged_data, args.output)

        print(f"\n✅ Successfully merged {len(valid_files)} scan files")

    except Exception as e:
        print(f"❌ Error during merge: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()