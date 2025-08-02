# blueprints/devices.py
"""
Devices Blueprint - Device inventory and management
CORRECTED VERSION: Uses CTE methodology to prevent duplicate data
"""
import json

from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
import sqlite3
from datetime import datetime, timedelta

devices_bp = Blueprint('devices', __name__, template_folder='../templates')


def get_db_connection():
    """Get database connection with row factory"""
    conn = sqlite3.connect('napalm_cmdb.db')
    conn.row_factory = sqlite3.Row
    return conn


def execute_query(query, params=None):
    """Execute query and return results"""
    conn = get_db_connection()
    try:
        if params:
            cursor = conn.execute(query, params)
        else:
            cursor = conn.execute(query)
        results = cursor.fetchall()
        return [dict(row) for row in results]
    except Exception as e:
        print(f"Database error: {e}")
        return []
    finally:
        conn.close()


@devices_bp.route('/')
def list_devices():
    """List all devices with filtering and search"""
    try:
        # Get filter parameters
        search = request.args.get('search', '').strip()
        vendor_filter = request.args.get('vendor', '')
        role_filter = request.args.get('role', '')
        site_filter = request.args.get('site', '')
        status_filter = request.args.get('status', '')

        # Build query with filters using CTE for latest collection status
        base_query = """
            WITH latest_collections AS (
                SELECT 
                    device_id,
                    collection_time,
                    success,
                    ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY collection_time DESC) as rn
                FROM collection_runs
            )
            SELECT 
                d.id,
                d.device_name,
                d.hostname,
                d.vendor,
                d.model,
                d.serial_number,
                d.site_code,
                d.device_role,
                d.os_version,
                d.uptime,
                d.last_updated,
                di.ip_address as primary_ip,
                lc.collection_time as last_collection,
                lc.success as last_collection_success,
                CASE 
                    WHEN lc.collection_time >= datetime('now', '-24 hours') AND lc.success = 1 THEN 'online'
                    WHEN lc.collection_time >= datetime('now', '-24 hours') AND lc.success = 0 THEN 'error'
                    WHEN lc.collection_time < datetime('now', '-24 hours') THEN 'stale'
                    ELSE 'unknown'
                END as status
            FROM devices d
            LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
            LEFT JOIN latest_collections lc ON d.id = lc.device_id AND lc.rn = 1
            WHERE d.is_active = 1
        """

        params = []
        conditions = []

        if search:
            conditions.append("(d.device_name LIKE ? OR d.hostname LIKE ? OR di.ip_address LIKE ?)")
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param])

        if vendor_filter:
            conditions.append("d.vendor = ?")
            params.append(vendor_filter)

        if role_filter:
            conditions.append("d.device_role = ?")
            params.append(role_filter)

        if site_filter:
            conditions.append("d.site_code = ?")
            params.append(site_filter)

        if conditions:
            base_query += " AND " + " AND ".join(conditions)

        # Add having clause for status filter
        if status_filter:
            base_query += f"""
                HAVING status = '{status_filter}'
            """

        base_query += " ORDER BY d.device_name"

        devices = execute_query(base_query, params)

        # Get filter options
        vendors = execute_query("SELECT DISTINCT vendor FROM devices WHERE is_active = 1 ORDER BY vendor")
        roles = execute_query("SELECT DISTINCT device_role FROM devices WHERE is_active = 1 ORDER BY device_role")
        sites = execute_query("SELECT DISTINCT site_code FROM devices WHERE is_active = 1 ORDER BY site_code")

        # Get summary statistics
        total_devices = len(devices)
        online_devices = len([d for d in devices if d['status'] == 'online'])
        error_devices = len([d for d in devices if d['status'] == 'error'])
        stale_devices = len([d for d in devices if d['status'] == 'stale'])

        stats = {
            'total': total_devices,
            'online': online_devices,
            'error': error_devices,
            'stale': stale_devices,
            'offline': total_devices - online_devices - error_devices - stale_devices
        }

        return render_template('devices/list.html',
                               devices=devices,
                               vendors=[v['vendor'] for v in vendors],
                               roles=[r['device_role'] for r in roles],
                               sites=[s['site_code'] for s in sites],
                               current_filters={
                                   'search': search,
                                   'vendor': vendor_filter,
                                   'role': role_filter,
                                   'site': site_filter,
                                   'status': status_filter
                               },
                               stats=stats)
    except Exception as e:
        flash(f"Error loading devices: {str(e)}", 'error')
        return render_template('devices/list.html', devices=[], vendors=[], roles=[], sites=[], current_filters={},
                               stats={})


def parse_hardware_status(hardware_list):
    """Parse additional_data JSON to get real hardware status"""

    for hw in hardware_list:
        # Set defaults
        hw['actual_status'] = hw.get('status', 'unknown')
        hw['psu_capacity'] = None
        hw['psu_output'] = None

        # Parse JSON if available
        if hw.get('additional_data'):
            try:
                parsed = json.loads(hw['additional_data'])

                # Parse status for fans and PSUs
                if hw['component_type'] in ['fan', 'psu']:
                    json_status = parsed.get('status')
                    if json_status is True:
                        hw['actual_status'] = 'operational'
                    elif json_status is False:
                        hw['actual_status'] = 'failed'

                # Parse PSU-specific data
                if hw['component_type'] == 'psu':
                    hw['psu_capacity'] = parsed.get('capacity', -1)
                    hw['psu_output'] = parsed.get('output', -1)

            except (json.JSONDecodeError, TypeError) as e:
                print(f"Error parsing hardware JSON: {e}")
                # Keep original status as fallback

    return hardware_list

# Enhanced device_detail route for devices.py
@devices_bp.route('/detail/<device_name>')
def device_detail(device_name):
    """Show detailed device information with ARP and MAC address tables"""
    try:
        # Get device basic info
        device_query = """
            SELECT 
                d.*,
                di.ip_address as primary_ip,
                di.ip_type as primary_ip_type
            FROM devices d
            LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
            WHERE d.device_name = ? AND d.is_active = 1
        """
        device_result = execute_query(device_query, [device_name])

        if not device_result:
            flash(f"Device '{device_name}' not found", 'error')
            return redirect(url_for('devices.list_devices'))

        device = device_result[0]
        device_id = device['id']

        # Get all IP addresses
        ips_query = """
            SELECT ip_address, ip_type, interface_name, subnet_mask, vlan_id, is_primary
            FROM device_ips
            WHERE device_id = ?
            ORDER BY is_primary DESC, ip_type, ip_address
        """
        ips = execute_query(ips_query, [device_id])

        # Get latest interfaces using CTE
        interfaces_query = """
            WITH latest_successful_collection AS (
                SELECT 
                    device_id, 
                    id as collection_run_id,
                    collection_time,
                    ROW_NUMBER() OVER (ORDER BY collection_time DESC) as rn
                FROM collection_runs
                WHERE device_id = ? AND success = 1
            )
            SELECT 
                i.*,
                lsc.collection_time
            FROM interfaces i
            JOIN latest_successful_collection lsc ON i.collection_run_id = lsc.collection_run_id
            WHERE lsc.rn = 1
            ORDER BY 
                CASE i.interface_type 
                    WHEN 'Physical' THEN 1
                    WHEN 'PortChannel' THEN 2
                    WHEN 'VLAN' THEN 3
                    WHEN 'Loopback' THEN 4
                    ELSE 5
                END,
                i.interface_name
        """
        interfaces = execute_query(interfaces_query, [device_id])

        # Get latest environment data
        env_query = """
            WITH latest_environment AS (
                SELECT *,
                       ROW_NUMBER() OVER (ORDER BY created_at DESC) as rn
                FROM environment_data
                WHERE device_id = ?
            )
            SELECT *
            FROM latest_environment
            WHERE rn = 1
        """
        environment = execute_query(env_query, [device_id])
        environment = environment[0] if environment else None

        # Get collection history
        collection_query = """
            SELECT *
            FROM collection_runs
            WHERE device_id = ?
            ORDER BY collection_time DESC
            LIMIT 10
        """
        collections = execute_query(collection_query, [device_id])

        # Get LLDP neighbors from latest successful collection
        lldp_query = """
            WITH latest_successful_collection AS (
                SELECT 
                    device_id, 
                    id as collection_run_id,
                    collection_time,
                    ROW_NUMBER() OVER (ORDER BY collection_time DESC) as rn
                FROM collection_runs
                WHERE device_id = ? AND success = 1
            )
            SELECT 
                ln.*,
                lsc.collection_time
            FROM lldp_neighbors ln
            JOIN latest_successful_collection lsc ON ln.collection_run_id = lsc.collection_run_id
            WHERE lsc.rn = 1
            ORDER BY ln.local_interface
        """
        lldp_neighbors = execute_query(lldp_query, [device_id])

        # Get hardware from latest successful collection
        hardware_query = """
            WITH latest_successful_collection AS (
                SELECT 
                    device_id, 
                    id as collection_run_id,
                    collection_time,
                    ROW_NUMBER() OVER (ORDER BY collection_time DESC) as rn
                FROM collection_runs
                WHERE device_id = ? AND success = 1
            )
            SELECT 
                hi.*,
                lsc.collection_time
            FROM hardware_inventory hi
            JOIN latest_successful_collection lsc ON hi.collection_run_id = lsc.collection_run_id
            WHERE lsc.rn = 1
            ORDER BY hi.component_type, hi.slot_position
        """
        hardware = execute_query(hardware_query, [device_id])
        hardware = parse_hardware_status(hardware)

        # NEW: Get ARP entries from latest successful collection (FIXED table name)
        arp_query = """
            WITH latest_successful_collection AS (
                SELECT 
                    device_id, 
                    id as collection_run_id,
                    collection_time,
                    ROW_NUMBER() OVER (ORDER BY collection_time DESC) as rn
                FROM collection_runs
                WHERE device_id = ? AND success = 1
            )
            SELECT 
                ae.*,
                lsc.collection_time
            FROM arp_entries ae
            JOIN latest_successful_collection lsc ON ae.collection_run_id = lsc.collection_run_id
            WHERE lsc.rn = 1
            ORDER BY 
                -- Simple IP address sorting (convert to numeric for proper ordering)
                CAST(SUBSTR(ae.ip_address, 1, INSTR(ae.ip_address||'.', '.') - 1) AS INTEGER),
                CAST(SUBSTR(ae.ip_address, INSTR(ae.ip_address, '.') + 1, 
                     INSTR(SUBSTR(ae.ip_address, INSTR(ae.ip_address, '.') + 1)||'.', '.') - 1) AS INTEGER),
                ae.interface_name
        """
        arp_table = execute_query(arp_query, [device_id])

        # NEW: Get MAC address table from latest successful collection (FIXED field names)
        mac_query = """
            WITH latest_successful_collection AS (
                SELECT 
                    device_id, 
                    id as collection_run_id,
                    collection_time,
                    ROW_NUMBER() OVER (ORDER BY collection_time DESC) as rn
                FROM collection_runs
                WHERE device_id = ? AND success = 1
            )
            SELECT 
                mat.*,
                lsc.collection_time
            FROM mac_address_table mat
            JOIN latest_successful_collection lsc ON mat.collection_run_id = lsc.collection_run_id
            WHERE lsc.rn = 1
            ORDER BY mat.vlan_id, mat.interface_name, mat.mac_address
        """
        mac_address_table = execute_query(mac_query, [device_id])

        # Get recent configuration changes
        config_changes_query = """
            SELECT 
                cc.*,
                nc.config_type,
                nc.size_bytes,
                nc.line_count
            FROM config_changes cc
            JOIN device_configs nc ON cc.new_config_id = nc.id
            WHERE cc.device_id = ?
            ORDER BY cc.detected_at DESC
            LIMIT 5
        """
        config_changes = execute_query(config_changes_query, [device_id])

        # Debug output
        print(f"[DEBUG] Device: {device['device_name']} (ID: {device_id})")
        print(f"[DEBUG] IPs: {len(ips)}")
        print(f"[DEBUG] Interfaces: {len(interfaces)}")
        print(f"[DEBUG] Environment: {'Yes' if environment else 'No'}")
        print(f"[DEBUG] Collections: {len(collections)}")
        print(f"[DEBUG] LLDP: {len(lldp_neighbors)}")
        print(f"[DEBUG] Hardware: {len(hardware)}")
        print(f"[DEBUG] ARP Table: {len(arp_table)}")
        print(f"[DEBUG] MAC Table: {len(mac_address_table)}")
        print(f"[DEBUG] Config Changes: {len(config_changes)}")

        return render_template('devices/detail.html',
                               device=device,
                               ips=ips,
                               interfaces=interfaces,
                               environment=environment,
                               collections=collections,
                               lldp_neighbors=lldp_neighbors,
                               hardware=hardware,
                               arp_table=arp_table,              # NEW
                               mac_address_table=mac_address_table,  # NEW
                               config_changes=config_changes)

    except Exception as e:
        print(f"[ERROR] Error loading device details: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Error loading device details: {str(e)}", 'error')
        return redirect(url_for('devices.list_devices'))

@devices_bp.route('/<device_name>/interfaces')
def device_interfaces(device_name):
    """Show device interfaces in detail"""
    try:
        # Get device info
        device_query = "SELECT id, device_name FROM devices WHERE device_name = ? AND is_active = 1"
        device_result = execute_query(device_query, [device_name])

        if not device_result:
            flash(f"Device '{device_name}' not found", 'error')
            return redirect(url_for('devices.list_devices'))

        device = device_result[0]
        device_id = device['id']

        # CORRECTED: Get interfaces with IP addresses using CTE
        interfaces_query = """
            WITH latest_successful_collection AS (
                SELECT 
                    device_id, 
                    id as collection_run_id,
                    collection_time,
                    ROW_NUMBER() OVER (ORDER BY collection_time DESC) as rn
                FROM collection_runs
                WHERE device_id = ? AND success = 1
            )
            SELECT 
                i.*,
                lsc.collection_time,
                GROUP_CONCAT(iip.ip_address || '/' || iip.prefix_length) as ip_addresses
            FROM interfaces i
            JOIN latest_successful_collection lsc ON i.collection_run_id = lsc.collection_run_id
            LEFT JOIN interface_ips iip ON i.id = iip.interface_id
            WHERE lsc.rn = 1
            GROUP BY i.id
            ORDER BY 
                CASE i.interface_type 
                    WHEN 'Physical' THEN 1
                    WHEN 'PortChannel' THEN 2
                    WHEN 'VLAN' THEN 3
                    WHEN 'Loopback' THEN 4
                    ELSE 5
                END,
                i.interface_name
        """
        interfaces = execute_query(interfaces_query, [device_id])

        return render_template('devices/interfaces.html',
                               device=device,
                               interfaces=interfaces)

    except Exception as e:
        flash(f"Error loading interfaces: {str(e)}", 'error')
        return redirect(url_for('devices.device_detail', device_name=device_name))


@devices_bp.route('/api/search')
def api_device_search():
    """API endpoint for device search autocomplete"""
    try:
        query = request.args.get('q', '').strip()
        if not query or len(query) < 2:
            return jsonify([])

        search_query = """
            SELECT device_name, hostname, vendor, model, site_code
            FROM devices
            WHERE is_active = 1
            AND (device_name LIKE ? OR hostname LIKE ?)
            ORDER BY device_name
            LIMIT 10
        """
        search_param = f"%{query}%"
        results = execute_query(search_query, [search_param, search_param])

        return jsonify(results)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@devices_bp.route('/api/stats')
def api_device_stats():
    """API endpoint for device statistics"""
    try:
        # CORRECTED: Use CTE for device statistics
        stats_query = """
            WITH latest_collections AS (
                SELECT 
                    device_id,
                    collection_time,
                    success,
                    ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY collection_time DESC) as rn
                FROM collection_runs
            )
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN lc.success = 1 AND lc.collection_time >= datetime('now', '-24 hours') THEN 1 END) as online,
                COUNT(CASE WHEN lc.success = 0 AND lc.collection_time >= datetime('now', '-24 hours') THEN 1 END) as error,
                COUNT(CASE WHEN lc.collection_time < datetime('now', '-24 hours') THEN 1 END) as stale
            FROM devices d
            LEFT JOIN latest_collections lc ON d.id = lc.device_id AND lc.rn = 1
            WHERE d.is_active = 1
        """

        result = execute_query(stats_query)
        stats = result[0] if result else {'total': 0, 'online': 0, 'error': 0, 'stale': 0}

        return jsonify({
            'stats': stats,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@devices_bp.route('/<device_name>/refresh', methods=['POST'])
def refresh_device(device_name):
    """Trigger device data refresh"""
    try:
        # This would trigger a NAPALM collection for the specific device
        # For now, just return a success message
        flash(f"Refresh triggered for {device_name}. Data collection will begin shortly.", 'success')
        return redirect(url_for('devices.device_detail', device_name=device_name))

    except Exception as e:
        flash(f"Error triggering refresh: {str(e)}", 'error')
        return redirect(url_for('devices.device_detail', device_name=device_name))


@devices_bp.route('/export')
def export_devices():
    """Export device list to CSV"""
    try:
        import csv
        import io
        from flask import make_response

        # CORRECTED: Get all devices with latest collection status using CTE
        devices_query = """
            WITH latest_collections AS (
                SELECT 
                    device_id,
                    collection_time,
                    success,
                    ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY collection_time DESC) as rn
                FROM collection_runs
            )
            SELECT 
                d.device_name,
                d.hostname,
                d.vendor,
                d.model,
                d.serial_number,
                d.site_code,
                d.device_role,
                d.os_version,
                di.ip_address as primary_ip,
                d.last_updated,
                lc.collection_time as last_collection,
                lc.success as last_collection_success
            FROM devices d
            LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
            LEFT JOIN latest_collections lc ON d.id = lc.device_id AND lc.rn = 1
            WHERE d.is_active = 1
            ORDER BY d.device_name
        """
        devices = execute_query(devices_query)

        # Create CSV
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            'device_name', 'hostname', 'vendor', 'model', 'serial_number',
            'site_code', 'device_role', 'os_version', 'primary_ip', 'last_updated',
            'last_collection', 'last_collection_success'
        ])

        writer.writeheader()
        for device in devices:
            writer.writerow(device)

        # Create response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers[
            'Content-Disposition'] = f'attachment; filename=devices_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

        return response

    except Exception as e:
        flash(f"Error exporting devices: {str(e)}", 'error')
        return redirect(url_for('devices.list_devices'))


# ADDITIONAL UTILITY FUNCTIONS FOR DATA INTEGRITY

def cleanup_duplicate_interfaces():
    """Utility function to clean up duplicate interface records"""
    try:
        conn = get_db_connection()

        # Find and remove duplicate interfaces (keep the one from the latest collection)
        cleanup_query = """
            DELETE FROM interfaces 
            WHERE id NOT IN (
                WITH ranked_interfaces AS (
                    SELECT 
                        i.id,
                        ROW_NUMBER() OVER (
                            PARTITION BY i.device_id, i.interface_name 
                            ORDER BY cr.collection_time DESC
                        ) as rn
                    FROM interfaces i
                    JOIN collection_runs cr ON i.collection_run_id = cr.id
                )
                SELECT id FROM ranked_interfaces WHERE rn = 1
            )
        """

        cursor = conn.execute(cleanup_query)
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        return deleted_count

    except Exception as e:
        print(f"Error cleaning up duplicates: {e}")
        return 0


def get_device_collection_summary(device_id):
    """Get a summary of collection runs for a device"""
    query = """
        SELECT 
            COUNT(*) as total_collections,
            COUNT(CASE WHEN success = 1 THEN 1 END) as successful_collections,
            MAX(collection_time) as latest_collection,
            MIN(collection_time) as first_collection,
            AVG(collection_duration) as avg_duration
        FROM collection_runs
        WHERE device_id = ?
    """
    result = execute_query(query, [device_id])
    return result[0] if result else None