#!/usr/bin/env python3
"""
Enhanced Aggregate Report to CSV Converter with Vendor Fingerprints
Converts aggregate network device reports to CSV with enriched vendor data
"""

import json
import csv
import sys
from pathlib import Path
import argparse
import yaml


class VendorFingerprinter:
    """Load and use vendor fingerprint data for device enrichment"""

    def __init__(self, config_path="config/vendor_fingerprints.yaml"):
        self.vendors = {}
        self.load_fingerprints(config_path)

    def load_fingerprints(self, config_path):
        """Load vendor fingerprint configuration"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            self.vendors = config.get('vendors', {})
            self.common_oids = config.get('common_oids', {})
            self.generic_oids = config.get('generic_oids', [])
            self.detection_rules = config.get('detection_rules', {})

            print(f"✓ Loaded fingerprints for {len(self.vendors)} vendors from {config_path}")

        except FileNotFoundError:
            print(f"Warning: Fingerprint file not found at {config_path}")
            print("Continuing without vendor enrichment...")
        except Exception as e:
            print(f"Warning: Error loading fingerprint file: {e}")
            print("Continuing without vendor enrichment...")

    def get_vendor_info(self, vendor_key):
        """Get detailed vendor information"""
        if vendor_key in self.vendors:
            vendor_data = self.vendors[vendor_key]
            return {
                'vendor_display_name': vendor_data.get('display_name', vendor_key),
                'vendor_enterprise_oid': vendor_data.get('enterprise_oid', ''),
                'vendor_device_types': '; '.join(vendor_data.get('device_types', [])),
                'vendor_detection_patterns': '; '.join(vendor_data.get('detection_patterns', [])),
                'vendor_exclusion_patterns': '; '.join(vendor_data.get('exclusion_patterns', [])),
                'vendor_fingerprint_oids_count': len(vendor_data.get('fingerprint_oids', []))
            }
        return {
            'vendor_display_name': vendor_key or 'Unknown',
            'vendor_enterprise_oid': '',
            'vendor_device_types': '',
            'vendor_detection_patterns': '',
            'vendor_exclusion_patterns': '',
            'vendor_fingerprint_oids_count': 0
        }

    def analyze_snmp_coverage(self, snmp_data, vendor_key):
        """Analyze SNMP data coverage against vendor fingerprints"""
        if not vendor_key or vendor_key not in self.vendors:
            return {
                'fingerprint_oids_present': 0,
                'fingerprint_oids_total': 0,
                'fingerprint_coverage_percent': 0,
                'definitive_oids_present': 0,
                'common_oids_present': 0
            }

        vendor_data = self.vendors[vendor_key]
        fingerprint_oids = vendor_data.get('fingerprint_oids', [])

        # Check fingerprint OID coverage
        fingerprint_present = 0
        definitive_present = 0

        for oid_config in fingerprint_oids:
            oid_name = oid_config.get('name', '')
            if oid_name in snmp_data:
                fingerprint_present += 1
                if oid_config.get('definitive', False):
                    definitive_present += 1

        # Check common OIDs
        common_present = 0
        for common_oid_name in self.common_oids.keys():
            if common_oid_name.replace('_', ' ').title() in snmp_data:
                common_present += 1

        coverage_percent = (fingerprint_present / len(fingerprint_oids) * 100) if fingerprint_oids else 0

        return {
            'fingerprint_oids_present': fingerprint_present,
            'fingerprint_oids_total': len(fingerprint_oids),
            'fingerprint_coverage_percent': round(coverage_percent, 1),
            'definitive_oids_present': definitive_present,
            'common_oids_present': common_present
        }


def flatten_snmp_data(snmp_data):
    """Flatten SNMP data dictionary into individual columns"""
    flattened = {}
    if isinstance(snmp_data, dict):
        for key, value in snmp_data.items():
            # Clean up the key name for CSV column
            clean_key = f"snmp_{key.replace('.', '_').replace(' ', '_').lower()}"
            flattened[clean_key] = str(value) if value is not None else ""
    return flattened


def flatten_interfaces(interfaces):
    """Flatten interfaces data into summary columns"""
    if not interfaces:
        return {
            'interface_count': 0,
            'interface_types': '',
            'interface_ips': '',
            'interface_names': '',
            'management_ips': '',
            'data_ips': ''
        }

    interface_types = []
    interface_ips = []
    interface_names = []
    management_ips = []
    data_ips = []

    for interface_data in interfaces.values():
        if isinstance(interface_data, dict):
            interface_type = interface_data.get('type', '')
            ip_address = interface_data.get('ip_address', '')

            if interface_type and interface_type not in interface_types:
                interface_types.append(interface_type)
            if ip_address:
                interface_ips.append(ip_address)
                if interface_type == 'management':
                    management_ips.append(ip_address)
                elif interface_type == 'data':
                    data_ips.append(ip_address)
            if 'name' in interface_data:
                interface_names.append(interface_data['name'])

    return {
        'interface_count': len(interfaces),
        'interface_types': '; '.join(interface_types),
        'interface_ips': '; '.join(interface_ips),
        'interface_names': '; '.join(interface_names),
        'management_ips': '; '.join(management_ips),
        'data_ips': '; '.join(data_ips)
    }


def convert_devices_to_csv(devices_data, output_file, fingerprinter=None):
    """Convert devices section to CSV with vendor enrichment"""
    print(f"  Processing {len(devices_data)} devices...")
    rows = []
    all_fieldnames = set()

    # First pass: collect all possible fieldnames
    print("  Analyzing all device fields...")
    for device_id, device_data in devices_data.items():
        if isinstance(device_data, dict):
            # Base fields
            base_fields = {
                'device_id', 'primary_ip', 'all_ips', 'mac_addresses', 'vendor',
                'device_type', 'model', 'serial_number', 'os_version', 'sys_descr',
                'sys_name', 'first_seen', 'last_seen', 'scan_count', 'last_scan_id',
                'identity_method', 'identity_confidence', 'confidence_score', 'detection_method'
            }
            all_fieldnames.update(base_fields)

            # Vendor enrichment fields
            if fingerprinter:
                vendor_fields = {
                    'vendor_display_name', 'vendor_enterprise_oid', 'vendor_device_types',
                    'vendor_detection_patterns', 'vendor_exclusion_patterns', 'vendor_fingerprint_oids_count',
                    'fingerprint_oids_present', 'fingerprint_oids_total', 'fingerprint_coverage_percent',
                    'definitive_oids_present', 'common_oids_present'
                }
                all_fieldnames.update(vendor_fields)

            # Interface fields
            interfaces = device_data.get('interfaces', {})
            interface_fields = flatten_interfaces(interfaces)
            all_fieldnames.update(interface_fields.keys())

            # SNMP fields from all IPs
            snmp_data_by_ip = device_data.get('snmp_data_by_ip', {})
            for ip, snmp_data in snmp_data_by_ip.items():
                snmp_fields = flatten_snmp_data(snmp_data)
                all_fieldnames.update(snmp_fields.keys())

    # Convert to sorted list for consistent column order
    fieldnames = sorted(list(all_fieldnames))
    print(f"  Found {len(fieldnames)} total columns")

    # Track enrichment stats
    enriched_devices = 0
    devices_with_snmp = 0
    devices_with_sysdesc = 0

    # Second pass: build rows with all fields
    print("  Building device records with vendor enrichment...")
    for device_id, device_data in devices_data.items():
        if isinstance(device_data, dict):
            # Initialize row with all fields as empty
            row = {field: '' for field in fieldnames}

            vendor_key = device_data.get('vendor', '')

            # Fill in base device data
            row.update({
                'device_id': device_id,
                'primary_ip': device_data.get('primary_ip', ''),
                'all_ips': '; '.join(device_data.get('all_ips', [])),
                'mac_addresses': '; '.join(device_data.get('mac_addresses', [])),
                'vendor': vendor_key,
                'device_type': device_data.get('device_type', ''),
                'model': device_data.get('model', ''),
                'serial_number': device_data.get('serial_number', ''),
                'os_version': device_data.get('os_version', ''),
                'sys_descr': device_data.get('sys_descr', ''),
                'sys_name': device_data.get('sys_name', ''),
                'first_seen': device_data.get('first_seen', ''),
                'last_seen': device_data.get('last_seen', ''),
                'scan_count': device_data.get('scan_count', 0),
                'last_scan_id': device_data.get('last_scan_id', ''),
                'identity_method': device_data.get('identity_method', ''),
                'identity_confidence': device_data.get('identity_confidence', 0),
                'confidence_score': device_data.get('confidence_score', 0),
                'detection_method': device_data.get('detection_method', '')
            })

            # Count devices with sys_descr
            if device_data.get('sys_descr'):
                devices_with_sysdesc += 1

            # Add vendor enrichment data
            if fingerprinter and vendor_key:
                vendor_info = fingerprinter.get_vendor_info(vendor_key)
                row.update(vendor_info)
                enriched_devices += 1

            # Add interface information
            interfaces = device_data.get('interfaces', {})
            row.update(flatten_interfaces(interfaces))

            # Add SNMP data from all IPs
            snmp_data_by_ip = device_data.get('snmp_data_by_ip', {})
            all_snmp_data = {}

            for ip, snmp_data in snmp_data_by_ip.items():
                for key, value in snmp_data.items():
                    # Use the first occurrence of each SNMP key
                    if key not in all_snmp_data:
                        all_snmp_data[key] = value

            if all_snmp_data:
                devices_with_snmp += 1
                row.update(flatten_snmp_data(all_snmp_data))

                # Add SNMP coverage analysis
                if fingerprinter and vendor_key:
                    coverage_info = fingerprinter.analyze_snmp_coverage(all_snmp_data, vendor_key)
                    row.update(coverage_info)

            rows.append(row)

    if rows:
        print(f"  Writing CSV file...")
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"✓ Devices CSV: {len(rows)} devices written to '{output_file}'")
        print(f"  Columns: {len(fieldnames)}")
        print(f"  Devices with sys_descr: {devices_with_sysdesc} ({devices_with_sysdesc / len(rows) * 100:.1f}%)")
        print(f"  Devices with SNMP data: {devices_with_snmp} ({devices_with_snmp / len(rows) * 100:.1f}%)")
        if fingerprinter:
            print(f"  Vendor-enriched devices: {enriched_devices} ({enriched_devices / len(rows) * 100:.1f}%)")
        return True
    return False


def convert_sessions_to_csv(sessions_data, output_file, fingerprinter=None):
    """Convert sessions section to CSV with vendor enrichment"""
    print(f"  Processing {len(sessions_data)} sessions...")
    rows = []
    all_fieldnames = set()

    # First pass: collect all possible fieldnames
    print("  Analyzing all session fields...")
    for session in sessions_data:
        if isinstance(session, dict):
            # Base session fields
            base_fields = {
                'session_id', 'session_timestamp', 'target_ip', 'scan_type',
                'devices_found', 'new_devices', 'updated_devices', 'duration', 'source_file'
            }
            all_fieldnames.update(base_fields)

            # Result fields
            results = session.get('results', [])
            if results:
                result_fields = {
                    'result_ip_address', 'result_vendor', 'result_device_type', 'result_model',
                    'result_serial_number', 'result_os_version', 'result_sys_descr', 'result_sys_name',
                    'result_confidence_score', 'result_detection_method', 'result_scan_timestamp'
                }
                all_fieldnames.update(result_fields)

                # Vendor enrichment fields for results
                if fingerprinter:
                    vendor_fields = {
                        'result_vendor_display_name', 'result_vendor_enterprise_oid',
                        'result_vendor_device_types', 'result_fingerprint_coverage_percent'
                    }
                    all_fieldnames.update(vendor_fields)

                # SNMP fields from results
                for result in results:
                    snmp_data = result.get('snmp_data', {})
                    snmp_fields = flatten_snmp_data(snmp_data)
                    all_fieldnames.update(snmp_fields.keys())

    # Convert to sorted list
    fieldnames = sorted(list(all_fieldnames))
    print(f"  Found {len(fieldnames)} total columns")

    # Second pass: build rows
    print("  Building session records...")
    for session in sessions_data:
        if isinstance(session, dict):
            base_info = {
                'session_id': session.get('id', ''),
                'session_timestamp': session.get('timestamp', ''),
                'target_ip': session.get('target_ip', ''),
                'scan_type': session.get('scan_type', ''),
                'devices_found': session.get('devices_found', 0),
                'new_devices': session.get('new_devices', 0),
                'updated_devices': session.get('updated_devices', 0),
                'duration': session.get('duration', ''),
                'source_file': session.get('source_file', '')
            }

            results = session.get('results', [])
            if results:
                for result in results:
                    # Initialize row with all fields as empty
                    row = {field: '' for field in fieldnames}
                    row.update(base_info)

                    vendor_key = result.get('vendor', '')

                    row.update({
                        'result_ip_address': result.get('ip_address', ''),
                        'result_vendor': vendor_key,
                        'result_device_type': result.get('device_type', ''),
                        'result_model': result.get('model', ''),
                        'result_serial_number': result.get('serial_number', ''),
                        'result_os_version': result.get('os_version', ''),
                        'result_sys_descr': result.get('sys_descr', ''),
                        'result_sys_name': result.get('sys_name', ''),
                        'result_confidence_score': result.get('confidence_score', 0),
                        'result_detection_method': result.get('detection_method', ''),
                        'result_scan_timestamp': result.get('scan_timestamp', '')
                    })

                    # Add vendor enrichment for result
                    if fingerprinter and vendor_key:
                        vendor_info = fingerprinter.get_vendor_info(vendor_key)
                        row['result_vendor_display_name'] = vendor_info['vendor_display_name']
                        row['result_vendor_enterprise_oid'] = vendor_info['vendor_enterprise_oid']
                        row['result_vendor_device_types'] = vendor_info['vendor_device_types']

                        # Add SNMP coverage for this result
                        snmp_data = result.get('snmp_data', {})
                        if snmp_data:
                            coverage_info = fingerprinter.analyze_snmp_coverage(snmp_data, vendor_key)
                            row['result_fingerprint_coverage_percent'] = coverage_info['fingerprint_coverage_percent']

                    # Add SNMP data from the result
                    snmp_data = result.get('snmp_data', {})
                    row.update(flatten_snmp_data(snmp_data))

                    rows.append(row)
            else:
                # Session with no results
                row = {field: '' for field in fieldnames}
                row.update(base_info)
                rows.append(row)

    if rows:
        print(f"  Writing CSV file...")
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"✓ Sessions CSV: {len(rows)} session results written to '{output_file}'")
        print(f"  Columns: {len(fieldnames)}")
        return True
    return False


def convert_statistics_to_csv(statistics_data, output_file, fingerprinter=None):
    """Convert statistics to a summary CSV with vendor enrichment"""
    rows = []

    # Vendor breakdown with enrichment
    vendor_breakdown = statistics_data.get('vendor_breakdown', {})
    for vendor, count in vendor_breakdown.items():
        row = {
            'category': 'vendor',
            'name': vendor if vendor else 'unknown',
            'count': count,
            'percentage': round((count / statistics_data.get('total_devices', 1)) * 100, 2)
        }

        # Add vendor enrichment
        if fingerprinter and vendor:
            vendor_info = fingerprinter.get_vendor_info(vendor)
            row.update({
                'display_name': vendor_info['vendor_display_name'],
                'enterprise_oid': vendor_info['vendor_enterprise_oid'],
                'supported_device_types': vendor_info['vendor_device_types'],
                'fingerprint_oids_available': vendor_info['vendor_fingerprint_oids_count']
            })
        else:
            row.update({
                'display_name': vendor if vendor else 'Unknown',
                'enterprise_oid': '',
                'supported_device_types': '',
                'fingerprint_oids_available': 0
            })

        rows.append(row)

    # Device type breakdown
    type_breakdown = statistics_data.get('type_breakdown', {})
    for device_type, count in type_breakdown.items():
        rows.append({
            'category': 'device_type',
            'name': device_type,
            'count': count,
            'percentage': round((count / statistics_data.get('total_devices', 1)) * 100, 2),
            'display_name': device_type.replace('_', ' ').title(),
            'enterprise_oid': '',
            'supported_device_types': '',
            'fingerprint_oids_available': 0
        })

    # Subnet breakdown (top 20)
    devices_per_subnet = statistics_data.get('devices_per_subnet', {})
    sorted_subnets = sorted(devices_per_subnet.items(), key=lambda x: x[1], reverse=True)[:20]
    for subnet, count in sorted_subnets:
        rows.append({
            'category': 'subnet',
            'name': subnet,
            'count': count,
            'percentage': round((count / statistics_data.get('total_devices', 1)) * 100, 2),
            'display_name': subnet,
            'enterprise_oid': '',
            'supported_device_types': '',
            'fingerprint_oids_available': 0
        })

    if rows:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['category', 'name', 'count', 'percentage', 'display_name',
                          'enterprise_oid', 'supported_device_types', 'fingerprint_oids_available']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"✓ Statistics CSV: {len(rows)} statistics written to '{output_file}'")
        return True
    return False


def convert_aggregate_report(input_file, output_prefix=None, config_path="config/vendor_fingerprints.yaml"):
    """Main conversion function for aggregate reports with vendor enrichment"""

    # Initialize vendor fingerprinter
    fingerprinter = VendorFingerprinter(config_path)

    # Read JSON file
    try:
        print(f"Reading aggregate report: {input_file}")
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{input_file}' not found.")
        return False
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in file '{input_file}': {e}")
        return False

    # Validate it's an aggregate report
    if not isinstance(data, dict):
        print("Error: Expected aggregate report format (top-level object)")
        return False

    required_sections = ['devices', 'sessions']
    missing_sections = [section for section in required_sections if section not in data]
    if missing_sections:
        print(f"Warning: Missing expected sections: {missing_sections}")

    # Generate output prefix if not provided
    if not output_prefix:
        input_path = Path(input_file)
        output_prefix = input_path.stem

    print(f"\nAggregate Report Summary:")
    print(f"  Version: {data.get('version', 'unknown')}")
    print(f"  Last Updated: {data.get('last_updated', 'unknown')}")
    print(f"  Total Devices: {data.get('total_devices', 0):,}")
    print(f"  Total Sessions: {len(data.get('sessions', []))}")

    success_count = 0

    # Convert devices with vendor enrichment
    if 'devices' in data:
        devices_output = f"{output_prefix}_devices_enriched.csv"
        if convert_devices_to_csv(data['devices'], devices_output, fingerprinter):
            success_count += 1

    # Convert sessions with vendor enrichment
    if 'sessions' in data:
        sessions_output = f"{output_prefix}_sessions_enriched.csv"
        if convert_sessions_to_csv(data['sessions'], sessions_output, fingerprinter):
            success_count += 1

    # Convert statistics with vendor enrichment
    if 'statistics' in data:
        stats_output = f"{output_prefix}_statistics_enriched.csv"
        if convert_statistics_to_csv(data['statistics'], stats_output, fingerprinter):
            success_count += 1

    print(f"\n✓ Conversion completed! Generated {success_count} enriched CSV files.")
    return success_count > 0


def main():
    parser = argparse.ArgumentParser(
        description='Convert aggregate network device reports to enriched CSV format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python enhanced_agg_to_csv.py testagg.json
  python enhanced_agg_to_csv.py report.json -o my_network
  python enhanced_agg_to_csv.py report.json --config custom_fingerprints.yaml

Output files:
  {prefix}_devices_enriched.csv     - Device inventory with vendor details
  {prefix}_sessions_enriched.csv    - Scan sessions with vendor analysis
  {prefix}_statistics_enriched.csv  - Statistics with vendor information
        """
    )

    parser.add_argument('input_file', help='Input aggregate report JSON file')
    parser.add_argument('-o', '--output-prefix', help='Output file prefix (default: input filename)')
    parser.add_argument('--config', default='config/vendor_fingerprints.yaml',
                        help='Path to vendor fingerprints YAML file')

    args = parser.parse_args()

    # Validate input file exists
    if not Path(args.input_file).exists():
        print(f"Error: Input file '{args.input_file}' does not exist.")
        sys.exit(1)

    # Convert the file
    success = convert_aggregate_report(args.input_file, args.output_prefix, args.config)

    if not success:
        sys.exit(1)
    else:
        print("\n🎉 All enriched CSV files generated successfully!")
        print("\nEnhanced data includes:")
        print("  ✓ Vendor display names and enterprise OIDs")
        print("  ✓ Supported device types per vendor")
        print("  ✓ SNMP fingerprint coverage analysis")
        print("  ✓ Detection pattern information")
        print("  ✓ Interface type breakdown")
        print("\nNext steps:")
        print("  - Open _devices_enriched.csv for complete enriched inventory")
        print("  - Use fingerprint coverage to identify devices needing better scanning")
        print("  - Analyze vendor distribution and device type patterns")


if __name__ == "__main__":
    main()