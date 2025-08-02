#!/usr/bin/env python3
"""
Network Device Scan Aggregator
Processes multiple JSON scan result files and creates:
1. Aggregated deduplicated JSON in the same format
2. CSV export with sysdesc strings and key device information
"""

import json
import csv
import os
import glob
from datetime import datetime
from collections import defaultdict
import argparse


def load_json_files(folder_path):
    """Load all JSON files from the specified folder."""
    json_files = glob.glob(os.path.join(folder_path, "*.json"))
    data_list = []

    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data['source_file'] = os.path.basename(file_path)
                data_list.append(data)
                print(f"Loaded: {file_path}")
        except Exception as e:
            print(f"Error loading {file_path}: {e}")

    return data_list


def deduplicate_devices(all_data):
    """
    Deduplicate devices based on primary_ip and device characteristics.
    Keep the most recent/complete information for each device.
    Use proper hostnames when available instead of IP-based IDs.
    """
    device_map = {}
    all_sessions = []

    for data in all_data:
        # Collect all sessions
        if 'sessions' in data:
            for session in data['sessions']:
                session['source_file'] = data['source_file']
                all_sessions.append(session)

        # Process devices
        if 'devices' in data:
            for device_id, device in data['devices'].items():
                primary_ip = device.get('primary_ip', '')

                # ✅ FIX: Clean hostname extraction
                sys_name = device.get('sys_name', '')

                # Extract hostname from SNMP data if sys_name is not meaningful
                if not sys_name or sys_name.startswith('ip_') or sys_name == primary_ip:
                    if 'snmp_data_by_ip' in device:
                        for ip, snmp_data in device['snmp_data_by_ip'].items():
                            snmp_hostname = snmp_data.get('1.3.6.1.2.1.1.5.0', '')
                            if (snmp_hostname and snmp_hostname != ip and
                                    not snmp_hostname.startswith('ip_') and snmp_hostname != primary_ip):
                                sys_name = snmp_hostname
                                device['sys_name'] = sys_name  # Update the device
                                break

                # ✅ CRITICAL FIX: Use CLEAN hostname for both key AND ID
                if sys_name and sys_name != primary_ip and not sys_name.startswith('ip_'):
                    # Use hostname for deduplication key (with prefix to avoid IP conflicts)
                    unique_key = f"hostname_{sys_name}"
                    # BUT use the CLEAN hostname as the actual device ID
                    preferred_id = sys_name  # ✅ Clean hostname, no prefix!
                else:
                    unique_key = f"ip_{primary_ip}"
                    preferred_id = f"ip_{primary_ip.replace('.', '_')}"

                if unique_key not in device_map:
                    device_copy = device.copy()
                    # ✅ FIX: Use clean hostname as ID
                    device_copy['id'] = preferred_id
                    device_copy['source_files'] = [data['source_file']]
                    device_map[unique_key] = device_copy
                else:
                    # Merge information, keeping the most recent or complete data
                    existing = device_map[unique_key]
                    existing['source_files'].append(data['source_file'])

                    # ✅ FIX: Update ID to use clean hostname if this device has a better name
                    if (sys_name and sys_name != primary_ip and not sys_name.startswith('ip_') and
                            existing['id'].startswith('ip_')):
                        existing['id'] = sys_name  # ✅ Clean hostname, no prefix!
                        existing['sys_name'] = sys_name

                    # Update last_seen to the most recent
                    if device.get('last_seen', '') > existing.get('last_seen', ''):
                        existing['last_seen'] = device['last_seen']

                    # Update scan_count (sum them up)
                    existing['scan_count'] = existing.get('scan_count', 0) + device.get('scan_count', 0)

                    # Merge SNMP data
                    if 'snmp_data_by_ip' in device:
                        if 'snmp_data_by_ip' not in existing:
                            existing['snmp_data_by_ip'] = {}
                        for ip, snmp_data in device['snmp_data_by_ip'].items():
                            if ip not in existing['snmp_data_by_ip']:
                                existing['snmp_data_by_ip'][ip] = snmp_data
                            else:
                                # Merge SNMP data, preferring non-null values
                                for key, value in snmp_data.items():
                                    if value and value != "<nil>":
                                        existing['snmp_data_by_ip'][ip][key] = value

                    # Update other fields if they're more complete
                    for field in ['vendor', 'device_type', 'model', 'serial_number', 'os_version', 'sys_name']:
                        if device.get(field) and (not existing.get(field) or existing.get(field) == "<nil>"):
                            existing[field] = device[field]

    return device_map, all_sessions


def create_aggregated_json(devices, sessions, output_path):
    """Create the aggregated JSON file with properly named device IDs."""
    # Convert device map back to the expected format
    devices_dict = {}
    for unique_key, device in devices.items():
        # ✅ FIX: Use the clean device ID (remove any prefixes)
        device_id = device.get('id', unique_key)

        # ✅ ADDITIONAL CLEANUP: Remove any accidental prefixes
        if device_id.startswith('hostname_'):
            device_id = device_id.replace('hostname_', '')
            device['id'] = device_id
        elif device_id.startswith('ip_') and device.get('sys_name'):
            sys_name = device['sys_name']
            if sys_name and sys_name != device.get('primary_ip', '') and not sys_name.startswith('ip_'):
                device_id = sys_name
                device['id'] = device_id

        devices_dict[device_id] = device

        # Clean up the source_files field as it's not in the original format
        if 'source_files' in device:
            del device['source_files']

    # Calculate statistics
    stats = calculate_statistics(devices, sessions)

    # Create the aggregated structure
    aggregated = {
        "version": "1.0.0",
        "last_updated": datetime.now().isoformat(),
        "total_devices": len(devices),
        "devices": devices_dict,
        "sessions": sessions,
        "statistics": stats,
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

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(aggregated, f, indent=2, ensure_ascii=False)

    print(f"Aggregated JSON saved to: {output_path}")

    # ✅ ENHANCEMENT: Report on hostname improvements
    hostname_count = sum(1 for device_id in devices_dict.keys()
                         if not device_id.startswith('ip_') and not device_id.startswith('hostname_'))
    ip_count = sum(1 for device_id in devices_dict.keys() if device_id.startswith('ip_'))
    prefix_count = sum(1 for device_id in devices_dict.keys() if device_id.startswith('hostname_'))

    print(f"Device naming: {hostname_count} clean hostnames, {ip_count} IP-based IDs, {prefix_count} with prefixes")

    if prefix_count > 0:
        print("⚠️  Warning: Some devices still have 'hostname_' prefixes - check the logic above")

    return aggregated

def calculate_statistics(devices, sessions):
    """Calculate aggregate statistics."""
    stats = {
        'total_devices': len(devices),
        'total_sessions': len(sessions),
        'vendor_breakdown': defaultdict(int),
        'type_breakdown': defaultdict(int),
        'devices_per_subnet': defaultdict(int)
    }

    confidence_scores = []
    first_seen_dates = []
    last_seen_dates = []

    for device in devices.values():
        # Vendor breakdown
        vendor = device.get('vendor', 'unknown')
        stats['vendor_breakdown'][vendor] += 1

        # Device type breakdown
        device_type = device.get('device_type', 'unknown')
        if device_type:
            stats['type_breakdown'][device_type] += 1

        # Subnet calculation (assuming /24)
        primary_ip = device.get('primary_ip', '')
        if primary_ip:
            subnet = '.'.join(primary_ip.split('.')[:-1]) + '.0/24'
            stats['devices_per_subnet'][subnet] += 1

        # Confidence scores
        if device.get('confidence_score'):
            confidence_scores.append(device['confidence_score'])

        # Date tracking
        if device.get('first_seen'):
            first_seen_dates.append(device['first_seen'])
        if device.get('last_seen'):
            last_seen_dates.append(device['last_seen'])

    # Convert defaultdicts to regular dicts
    stats['vendor_breakdown'] = dict(stats['vendor_breakdown'])
    stats['type_breakdown'] = dict(stats['type_breakdown'])
    stats['devices_per_subnet'] = dict(stats['devices_per_subnet'])

    # Calculate averages and extremes
    if confidence_scores:
        stats['avg_confidence'] = sum(confidence_scores) / len(confidence_scores)

    if first_seen_dates:
        stats['oldest_device'] = min(first_seen_dates)

    if last_seen_dates:
        stats['last_scan_date'] = max(last_seen_dates)

    stats['error_stats'] = {}

    return stats


def create_aggregated_json(devices, sessions, output_path):
    """Create the aggregated JSON file."""
    # Convert device map back to the expected format
    devices_dict = {}
    for unique_key, device in devices.items():
        # Use the original device ID format or create a new one
        device_id = device.get('id', f"host_{device.get('sys_name', unique_key)}")
        devices_dict[device_id] = device

        # Clean up the source_files field as it's not in the original format
        if 'source_files' in device:
            del device['source_files']

    # Calculate statistics
    stats = calculate_statistics(devices, sessions)

    # Create the aggregated structure
    aggregated = {
        "version": "1.0.0",
        "last_updated": datetime.now().isoformat(),
        "total_devices": len(devices),
        "devices": devices_dict,
        "sessions": sessions,
        "statistics": stats,
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

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(aggregated, f, indent=2, ensure_ascii=False)

    print(f"Aggregated JSON saved to: {output_path}")
    return aggregated


def create_csv_export(devices, output_path):
    """Create CSV export with device information including sysdesc."""
    fieldnames = [
        'device_id', 'primary_ip', 'sys_name', 'vendor', 'device_type', 'model',
        'serial_number', 'os_version', 'sys_descr', 'first_seen', 'last_seen',
        'scan_count', 'confidence_score', 'detection_method', 'all_ips',
        'snmp_sys_descr', 'snmp_sys_name', 'printer_status', 'zebra_status'
    ]

    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for device_id, device in devices.items():
            # Extract SNMP data
            snmp_data = {}
            if 'snmp_data_by_ip' in device:
                for ip, data in device['snmp_data_by_ip'].items():
                    snmp_data.update(data)

            row = {
                'device_id': device_id,
                'primary_ip': device.get('primary_ip', ''),
                'sys_name': device.get('sys_name', ''),
                'vendor': device.get('vendor', ''),
                'device_type': device.get('device_type', ''),
                'model': device.get('model', ''),
                'serial_number': device.get('serial_number', ''),
                'os_version': device.get('os_version', ''),
                'sys_descr': device.get('sys_descr', ''),
                'first_seen': device.get('first_seen', ''),
                'last_seen': device.get('last_seen', ''),
                'scan_count': device.get('scan_count', 0),
                'confidence_score': device.get('confidence_score', 0),
                'detection_method': device.get('detection_method', ''),
                'all_ips': ','.join(device.get('all_ips', [])),
                'snmp_sys_descr': snmp_data.get('1.3.6.1.2.1.1.1.0', ''),
                'snmp_sys_name': snmp_data.get('1.3.6.1.2.1.1.5.0', ''),
                'printer_status': snmp_data.get('Printer Status', ''),
                'zebra_status': snmp_data.get('Zebra Status', '')
            }

            writer.writerow(row)

    print(f"CSV export saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Aggregate and deduplicate network device scan results')
    parser.add_argument('input_folder', help='Folder containing JSON scan result files')
    parser.add_argument('-o', '--output', default='aggregated_scan_results',
                        help='Output filename prefix (default: aggregated_scan_results)')

    args = parser.parse_args()

    if not os.path.isdir(args.input_folder):
        print(f"Error: {args.input_folder} is not a valid directory")
        return

    print(f"Processing JSON files in: {args.input_folder}")

    # Load all JSON files
    all_data = load_json_files(args.input_folder)

    if not all_data:
        print("No JSON files found or loaded successfully")
        return

    print(f"Loaded {len(all_data)} JSON files")

    # Deduplicate devices and aggregate sessions
    devices, sessions = deduplicate_devices(all_data)
    print(f"Found {len(devices)} unique devices across {len(sessions)} total sessions")

    # Create output files
    json_output = f"{args.output}.json"
    csv_output = f"{args.output}.csv"

    # Create aggregated JSON
    aggregated_data = create_aggregated_json(devices, sessions, json_output)

    # Create CSV export
    create_csv_export(devices, csv_output)

    print(f"\nSummary:")
    print(f"- Total unique devices: {len(devices)}")
    print(f"- Total sessions: {len(sessions)}")
    print(f"- Vendor breakdown: {aggregated_data['statistics']['vendor_breakdown']}")
    print(f"- Device type breakdown: {aggregated_data['statistics']['type_breakdown']}")


if __name__ == "__main__":
    main()