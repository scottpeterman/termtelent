#!/usr/bin/env python3
"""
Uptime Analysis Blueprint - Device uptime reporting and analysis
Provides comprehensive uptime analytics for NAPALM-collected devices
"""

from flask import Blueprint, render_template, jsonify, request, send_file, flash, redirect, url_for
import sqlite3
from datetime import datetime, timedelta
import logging
from collections import defaultdict, Counter
import json
import tempfile
import csv
from typing import Dict, List, Tuple, Optional
import math

uptime_bp = Blueprint('uptime', __name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UptimeAnalyzer:
    """Analyzes device uptime data from NAPALM collections"""

    def __init__(self):
        # Uptime risk categories (in days)
        self.uptime_categories = {
            'recent': {'min': 0, 'max': 30, 'label': 'Recent', 'color': 'success'},
            'moderate': {'min': 30, 'max': 180, 'label': 'Moderate', 'color': 'warning'},
            'extended': {'min': 180, 'max': 365, 'label': 'Extended', 'color': 'info'},
            'excessive': {'min': 365, 'max': 1095, 'label': 'Excessive', 'color': 'danger'},
            'critical': {'min': 1095, 'max': float('inf'), 'label': 'Critical Risk', 'color': 'dark'}
        }

        # Maintenance recommendations
        self.maintenance_thresholds = {
            'immediate': 1095,  # 3+ years
            'urgent': 730,  # 2+ years
            'planned': 365,  # 1+ year
            'monitor': 180  # 6+ months
        }

    def seconds_to_days(self, seconds: float) -> float:
        """Convert seconds to days"""
        if seconds is None:
            return 0
        try:
            return float(seconds) / 86400.0  # 86400 seconds in a day
        except (ValueError, TypeError):
            return 0

    def format_uptime_duration(self, seconds: float) -> str:
        """Format uptime seconds into human-readable duration"""
        if not seconds:
            return "Unknown"

        try:
            total_seconds = float(seconds)
            days = int(total_seconds // 86400)
            hours = int((total_seconds % 86400) // 3600)
            minutes = int((total_seconds % 3600) // 60)

            if days > 365:
                years = days // 365
                remaining_days = days % 365
                return f"{years}y {remaining_days}d"
            elif days > 30:
                months = days // 30
                remaining_days = days % 30
                return f"{months}mo {remaining_days}d"
            elif days > 0:
                return f"{days}d {hours}h"
            else:
                return f"{hours}h {minutes}m"

        except (ValueError, TypeError):
            return "Unknown"

    def categorize_uptime(self, days: float) -> Dict:
        """Categorize uptime based on days"""
        for category, config in self.uptime_categories.items():
            if config['min'] <= days < config['max']:
                return {
                    'category': category,
                    'label': config['label'],
                    'color': config['color'],
                    'days': days
                }

        # Default to critical if beyond all categories
        return {
            'category': 'critical',
            'label': 'Critical Risk',
            'color': 'dark',
            'days': days
        }

    def get_maintenance_priority(self, days: float) -> Dict:
        """Determine maintenance priority based on uptime"""
        if days >= self.maintenance_thresholds['immediate']:
            return {'priority': 'immediate', 'level': 'CRITICAL', 'color': 'danger'}
        elif days >= self.maintenance_thresholds['urgent']:
            return {'priority': 'urgent', 'level': 'HIGH', 'color': 'warning'}
        elif days >= self.maintenance_thresholds['planned']:
            return {'priority': 'planned', 'level': 'MEDIUM', 'color': 'info'}
        elif days >= self.maintenance_thresholds['monitor']:
            return {'priority': 'monitor', 'level': 'LOW', 'color': 'secondary'}
        else:
            return {'priority': 'none', 'level': 'GOOD', 'color': 'success'}

    def analyze_uptime_data(self, conn: sqlite3.Connection) -> Dict:
        """Perform comprehensive uptime analysis"""
        query = """
        SELECT 
            d.id,
            d.device_name,
            d.hostname,
            d.vendor,
            d.model,
            d.device_role,
            d.site_code,
            d.uptime,
            di.ip_address as primary_ip,
            cr.collection_time as last_collection,
            cr.napalm_driver,
            CASE 
                WHEN d.uptime IS NOT NULL AND d.uptime > 0 THEN 'has_uptime'
                ELSE 'no_uptime'
            END as uptime_status
        FROM devices d
        LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
        LEFT JOIN (
            SELECT device_id, collection_time, napalm_driver,
                   ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY collection_time DESC) as rn
            FROM collection_runs
            WHERE success = 1
        ) cr ON d.id = cr.device_id AND cr.rn = 1
        WHERE d.is_active = 1
        ORDER BY d.uptime DESC NULLS LAST
        """

        cursor = conn.execute(query)
        devices = [dict(row) for row in cursor.fetchall()]

        # Process and categorize devices
        devices_with_uptime = []
        devices_without_uptime = []
        category_counts = defaultdict(int)
        vendor_stats = defaultdict(lambda: {'count': 0, 'total_uptime': 0, 'devices': []})
        role_stats = defaultdict(lambda: {'count': 0, 'total_uptime': 0, 'devices': []})
        site_stats = defaultdict(lambda: {'count': 0, 'total_uptime': 0, 'devices': []})
        maintenance_counts = defaultdict(int)

        for device in devices:
            uptime_seconds = device.get('uptime')

            if uptime_seconds and uptime_seconds > 0:
                uptime_days = self.seconds_to_days(uptime_seconds)
                uptime_category = self.categorize_uptime(uptime_days)
                maintenance_priority = self.get_maintenance_priority(uptime_days)

                device_info = {
                    **device,
                    'uptime_days': uptime_days,
                    'uptime_formatted': self.format_uptime_duration(uptime_seconds),
                    'uptime_category': uptime_category,
                    'maintenance_priority': maintenance_priority
                }

                devices_with_uptime.append(device_info)
                category_counts[uptime_category['category']] += 1
                maintenance_counts[maintenance_priority['priority']] += 1

                # Vendor statistics
                vendor = device.get('vendor', 'Unknown')
                vendor_stats[vendor]['count'] += 1
                vendor_stats[vendor]['total_uptime'] += uptime_days
                vendor_stats[vendor]['devices'].append(device_info)

                # Role statistics
                role = device.get('device_role', 'Unknown')
                role_stats[role]['count'] += 1
                role_stats[role]['total_uptime'] += uptime_days
                role_stats[role]['devices'].append(device_info)

                # Site statistics
                site = device.get('site_code', 'Unknown')
                site_stats[site]['count'] += 1
                site_stats[site]['total_uptime'] += uptime_days
                site_stats[site]['devices'].append(device_info)

            else:
                devices_without_uptime.append(device)

        # Calculate averages and sort
        for vendor_data in vendor_stats.values():
            if vendor_data['count'] > 0:
                vendor_data['avg_uptime'] = vendor_data['total_uptime'] / vendor_data['count']

        for role_data in role_stats.values():
            if role_data['count'] > 0:
                role_data['avg_uptime'] = role_data['total_uptime'] / role_data['count']

        for site_data in site_stats.values():
            if site_data['count'] > 0:
                site_data['avg_uptime'] = site_data['total_uptime'] / site_data['count']

        # Generate recommendations
        recommendations = self.generate_recommendations(devices_with_uptime, maintenance_counts)

        return {
            'devices_with_uptime': devices_with_uptime,
            'devices_without_uptime': devices_without_uptime,
            'total_devices': len(devices),
            'devices_with_uptime_count': len(devices_with_uptime),
            'devices_without_uptime_count': len(devices_without_uptime),
            'category_counts': dict(category_counts),
            'maintenance_counts': dict(maintenance_counts),
            'vendor_stats': dict(vendor_stats),
            'role_stats': dict(role_stats),
            'site_stats': dict(site_stats),
            'recommendations': recommendations,
            'analysis_timestamp': datetime.now().isoformat()
        }

    def generate_recommendations(self, devices: List[Dict], maintenance_counts: Dict) -> List[Dict]:
        """Generate uptime-based recommendations"""
        recommendations = []

        # Critical uptime devices
        critical_devices = [d for d in devices if d['maintenance_priority']['priority'] == 'immediate']
        if critical_devices:
            device_names = [d['device_name'] for d in critical_devices[:5]]  # Show first 5
            more_count = len(critical_devices) - 5

            recommendations.append({
                'level': 'CRITICAL',
                'title': f'{len(critical_devices)} devices require immediate reboot',
                'description': 'These devices have excessive uptime and pose critical compliance risks',
                'action': 'Schedule maintenance windows for device reboots',
                'affected_devices': device_names + ([f'and {more_count} more'] if more_count > 0 else []),
                'color': 'danger'
            })

        # High uptime devices
        high_devices = [d for d in devices if d['maintenance_priority']['priority'] == 'urgent']
        if high_devices:
            device_names = [d['device_name'] for d in high_devices[:7]]  # Show first 7
            more_count = len(high_devices) - 7

            recommendations.append({
                'level': 'HIGH',
                'title': f'{len(high_devices)} devices need planned maintenance',
                'description': 'These devices should be rebooted during next maintenance window',
                'action': 'Include in next scheduled maintenance cycle',
                'affected_devices': device_names + ([f'and {more_count} more'] if more_count > 0 else []),
                'color': 'warning'
            })

        # Vendor-specific recommendations
        vendor_recommendations = self.get_vendor_recommendations(devices)
        recommendations.extend(vendor_recommendations)

        return recommendations

    def get_vendor_recommendations(self, devices: List[Dict]) -> List[Dict]:
        """Generate vendor-specific uptime recommendations"""
        recommendations = []
        vendor_groups = defaultdict(list)

        for device in devices:
            if device['maintenance_priority']['priority'] in ['immediate', 'urgent']:
                vendor_groups[device['vendor']].append(device)

        for vendor, vendor_devices in vendor_groups.items():
            if len(vendor_devices) >= 3:  # Only recommend if 3+ devices from same vendor
                avg_uptime = sum(d['uptime_days'] for d in vendor_devices) / len(vendor_devices)

                recommendations.append({
                    'level': 'INFO',
                    'title': f'{vendor} devices showing high uptime patterns',
                    'description': f'{len(vendor_devices)} {vendor} devices averaging {avg_uptime:.0f} days uptime',
                    'action': f'Review {vendor} maintenance schedules and policies',
                    'affected_devices': [d['device_name'] for d in vendor_devices[:3]],
                    'color': 'info'
                })

        return recommendations


def get_db_connection():
    """Get database connection with row factory"""
    conn = sqlite3.connect('napalm_cmdb.db')
    conn.row_factory = sqlite3.Row
    return conn


@uptime_bp.route('/')
def uptime_analysis():
    """Main uptime analysis page"""
    try:
        analyzer = UptimeAnalyzer()
        conn = get_db_connection()

        analysis_data = analyzer.analyze_uptime_data(conn)
        conn.close()

        # Sort devices by uptime (highest first)
        analysis_data['devices_with_uptime'].sort(
            key=lambda x: x.get('uptime_days', 0),
            reverse=True
        )

        return render_template('uptime/analysis.html', analysis=analysis_data)

    except Exception as e:
        logger.error(f"Error in uptime analysis: {e}")
        import traceback
        logger.error(traceback.format_exc())
        flash(f'Error generating uptime analysis: {str(e)}', 'error')
        return redirect(url_for('dashboard.index'))


@uptime_bp.route('/api/uptime-data')
def api_uptime_data():
    """API endpoint for uptime data"""
    try:
        analyzer = UptimeAnalyzer()
        conn = get_db_connection()

        analysis_data = analyzer.analyze_uptime_data(conn)
        conn.close()

        # Clean data for JSON serialization
        def clean_for_json(obj):
            if isinstance(obj, sqlite3.Row):
                return dict(obj)
            elif isinstance(obj, dict):
                return {k: clean_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_for_json(item) for item in obj]
            else:
                return obj

        clean_data = clean_for_json(analysis_data)
        return jsonify(clean_data)

    except Exception as e:
        logger.error(f"Error in uptime API: {e}")
        return jsonify({'error': str(e)}), 500


@uptime_bp.route('/api/vendor/<vendor_name>')
def api_vendor_uptime(vendor_name):
    """API endpoint for vendor-specific uptime data"""
    try:
        analyzer = UptimeAnalyzer()
        conn = get_db_connection()

        query = """
        SELECT 
            d.id, d.device_name, d.hostname, d.vendor, d.model, 
            d.device_role, d.site_code, d.uptime,
            di.ip_address as primary_ip
        FROM devices d
        LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
        WHERE d.is_active = 1 AND d.vendor = ? AND d.uptime IS NOT NULL AND d.uptime > 0
        ORDER BY d.uptime DESC
        """

        cursor = conn.execute(query, (vendor_name,))
        devices = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Process devices
        processed_devices = []
        for device in devices:
            uptime_days = analyzer.seconds_to_days(device['uptime'])
            uptime_category = analyzer.categorize_uptime(uptime_days)
            maintenance_priority = analyzer.get_maintenance_priority(uptime_days)

            processed_devices.append({
                **device,
                'uptime_days': uptime_days,
                'uptime_formatted': analyzer.format_uptime_duration(device['uptime']),
                'uptime_category': uptime_category,
                'maintenance_priority': maintenance_priority
            })

        return jsonify({
            'vendor': vendor_name,
            'device_count': len(processed_devices),
            'devices': processed_devices,
            'avg_uptime_days': sum(d['uptime_days'] for d in processed_devices) / len(
                processed_devices) if processed_devices else 0
        })

    except Exception as e:
        logger.error(f"Error in vendor uptime API: {e}")
        return jsonify({'error': str(e)}), 500


@uptime_bp.route('/export/csv')
def export_uptime_csv():
    """Export uptime analysis to CSV"""
    try:
        analyzer = UptimeAnalyzer()
        conn = get_db_connection()

        analysis_data = analyzer.analyze_uptime_data(conn)
        conn.close()

        # Create temporary CSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            # Write header
            writer.writerow([
                'Device Name', 'Hostname', 'Vendor', 'Model', 'Role', 'Site',
                'Primary IP', 'Uptime (Days)', 'Uptime (Formatted)', 'Category',
                'Maintenance Priority', 'Last Collection', 'Platform'
            ])

            # Write device data
            for device in analysis_data['devices_with_uptime']:
                writer.writerow([
                    device.get('device_name', ''),
                    device.get('hostname', ''),
                    device.get('vendor', ''),
                    device.get('model', ''),
                    device.get('device_role', ''),
                    device.get('site_code', ''),
                    device.get('primary_ip', ''),
                    f"{device.get('uptime_days', 0):.1f}",
                    device.get('uptime_formatted', ''),
                    device.get('uptime_category', {}).get('label', ''),
                    device.get('maintenance_priority', {}).get('level', ''),
                    device.get('last_collection', ''),
                    device.get('napalm_driver', '')
                ])

            temp_path = f.name

        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'uptime_analysis_{timestamp}.csv'

        return send_file(temp_path, as_attachment=True, download_name=filename, mimetype='text/csv')

    except Exception as e:
        logger.error(f"Error exporting uptime CSV: {e}")
        flash(f'Error exporting CSV: {str(e)}', 'error')
        return redirect(url_for('uptime.uptime_analysis'))


@uptime_bp.route('/maintenance-report')
def maintenance_report():
    """Generate maintenance report based on uptime analysis"""
    try:
        analyzer = UptimeAnalyzer()
        conn = get_db_connection()

        analysis_data = analyzer.analyze_uptime_data(conn)
        conn.close()

        # Group devices by maintenance priority
        maintenance_groups = defaultdict(list)
        for device in analysis_data['devices_with_uptime']:
            priority = device['maintenance_priority']['priority']
            maintenance_groups[priority].append(device)

        # Sort each group by uptime (highest first)
        for priority_group in maintenance_groups.values():
            priority_group.sort(key=lambda x: x.get('uptime_days', 0), reverse=True)

        return render_template('uptime/maintenance_report.html',
                               maintenance_groups=dict(maintenance_groups),
                               analysis=analysis_data)

    except Exception as e:
        logger.error(f"Error in maintenance report: {e}")
        flash(f'Error generating maintenance report: {str(e)}', 'error')
        return redirect(url_for('uptime.uptime_analysis'))


@uptime_bp.route('/api/uptime-trends')
def api_uptime_trends():
    """API endpoint for uptime trend analysis"""
    try:
        conn = get_db_connection()

        # Get uptime trends over time (last 6 months of collections)
        query = """
        SELECT 
            d.vendor,
            d.device_role,
            d.site_code,
            AVG(d.uptime) as avg_uptime_seconds,
            COUNT(*) as device_count,
            DATE(cr.collection_time) as collection_date
        FROM devices d
        JOIN collection_runs cr ON d.id = cr.device_id
        WHERE d.is_active = 1 
        AND d.uptime IS NOT NULL 
        AND d.uptime > 0
        AND cr.collection_time >= datetime('now', '-6 months')
        AND cr.success = 1
        GROUP BY d.vendor, d.device_role, d.site_code, DATE(cr.collection_time)
        ORDER BY collection_date DESC
        """

        cursor = conn.execute(query)
        trends = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Convert to days and format for charts
        analyzer = UptimeAnalyzer()
        for trend in trends:
            trend['avg_uptime_days'] = analyzer.seconds_to_days(trend['avg_uptime_seconds'])
            trend['avg_uptime_formatted'] = analyzer.format_uptime_duration(trend['avg_uptime_seconds'])

        return jsonify({
            'trends': trends,
            'last_updated': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error in uptime trends API: {e}")
        return jsonify({'error': str(e)}), 500