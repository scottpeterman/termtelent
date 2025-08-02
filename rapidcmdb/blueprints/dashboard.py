# blueprints/dashboard.py
"""
Dashboard Blueprint - Main overview and metrics with enhanced chart data
"""

from flask import Blueprint, render_template, jsonify, session
import sqlite3
from datetime import datetime, timedelta
import logging
from theme_manager_web import theme_manager

dashboard_bp = Blueprint('dashboard', __name__, template_folder='../templates')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Get database connection with row factory"""
    conn = sqlite3.connect('napalm_cmdb.db')
    conn.row_factory = sqlite3.Row
    return conn


def execute_query(query, params=None):
    """Execute query and return results with error handling"""
    conn = get_db_connection()
    try:
        if params:
            cursor = conn.execute(query, params)
        else:
            cursor = conn.execute(query)
        results = cursor.fetchall()
        return [dict(row) for row in results]
    except Exception as e:
        logger.error(f"Database error in query '{query[:50]}...': {e}")
        return []
    finally:
        conn.close()


@dashboard_bp.route('/')
def index():
    """Main dashboard view"""
    try:
        # Get device statistics
        device_stats = get_device_statistics()
        logger.info(f"Device stats: {device_stats}")

        # Get collection status
        collection_stats = get_collection_statistics()

        # Get collection age statistics (NEW)
        collection_age_stats = get_collection_age_statistics()

        # Get site distribution
        site_stats = get_site_statistics()

        # Get recent activities
        recent_activities = get_recent_activities()

        # Get health metrics (keeping for compatibility)
        health_metrics = get_health_metrics()

        # Get top alerts/issues
        alerts = get_system_alerts()

        return render_template('dashboard/index.html',
                               device_stats=device_stats,
                               collection_stats=collection_stats,
                               collection_age_stats=collection_age_stats,
                               site_stats=site_stats,
                               recent_activities=recent_activities,
                               health_metrics=health_metrics,
                               alerts=alerts)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        # Return with empty data to prevent template crashes
        return render_template('dashboard/index.html',
                               device_stats={'total': 0, 'vendors': [], 'roles': [], 'recent': 0},
                               collection_stats={'success_rate': 0, 'avg_duration': 0, 'last_collections': []},
                               collection_age_stats={'age_24h': 0, 'age_3d': 0, 'age_1w': 0, 'age_1m': 0},
                               site_stats=[],
                               recent_activities=[],
                               health_metrics={'avg_cpu': 0, 'avg_memory': 0, 'monitored_devices': 0},
                               alerts=[])


def get_device_statistics():
    """Get device count and status statistics with chart data"""
    try:
        # Total devices
        total_query = "SELECT COUNT(*) as total FROM devices WHERE is_active = 1"
        total_result = execute_query(total_query)
        total_devices = total_result[0]['total'] if total_result else 0

        # Devices by vendor (for chart)
        vendor_query = """
            SELECT 
                COALESCE(TRIM(vendor), 'Unknown') as vendor, 
                COUNT(*) as count 
            FROM devices 
            WHERE is_active = 1 
            GROUP BY vendor 
            ORDER BY count DESC
            LIMIT 10
        """
        vendor_results = execute_query(vendor_query)
        logger.info(f"Vendor data: {vendor_results}")

        # Devices by role (for chart)
        role_query = """
            SELECT 
                COALESCE(TRIM(device_role), 'unknown') as device_role, 
                COUNT(*) as count 
            FROM devices 
            WHERE is_active = 1 
            GROUP BY device_role 
            ORDER BY count DESC
        """
        role_results = execute_query(role_query)
        logger.info(f"Role data: {role_results}")

        # Recently added devices (last 7 days)
        recent_query = """
            SELECT COUNT(*) as count 
            FROM devices 
            WHERE is_active = 1 
            AND first_discovered >= datetime('now', '-7 days')
        """
        recent_result = execute_query(recent_query)
        recent_devices = recent_result[0]['count'] if recent_result else 0

        # Return formatted data
        device_stats = {
            'total': total_devices,
            'vendors': vendor_results,  # This is the key data for the chart
            'roles': role_results,  # This is the key data for the chart
            'recent': recent_devices
        }

        logger.info(f"Final device stats: {device_stats}")
        return device_stats

    except Exception as e:
        logger.error(f"Error getting device statistics: {e}")
        return {
            'total': 0,
            'vendors': [],
            'roles': [],
            'recent': 0
        }


def get_collection_statistics():
    """Get data collection statistics"""
    try:
        # Collection success rate (last 24 hours)
        success_query = """
            SELECT 
                COUNT(*) as total_collections,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_collections,
                AVG(collection_duration) as avg_duration
            FROM collection_runs 
            WHERE collection_time >= datetime('now', '-24 hours')
        """
        success_result = execute_query(success_query)

        if success_result and success_result[0]['total_collections'] > 0:
            total = success_result[0]['total_collections']
            successful = success_result[0]['successful_collections'] or 0
            success_rate = (successful / total) * 100 if total > 0 else 0
            avg_duration = success_result[0]['avg_duration'] or 0
        else:
            success_rate = 0
            avg_duration = 0
            total = 0
            successful = 0

        # Last collection times per device
        last_collection_query = """
            SELECT 
                d.device_name,
                cr.collection_time,
                cr.success
            FROM devices d
            LEFT JOIN (
                SELECT device_id, collection_time, success,
                       ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY collection_time DESC) as rn
                FROM collection_runs
            ) cr ON d.id = cr.device_id AND cr.rn = 1
            WHERE d.is_active = 1
            ORDER BY cr.collection_time DESC
            LIMIT 10
        """
        last_collections = execute_query(last_collection_query)

        return {
            'success_rate': round(success_rate, 1),
            'avg_duration': round(avg_duration or 0, 2),
            'total_runs': total,
            'successful_runs': successful,
            'last_collections': last_collections
        }
    except Exception as e:
        logger.error(f"Error getting collection statistics: {e}")
        return {
            'success_rate': 0,
            'avg_duration': 0,
            'total_runs': 0,
            'successful_runs': 0,
            'last_collections': []
        }


def get_collection_age_statistics():
    """Get device collection age statistics - NEW FUNCTION"""
    try:
        age_query = """
            SELECT 
                COUNT(CASE WHEN cr.last_collection >= datetime('now', '-1 day') THEN 1 END) as age_24h,
                COUNT(CASE WHEN cr.last_collection >= datetime('now', '-3 days') AND cr.last_collection < datetime('now', '-1 day') THEN 1 END) as age_3d,
                COUNT(CASE WHEN cr.last_collection >= datetime('now', '-7 days') AND cr.last_collection < datetime('now', '-3 days') THEN 1 END) as age_1w,
                COUNT(CASE WHEN cr.last_collection < datetime('now', '-7 days') OR cr.last_collection IS NULL THEN 1 END) as age_1m
            FROM devices d
            LEFT JOIN (
                SELECT device_id, MAX(collection_time) as last_collection
                FROM collection_runs
                GROUP BY device_id
            ) cr ON d.id = cr.device_id
            WHERE d.is_active = 1
        """
        result = execute_query(age_query)
        return result[0] if result else {'age_24h': 0, 'age_3d': 0, 'age_1w': 0, 'age_1m': 0}
    except Exception as e:
        logger.error(f"Error getting collection age statistics: {e}")
        return {'age_24h': 0, 'age_3d': 0, 'age_1w': 0, 'age_1m': 0}


def get_site_statistics():
    """Get device distribution by site"""
    try:
        site_query = """
            SELECT 
                site_code,
                COUNT(*) as device_count,
                COUNT(CASE WHEN device_role = 'core' THEN 1 END) as core_devices,
                COUNT(CASE WHEN device_role = 'access' THEN 1 END) as access_devices,
                COUNT(CASE WHEN device_role = 'distribution' THEN 1 END) as dist_devices
            FROM devices 
            WHERE is_active = 1 
            GROUP BY site_code 
            ORDER BY device_count DESC
        """
        return execute_query(site_query)
    except Exception as e:
        logger.error(f"Error getting site statistics: {e}")
        return []


def get_recent_activities():
    """Get recent system activities"""
    try:
        activities = []

        # Recent configuration changes
        config_changes_query = """
            SELECT 
                'config_change' as activity_type,
                d.device_name,
                cc.change_type,
                cc.change_size,
                cc.detected_at as timestamp,
                'Configuration ' || cc.change_type || ' (' || cc.change_size || ' lines)' as description
            FROM config_changes cc
            JOIN devices d ON cc.device_id = d.id
            WHERE cc.detected_at >= datetime('now', '-7 days')
            ORDER BY cc.detected_at DESC
            LIMIT 5
        """
        config_activities = execute_query(config_changes_query)

        # Recent device discoveries
        discovery_query = """
            SELECT 
                'device_discovery' as activity_type,
                device_name,
                vendor,
                model,
                first_discovered as timestamp,
                'New device discovered: ' || COALESCE(vendor, 'Unknown') || ' ' || COALESCE(model, 'Unknown') as description
            FROM devices 
            WHERE first_discovered >= datetime('now', '-7 days')
            ORDER BY first_discovered DESC
            LIMIT 5
        """
        discovery_activities = execute_query(discovery_query)

        # Recent collection runs
        collection_query = """
            SELECT 
                'collection_run' as activity_type,
                d.device_name,
                cr.success,
                cr.collection_time as timestamp,
                CASE WHEN cr.success = 1 THEN 'Successful data collection' ELSE 'Failed data collection' END as description
            FROM collection_runs cr
            JOIN devices d ON cr.device_id = d.id
            WHERE cr.collection_time >= datetime('now', '-24 hours')
            ORDER BY cr.collection_time DESC
            LIMIT 5
        """
        collection_activities = execute_query(collection_query)

        # Combine and sort all activities
        all_activities = config_activities + discovery_activities + collection_activities
        all_activities.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        return all_activities[:10]
    except Exception as e:
        logger.error(f"Error getting recent activities: {e}")
        return []


def get_health_metrics():
    """Get system health metrics"""
    try:
        # CPU and memory usage averages from latest environment data
        health_query = """
            SELECT 
                AVG(ed.cpu_usage) as avg_cpu,
                AVG(CASE 
                    WHEN ed.memory_total > 0 THEN (ed.memory_used * 100.0 / ed.memory_total) 
                    WHEN ed.memory_available > 0 THEN (ed.memory_used * 100.0 / (ed.memory_used + ed.memory_available))
                    ELSE NULL 
                END) as avg_memory,
                COUNT(DISTINCT ed.device_id) as monitored_devices
            FROM environment_data ed
            JOIN (
                SELECT device_id, MAX(created_at) as max_time
                FROM environment_data
                WHERE created_at >= datetime('now', '-24 hours')
                GROUP BY device_id
            ) latest ON ed.device_id = latest.device_id AND ed.created_at = latest.max_time
        """
        health_result = execute_query(health_query)

        if health_result and health_result[0]['monitored_devices'] > 0:
            health_data = health_result[0]
            return {
                'avg_cpu': round(health_data['avg_cpu'] or 0, 1),
                'avg_memory': round(health_data['avg_memory'] or 0, 1),
                'monitored_devices': health_data['monitored_devices']
            }
        else:
            return {'avg_cpu': 0, 'avg_memory': 0, 'monitored_devices': 0}
    except Exception as e:
        logger.error(f"Error getting health metrics: {e}")
        return {'avg_cpu': 0, 'avg_memory': 0, 'monitored_devices': 0}


def get_system_alerts():
    """Get system alerts and issues"""
    try:
        alerts = []

        # Check for devices not collected in 24 hours
        stale_devices_query = """
            SELECT COUNT(*) as count
            FROM devices d
            LEFT JOIN (
                SELECT device_id, MAX(collection_time) as last_collection
                FROM collection_runs
                GROUP BY device_id
            ) cr ON d.id = cr.device_id
            WHERE d.is_active = 1 
            AND (cr.last_collection IS NULL OR cr.last_collection < datetime('now', '-24 hours'))
        """
        stale_result = execute_query(stale_devices_query)
        if stale_result and stale_result[0]['count'] > 0:
            alerts.append({
                'type': 'warning',
                'title': 'Stale Data',
                'message': f"{stale_result[0]['count']} devices not collected in 24+ hours",
                'count': stale_result[0]['count']
            })

        # Check for high CPU usage
        high_cpu_query = """
            SELECT COUNT(*) as count
            FROM environment_data ed
            JOIN (
                SELECT device_id, MAX(created_at) as max_time
                FROM environment_data
                WHERE created_at >= datetime('now', '-24 hours')
                GROUP BY device_id
            ) latest ON ed.device_id = latest.device_id AND ed.created_at = latest.max_time
            WHERE ed.cpu_usage > 80
        """
        cpu_result = execute_query(high_cpu_query)
        if cpu_result and cpu_result[0]['count'] > 0:
            alerts.append({
                'type': 'danger',
                'title': 'High CPU Usage',
                'message': f"{cpu_result[0]['count']} devices with CPU > 80%",
                'count': cpu_result[0]['count']
            })

        # Check for recent collection failures
        failed_collections_query = """
            SELECT COUNT(*) as count
            FROM collection_runs
            WHERE collection_time >= datetime('now', '-24 hours')
            AND success = 0
        """
        failed_result = execute_query(failed_collections_query)
        if failed_result and failed_result[0]['count'] > 0:
            alerts.append({
                'type': 'warning',
                'title': 'Collection Failures',
                'message': f"{failed_result[0]['count']} failed collections in 24h",
                'count': failed_result[0]['count']
            })

        # Check for recent configuration changes
        recent_changes_query = """
            SELECT COUNT(*) as count
            FROM config_changes
            WHERE detected_at >= datetime('now', '-24 hours')
        """
        changes_result = execute_query(recent_changes_query)
        if changes_result and changes_result[0]['count'] > 0:
            alerts.append({
                'type': 'info',
                'title': 'Recent Changes',
                'message': f"{changes_result[0]['count']} configuration changes in 24h",
                'count': changes_result[0]['count']
            })

        return alerts
    except Exception as e:
        logger.error(f"Error getting system alerts: {e}")
        return []


# API endpoints for AJAX updates
@dashboard_bp.route('/api/metrics')
def api_metrics():
    """API endpoint for dashboard metrics"""
    try:
        data = {
            'device_stats': get_device_statistics(),
            'collection_stats': get_collection_statistics(),
            'collection_age_stats': get_collection_age_statistics(),
            'health_metrics': get_health_metrics(),
            'timestamp': datetime.now().isoformat()
        }
        return jsonify(data)
    except Exception as e:
        logger.error(f"API metrics error: {e}")
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/collection-age')
def api_collection_age():
    """API endpoint for collection age statistics - NEW ENDPOINT"""
    try:
        age_stats = get_collection_age_statistics()
        return jsonify({'collection_age': age_stats, 'timestamp': datetime.now().isoformat()})
    except Exception as e:
        logger.error(f"API collection age error: {e}")
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/alerts')
def api_alerts():
    """API endpoint for system alerts"""
    try:
        alerts = get_system_alerts()
        return jsonify({'alerts': alerts, 'timestamp': datetime.now().isoformat()})
    except Exception as e:
        logger.error(f"API alerts error: {e}")
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/activities')
def api_activities():
    """API endpoint for recent activities"""
    try:
        activities = get_recent_activities()
        return jsonify({'activities': activities, 'timestamp': datetime.now().isoformat()})
    except Exception as e:
        logger.error(f"API activities error: {e}")
        return jsonify({'error': str(e)}), 500


# Debug endpoint to populate sample data for testing
@dashboard_bp.route('/api/debug/sample-data')
def debug_sample_data():
    """Generate sample data for testing charts (remove in production)"""
    try:
        sample_data = {
            'device_stats': {
                'total': 126,
                'vendors': [
                    {'vendor': 'Cisco', 'count': 45},
                    {'vendor': 'Arista', 'count': 28},
                    {'vendor': 'Juniper', 'count': 15},
                    {'vendor': 'HP', 'count': 12},
                    {'vendor': 'Fortinet', 'count': 8},
                    {'vendor': 'Palo Alto', 'count': 18}
                ],
                'roles': [
                    {'device_role': 'access', 'count': 68},
                    {'device_role': 'core', 'count': 12},
                    {'device_role': 'distribution', 'count': 18},
                    {'device_role': 'firewall', 'count': 8},
                    {'device_role': 'router', 'count': 6},
                    {'device_role': 'switch', 'count': 14}
                ],
                'recent': 5
            },
            'collection_stats': {
                'success_rate': 98.5,
                'avg_duration': 12.3
            },
            'collection_age_stats': {
                'age_24h': 85,
                'age_3d': 28,
                'age_1w': 8,
                'age_1m': 5
            },
            'health_metrics': {
                'avg_cpu': 14.2,
                'avg_memory': 21.8,
                'monitored_devices': 126
            }
        }
        return jsonify(sample_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Function to insert sample data for testing
def insert_sample_data():
    """Insert sample data for testing (call this manually if needed)"""
    conn = get_db_connection()
    try:
        # Sample devices
        sample_devices = [
            ('cisco-1', 'Cisco', 'C9300-48T', 'FCW2140L0AK', 'access', 'FRC'),
            ('arista-1', 'Arista', '7050QX-32', 'JPE14070259', 'core', 'USC'),
            ('juniper-1', 'Juniper', 'EX4300-48T', 'PE3714AF0123', 'distribution', 'LAX'),
            ('hp-1', 'HP', 'ProCurve 2920', 'SG99KX0123', 'access', 'BUR'),
            ('fortinet-1', 'Fortinet', 'FortiGate-100F', 'FG100F3G19000123', 'firewall', 'FRC')
        ]

        for device in sample_devices:
            conn.execute("""
                INSERT OR IGNORE INTO devices 
                (device_name, vendor, model, serial_number, device_role, site_code, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, device)

        conn.commit()
        logger.info("Sample data inserted successfully")

    except Exception as e:
        logger.error(f"Error inserting sample data: {e}")
        conn.rollback()
    finally:
        conn.close()