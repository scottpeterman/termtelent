#!/usr/bin/env python3
"""
Device CRUD Management Blueprint for RapidCMDB
Provides comprehensive Create, Read, Update, Delete operations for manual device management
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import sqlite3
import logging
import hashlib
from datetime import datetime
import json
import ipaddress
import re

device_crud_bp = Blueprint('device_crud', __name__)


# Database helper functions
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

        if query.strip().upper().startswith('SELECT'):
            results = cursor.fetchall()
            return [dict(row) for row in results]
        else:
            conn.commit()
            return cursor.lastrowid
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def generate_device_key(vendor, serial_number, model):
    """Generate stable device key from vendor, serial, model"""
    key_string = f"{vendor}|{serial_number}|{model}".lower()
    return hashlib.sha256(key_string.encode()).hexdigest()[:16]


def get_vendor_list():
    """Get combined vendor list from static list + database vendors"""
    # Static/common vendors (your preferred list)
    static_vendors = [
        'Aruba', 'Cisco', 'Juniper', 'Arista', 'HP', 'Dell', 'Fortinet',
        'Palo Alto', 'Ubiquiti', 'Mikrotik', 'Netgear', 'Other'
    ]

    # Get vendors from database
    try:
        db_vendors = execute_query("""
            SELECT DISTINCT vendor 
            FROM devices 
            WHERE vendor IS NOT NULL 
            AND vendor != '' 
            AND vendor != 'Unknown'
            ORDER BY vendor
        """)
        db_vendor_list = [v['vendor'] for v in db_vendors]
    except Exception as e:
        print(f"Error getting DB vendors: {e}")
        db_vendor_list = []

    # Combine and deduplicate (case-insensitive)
    all_vendors = set()
    vendor_lookup = {}  # For case preservation

    # Add static vendors first (these take precedence for casing)
    for vendor in static_vendors:
        vendor_lower = vendor.lower()
        all_vendors.add(vendor_lower)
        vendor_lookup[vendor_lower] = vendor

    # Add database vendors
    for vendor in db_vendor_list:
        vendor_lower = vendor.lower()
        if vendor_lower not in all_vendors:
            all_vendors.add(vendor_lower)
            vendor_lookup[vendor_lower] = vendor

    # Return sorted list with proper casing
    return sorted([vendor_lookup[v] for v in all_vendors])


def get_role_list():
    """Get combined role list from static list + database roles"""
    # Static/common roles
    static_roles = [
        'spine', 'leaf', 'core', 'distribution', 'access', 'router', 'firewall', 'access-point', 'wireless-controller','load-balancer'
        'switch', 'server', 'appliance', 'printer', 'ups','pdu','iot', 'camera','facility', 'unknown'
    ]

    # Get roles from database
    try:
        db_roles = execute_query("""
            SELECT DISTINCT device_role 
            FROM devices 
            WHERE device_role IS NOT NULL 
            AND device_role != '' 
            ORDER BY device_role
        """)
        db_role_list = [r['device_role'] for r in db_roles]
    except Exception as e:
        print(f"Error getting DB roles: {e}")
        db_role_list = []

    # Combine and deduplicate
    all_roles = set()
    role_lookup = {}

    # Add static roles first
    for role in static_roles:
        role_lower = role.lower()
        all_roles.add(role_lower)
        role_lookup[role_lower] = role

    # Add database roles
    for role in db_role_list:
        role_lower = role.lower()
        if role_lower not in all_roles:
            all_roles.add(role_lower)
            role_lookup[role_lower] = role

    return sorted([role_lookup[r] for r in all_roles])


def validate_ip_address(ip_str):
    """Validate IP address format"""
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False


def validate_site_code(site_code):
    """Validate site code format (3+ uppercase letters)"""
    return bool(re.match(r'^[A-Z]{3,}$', site_code))


# ==================
# DEVICE CRUD ROUTES
# ==================

@device_crud_bp.route('/devices')
def list_devices():
    """List all devices with filtering and pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    # Filters
    site_filter = request.args.get('site', '')
    vendor_filter = request.args.get('vendor', '')
    role_filter = request.args.get('role', '')
    status_filter = request.args.get('status', 'all')
    search_term = request.args.get('search', '')

    # Build query with filters
    where_conditions = []
    params = []

    if site_filter:
        # Site codes are typically uppercase, but let's be safe
        where_conditions.append("UPPER(d.site_code) = UPPER(?)")
        params.append(site_filter)

    if vendor_filter:
        # Case-insensitive vendor matching
        where_conditions.append("UPPER(d.vendor) = UPPER(?)")
        params.append(vendor_filter)

    if role_filter:
        # Case-insensitive role matching
        where_conditions.append("UPPER(d.device_role) = UPPER(?)")
        params.append(role_filter)

    if status_filter == 'active':
        where_conditions.append("d.is_active = 1")
    elif status_filter == 'inactive':
        where_conditions.append("d.is_active = 0")

    if search_term:
        # Case-insensitive search across multiple fields
        where_conditions.append("""
            (UPPER(d.device_name) LIKE UPPER(?) OR UPPER(d.hostname) LIKE UPPER(?) OR 
             UPPER(d.serial_number) LIKE UPPER(?) OR UPPER(d.model) LIKE UPPER(?))
        """)
        search_pattern = f"%{search_term}%"
        params.extend([search_pattern] * 4)

    # Construct WHERE clause
    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

    # Get total count
    count_query = f"""
        SELECT COUNT(*) as total
        FROM devices d
        {where_clause}
    """
    total_devices = execute_query(count_query, params)[0]['total']

    # Get paginated devices
    offset = (page - 1) * per_page
    devices_query = f"""
        SELECT 
            d.*,
            di.ip_address as primary_ip,
            cr.collection_time as last_collection,
            cr.success as last_collection_success,
            CASE 
                WHEN cr.collection_time IS NULL THEN 'never'
                WHEN cr.collection_time < datetime('now', '-7 days') THEN 'stale'
                WHEN cr.success = 0 THEN 'failed'
                ELSE 'recent'
            END as collection_status
        FROM devices d
        LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
        LEFT JOIN (
            SELECT device_id, collection_time, success,
                   ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY collection_time DESC) as rn
            FROM collection_runs
        ) cr ON d.id = cr.device_id AND cr.rn = 1
        {where_clause}
        ORDER BY d.device_name
        LIMIT ? OFFSET ?
    """
    params.extend([per_page, offset])
    devices = execute_query(devices_query, params)

    # Get filter options - also fix these to be case-insensitive
    sites = execute_query("""
        SELECT DISTINCT UPPER(site_code) as site_code 
        FROM devices 
        WHERE site_code IS NOT NULL AND site_code != ''
        ORDER BY site_code
    """)

    vendors = get_vendor_list()
    roles = get_role_list()

    # Pagination info
    total_pages = (total_devices + per_page - 1) // per_page

    return render_template('devices/crud_list.html',
                           devices=devices,
                           sites=[s['site_code'] for s in sites],
                           vendors=vendors,
                           roles=roles,
                           current_page=page,
                           total_pages=total_pages,
                           total_devices=total_devices,
                           per_page=per_page,
                           filters={
                               'site': site_filter,
                               'vendor': vendor_filter,
                               'role': role_filter,
                               'status': status_filter,
                               'search': search_term
                           })


@device_crud_bp.route('/devices/new')
def new_device():
    """Show form for creating new device"""
    # Get reference data for dropdowns
    sites = execute_query("SELECT DISTINCT site_code FROM devices ORDER BY site_code")
    vendors = get_vendor_list()  # ← CHANGED: Use dynamic function
    roles = get_role_list()      # ← CHANGED: Use dynamic function

    return render_template('devices/crud_form.html',
                           device=None,
                           sites=[s['site_code'] for s in sites],
                           vendors=vendors,
                           roles=roles,
                           action='create')


@device_crud_bp.route('/devices/create', methods=['POST'])
def create_device():
    """Create new device"""
    try:
        # Validate required fields
        required_fields = ['device_name', 'vendor', 'serial_number', 'site_code', 'device_role']
        for field in required_fields:
            if not request.form.get(field, '').strip():
                flash(f'{field.replace("_", " ").title()} is required', 'error')
                return redirect(url_for('device_crud.new_device'))

        # Extract form data
        device_name = request.form['device_name'].strip()
        hostname = request.form.get('hostname', '').strip() or device_name
        fqdn = request.form.get('fqdn', '').strip()
        vendor = request.form['vendor'].strip()
        model = request.form.get('model', '').strip() or 'Unknown'
        serial_number = request.form['serial_number'].strip()
        os_version = request.form.get('os_version', '').strip()
        site_code = request.form['site_code'].strip().upper()
        device_role = request.form['device_role'].strip()
        notes = request.form.get('notes', '').strip()
        primary_ip = request.form.get('primary_ip', '').strip()

        # Validation
        if not validate_site_code(site_code):
            flash('Site code must be 3+ uppercase letters', 'error')
            return redirect(url_for('device_crud.new_device'))

        if primary_ip and not validate_ip_address(primary_ip):
            flash('Invalid IP address format', 'error')
            return redirect(url_for('device_crud.new_device'))

        # Check for duplicate device name
        existing = execute_query("SELECT id FROM devices WHERE device_name = ?", [device_name])
        if existing:
            flash(f'Device name "{device_name}" already exists', 'error')
            return redirect(url_for('device_crud.new_device'))

        # Generate device key
        device_key = generate_device_key(vendor, serial_number, model)

        # Insert device
        device_query = """
            INSERT INTO devices (
                device_key, device_name, hostname, fqdn, vendor, model, 
                serial_number, os_version, site_code, device_role, notes,
                first_discovered, last_updated, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """
        now = datetime.now().isoformat()
        device_params = [
            device_key, device_name, hostname, fqdn, vendor, model,
            serial_number, os_version, site_code, device_role, notes,
            now, now
        ]

        device_id = execute_query(device_query, device_params)

        # Add primary IP if provided
        if primary_ip:
            ip_query = """
                INSERT INTO device_ips (
                    device_id, ip_address, ip_type, is_primary, created_at, updated_at
                ) VALUES (?, ?, 'management', 1, ?, ?)
            """
            execute_query(ip_query, [device_id, primary_ip, now, now])

        flash(f'Device "{device_name}" created successfully', 'success')
        return redirect(url_for('device_crud.view_device', device_id=device_id))

    except Exception as e:
        logging.error(f"Error creating device: {e}")
        flash(f'Error creating device: {str(e)}', 'error')
        return redirect(url_for('device_crud.new_device'))


def parse_hardware_status(hardware_list):
    """Parse additional_data JSON to get real hardware status"""

    for hw in hardware_list:
        # Set defaults
        hw['actual_status'] = hw.get('status', 'unknown')
        hw['psu_capacity'] = None
        hw['psu_output'] = None
        if hw.get('slot_position') == 'invalid' or not hw.get('slot_position'):
            hw['slot_position'] = 'N/A'
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


@device_crud_bp.route('/devices/<int:device_id>')
def view_device(device_id):
    """View device details"""
    try:
        # Get device with primary IP
        device_query = """
            SELECT 
                d.*,
                di.ip_address as primary_ip,
                di.ip_type as primary_ip_type
            FROM devices d
            LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
            WHERE d.id = ?
        """
        device = execute_query(device_query, [device_id])
        if not device:
            flash('Device not found', 'error')
            return redirect(url_for('device_crud.list_devices'))

        device = device[0]

        # Get all IPs
        ips = execute_query("""
            SELECT * FROM device_ips 
            WHERE device_id = ? 
            ORDER BY is_primary DESC, ip_type, ip_address
        """, [device_id])

        # FIXED: Get interfaces from the most recent collection that has interface data
        interfaces = execute_query("""
            SELECT i.*, cr.collection_time
            FROM interfaces i
            JOIN collection_runs cr ON i.collection_run_id = cr.id
            WHERE i.device_id = ?
            AND cr.id = (
                SELECT cr2.id 
                FROM collection_runs cr2
                JOIN interfaces i2 ON cr2.id = i2.collection_run_id
                WHERE cr2.device_id = ? AND cr2.success = 1
                ORDER BY cr2.collection_time DESC
                LIMIT 1
            )
            ORDER BY 
                CASE i.interface_type 
                    WHEN 'Physical' THEN 1
                    WHEN 'PortChannel' THEN 2
                    WHEN 'VLAN' THEN 3
                    WHEN 'Loopback' THEN 4
                    ELSE 5
                END,
                i.interface_name
        """, [device_id, device_id])

        # FIXED: Get most recent environment data (any collection run)
        environment = execute_query("""
            SELECT ed.*, cr.collection_time
            FROM environment_data ed
            JOIN collection_runs cr ON ed.collection_run_id = cr.id
            WHERE ed.device_id = ?
            ORDER BY ed.created_at DESC
            LIMIT 1
        """, [device_id])
        environment = environment[0] if environment else None

        # Get collection history
        collections = execute_query("""
            SELECT *
            FROM collection_runs
            WHERE device_id = ?
            ORDER BY collection_time DESC
            LIMIT 10
        """, [device_id])

        # FIXED: Get LLDP neighbors from most recent collection that has LLDP data
        lldp_neighbors = execute_query("""
            SELECT ln.*, cr.collection_time
            FROM lldp_neighbors ln
            JOIN collection_runs cr ON ln.collection_run_id = cr.id
            WHERE ln.device_id = ?
            AND cr.id = (
                SELECT cr2.id 
                FROM collection_runs cr2
                JOIN lldp_neighbors ln2 ON cr2.id = ln2.collection_run_id
                WHERE cr2.device_id = ? AND cr2.success = 1
                ORDER BY cr2.collection_time DESC
                LIMIT 1
            )
            ORDER BY ln.local_interface
        """, [device_id, device_id])

        # FIXED: Get hardware from most recent collection that has hardware data
        hardware = execute_query("""
            SELECT hi.*, cr.collection_time
            FROM hardware_inventory hi
            JOIN collection_runs cr ON hi.collection_run_id = cr.id
            WHERE hi.device_id = ?
            AND cr.id = (
                SELECT cr2.id 
                FROM collection_runs cr2
                JOIN hardware_inventory hi2 ON cr2.id = hi2.collection_run_id
                WHERE cr2.device_id = ? AND cr2.success = 1
                ORDER BY cr2.collection_time DESC
                LIMIT 1
            )
            ORDER BY hi.component_type, hi.slot_position
        """, [device_id, device_id])
        hardware = parse_hardware_status(hardware)

        # FIXED: Get recent configuration changes
        config_changes = execute_query("""
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
        """, [device_id])

        # Debug output
        print(f"[DEBUG] Device: {device['device_name']} (ID: {device_id})")
        print(f"[DEBUG] IPs: {len(ips)}")
        print(f"[DEBUG] Interfaces: {len(interfaces)}")
        print(f"[DEBUG] Environment: {'Yes' if environment else 'No'}")
        print(f"[DEBUG] Collections: {len(collections)}")
        print(f"[DEBUG] LLDP: {len(lldp_neighbors)}")
        print(f"[DEBUG] Hardware: {len(hardware)}")
        print(f"[DEBUG] Config Changes: {len(config_changes)}")

        # Additional debug: Show which collection runs have data
        for table_name in ['interfaces', 'lldp_neighbors', 'hardware_inventory', 'environment_data']:
            runs_with_data = execute_query(f"""
                SELECT DISTINCT cr.id, cr.collection_time, COUNT(*) as record_count
                FROM collection_runs cr
                JOIN {table_name} t ON cr.id = t.collection_run_id
                WHERE cr.device_id = ?
                GROUP BY cr.id, cr.collection_time
                ORDER BY cr.collection_time DESC
            """, [device_id])

            if runs_with_data:
                print(f"[DEBUG] {table_name} data found in collection runs:")
                for run in runs_with_data:
                    print(f"  Run {run['id']} ({run['collection_time']}): {run['record_count']} records")
            else:
                print(f"[DEBUG] No {table_name} data found")

        return render_template('devices/detail.html',
                               device=device,
                               ips=ips,
                               interfaces=interfaces,
                               environment=environment,
                               collections=collections,
                               lldp_neighbors=lldp_neighbors,
                               hardware=hardware,
                               config_changes=config_changes)

    except Exception as e:
        print(f"[ERROR] Error loading device details: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Error loading device details: {str(e)}", 'error')
        return redirect(url_for('device_crud.list_devices'))


@device_crud_bp.route('/devices/<int:device_id>/edit')
def edit_device(device_id):
    """Show form for editing device"""
    device = execute_query("SELECT * FROM devices WHERE id = ?", [device_id])
    if not device:
        flash('Device not found', 'error')
        return redirect(url_for('device_crud.list_devices'))

    device = device[0]

    # Get primary IP
    primary_ip = execute_query("""
        SELECT ip_address FROM device_ips 
        WHERE device_id = ? AND is_primary = 1
    """, [device_id])

    if primary_ip:
        device['primary_ip'] = primary_ip[0]['ip_address']

    # Get reference data
    sites = execute_query("SELECT DISTINCT site_code FROM devices ORDER BY site_code")
    vendors = get_vendor_list()  # ← CHANGED: Use dynamic function
    roles = get_role_list()      # ← CHANGED: Use dynamic function

    return render_template('devices/crud_form.html',
                           device=device,
                           sites=[s['site_code'] for s in sites],
                           vendors=vendors,
                           roles=roles,
                           action='edit')



@device_crud_bp.route('/devices/<int:device_id>/update', methods=['POST'])
def update_device(device_id):
    """Update device"""
    try:
        # Check if device exists
        existing_device = execute_query("SELECT * FROM devices WHERE id = ?", [device_id])
        if not existing_device:
            flash('Device not found', 'error')
            return redirect(url_for('device_crud.list_devices'))

        # Validate required fields
        required_fields = ['device_name', 'vendor', 'serial_number', 'site_code', 'device_role']
        for field in required_fields:
            if not request.form.get(field, '').strip():
                flash(f'{field.replace("_", " ").title()} is required', 'error')
                return redirect(url_for('device_crud.edit_device', device_id=device_id))

        # Extract form data
        device_name = request.form['device_name'].strip()
        hostname = request.form.get('hostname', '').strip() or device_name
        fqdn = request.form.get('fqdn', '').strip()
        vendor = request.form['vendor'].strip()
        model = request.form.get('model', '').strip() or 'Unknown'
        serial_number = request.form['serial_number'].strip()
        os_version = request.form.get('os_version', '').strip()
        site_code = request.form['site_code'].strip().upper()
        device_role = request.form['device_role'].strip()
        notes = request.form.get('notes', '').strip()
        primary_ip = request.form.get('primary_ip', '').strip()
        is_active = request.form.get('is_active') == 'on'

        # Validation
        if not validate_site_code(site_code):
            flash('Site code must be 3+ uppercase letters', 'error')
            return redirect(url_for('device_crud.edit_device', device_id=device_id))

        if primary_ip and not validate_ip_address(primary_ip):
            flash('Invalid IP address format', 'error')
            return redirect(url_for('device_crud.edit_device', device_id=device_id))

        # Check for duplicate device name (excluding current device)
        name_check = execute_query(
            "SELECT id FROM devices WHERE device_name = ? AND id != ?",
            [device_name, device_id]
        )
        if name_check:
            flash(f'Device name "{device_name}" already exists', 'error')
            return redirect(url_for('device_crud.edit_device', device_id=device_id))

        # Generate new device key if vendor/serial/model changed
        old_device = existing_device[0]
        if (vendor != old_device['vendor'] or
                serial_number != old_device['serial_number'] or
                model != old_device['model']):
            device_key = generate_device_key(vendor, serial_number, model)
        else:
            device_key = old_device['device_key']

        # Update device
        update_query = """
            UPDATE devices SET
                device_key = ?, device_name = ?, hostname = ?, fqdn = ?,
                vendor = ?, model = ?, serial_number = ?, os_version = ?,
                site_code = ?, device_role = ?, notes = ?, is_active = ?,
                last_updated = ?
            WHERE id = ?
        """
        now = datetime.now().isoformat()
        update_params = [
            device_key, device_name, hostname, fqdn, vendor, model,
            serial_number, os_version, site_code, device_role, notes,
            is_active, now, device_id
        ]

        execute_query(update_query, update_params)

        # Update primary IP
        if primary_ip:
            # Remove old primary IP
            execute_query("DELETE FROM device_ips WHERE device_id = ? AND is_primary = 1", [device_id])

            # Add new primary IP
            ip_query = """
                INSERT INTO device_ips (
                    device_id, ip_address, ip_type, is_primary, created_at, updated_at
                ) VALUES (?, ?, 'management', 1, ?, ?)
            """
            execute_query(ip_query, [device_id, primary_ip, now, now])
        else:
            # Remove primary IP if none provided
            execute_query("DELETE FROM device_ips WHERE device_id = ? AND is_primary = 1", [device_id])

        flash(f'Device "{device_name}" updated successfully', 'success')
        return redirect(url_for('device_crud.view_device', device_id=device_id))

    except Exception as e:
        logging.error(f"Error updating device: {e}")
        flash(f'Error updating device: {str(e)}', 'error')
        return redirect(url_for('device_crud.edit_device', device_id=device_id))


@device_crud_bp.route('/devices/<int:device_id>/delete', methods=['POST'])
def delete_device(device_id):
    """Delete device (soft delete by default)"""
    try:
        device = execute_query("SELECT device_name FROM devices WHERE id = ?", [device_id])
        if not device:
            flash('Device not found', 'error')
            return redirect(url_for('device_crud.list_devices'))

        device_name = device[0]['device_name']
        soft_delete = request.form.get('soft_delete', 'true') == 'true'

        if soft_delete:
            # Soft delete - mark as inactive
            execute_query("UPDATE devices SET is_active = 0, last_updated = ? WHERE id = ?",
                          [datetime.now().isoformat(), device_id])
            flash(f'Device "{device_name}" deactivated successfully', 'success')
        else:
            # Hard delete - remove completely (cascades to related data)
            execute_query("DELETE FROM devices WHERE id = ?", [device_id])
            flash(f'Device "{device_name}" deleted permanently', 'success')

        return redirect(url_for('device_crud.list_devices'))

    except Exception as e:
        logging.error(f"Error deleting device: {e}")
        flash(f'Error deleting device: {str(e)}', 'error')
        return redirect(url_for('device_crud.view_device', device_id=device_id))


# ================
# BULK OPERATIONS
# ================

@device_crud_bp.route('/devices/bulk')
def bulk_operations():
    """Show bulk operations interface"""
    return render_template('devices/crud_bulk.html')


@device_crud_bp.route('/devices/bulk/import', methods=['POST'])
def bulk_import():
    """Bulk import devices from CSV"""
    try:
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(url_for('device_crud.bulk_operations'))

        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('device_crud.bulk_operations'))

        if not file.filename.endswith('.csv'):
            flash('Please upload a CSV file', 'error')
            return redirect(url_for('device_crud.bulk_operations'))

        # Process CSV file
        import csv
        import io

        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.DictReader(stream)

        imported_count = 0
        error_count = 0
        errors = []

        for row_num, row in enumerate(csv_input, start=2):
            try:
                # Validate required fields
                required_fields = ['device_name', 'vendor', 'serial_number', 'site_code', 'device_role']
                for field in required_fields:
                    if not row.get(field, '').strip():
                        raise ValueError(f"Missing required field: {field}")

                # Extract and validate data
                device_name = row['device_name'].strip()
                vendor = row['vendor'].strip()
                serial_number = row['serial_number'].strip()
                site_code = row['site_code'].strip().upper()
                device_role = row['device_role'].strip()

                if not validate_site_code(site_code):
                    raise ValueError("Invalid site code format")

                # Check for duplicates
                existing = execute_query("SELECT id FROM devices WHERE device_name = ?", [device_name])
                if existing:
                    raise ValueError(f"Device name already exists: {device_name}")

                # Create device
                device_key = generate_device_key(vendor, serial_number, row.get('model', 'Unknown'))
                now = datetime.now().isoformat()

                device_query = """
                    INSERT INTO devices (
                        device_key, device_name, hostname, vendor, model, 
                        serial_number, os_version, site_code, device_role,
                        first_discovered, last_updated, is_active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """
                device_params = [
                    device_key, device_name, row.get('hostname', device_name),
                    vendor, row.get('model', 'Unknown'), serial_number,
                    row.get('os_version', ''), site_code, device_role,
                    now, now
                ]

                execute_query(device_query, device_params)
                imported_count += 1

            except Exception as e:
                error_count += 1
                errors.append(f"Row {row_num}: {str(e)}")

        # Report results
        if imported_count > 0:
            flash(f'Successfully imported {imported_count} devices', 'success')

        if error_count > 0:
            flash(f'{error_count} errors occurred during import', 'warning')
            for error in errors[:10]:  # Show first 10 errors
                flash(error, 'error')

        return redirect(url_for('device_crud.list_devices'))

    except Exception as e:
        logging.error(f"Error in bulk import: {e}")
        flash(f'Import failed: {str(e)}', 'error')
        return redirect(url_for('device_crud.bulk_operations'))


@device_crud_bp.route('/devices/bulk/update', methods=['POST'])
def bulk_update():
    """Bulk update selected devices"""
    try:
        device_ids = request.form.getlist('device_ids')
        if not device_ids:
            flash('No devices selected', 'error')
            return redirect(url_for('device_crud.list_devices'))

        # Get update fields
        updates = {}
        if request.form.get('update_site_code'):
            updates['site_code'] = request.form['site_code'].strip().upper()
        if request.form.get('update_device_role'):
            updates['device_role'] = request.form['device_role'].strip()
        if request.form.get('update_vendor'):
            updates['vendor'] = request.form['vendor'].strip()
        if request.form.get('update_status'):
            updates['is_active'] = request.form['status'] == 'active'

        if not updates:
            flash('No update fields specified', 'error')
            return redirect(url_for('device_crud.list_devices'))

        # Build update query
        set_clauses = []
        params = []

        for field, value in updates.items():
            set_clauses.append(f"{field} = ?")
            params.append(value)

        params.append(datetime.now().isoformat())  # last_updated

        # Add device IDs for WHERE clause
        placeholders = ','.join(['?'] * len(device_ids))
        params.extend([int(id) for id in device_ids])

        update_query = f"""
            UPDATE devices 
            SET {', '.join(set_clauses)}, last_updated = ?
            WHERE id IN ({placeholders})
        """

        execute_query(update_query, params)

        flash(f'Successfully updated {len(device_ids)} devices', 'success')
        return redirect(url_for('device_crud.list_devices'))

    except Exception as e:
        logging.error(f"Error in bulk update: {e}")
        flash(f'Bulk update failed: {str(e)}', 'error')
        return redirect(url_for('device_crud.list_devices'))


# =============
# API ENDPOINTS
# =============

@device_crud_bp.route('/api/devices', methods=['GET'])
def api_devices():
    """API endpoint for device list with pagination, filtering, and CSV export"""
    try:
        # Check if CSV export is requested
        format_type = request.args.get('format', 'json')
        export_type = request.args.get('export', 'paginated')

        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 500)

        # Filters
        site_filter = request.args.get('site', '')
        vendor_filter = request.args.get('vendor', '')
        role_filter = request.args.get('role', '')
        status_filter = request.args.get('status', 'all')
        search_term = request.args.get('search', '')

        # Build query with filters
        where_conditions = []
        params = []

        if site_filter:
            where_conditions.append("d.site_code = ?")
            params.append(site_filter)

        if vendor_filter:
            where_conditions.append("d.vendor = ?")
            params.append(vendor_filter)

        if role_filter:
            where_conditions.append("d.device_role = ?")
            params.append(role_filter)

        if status_filter == 'active':
            where_conditions.append("d.is_active = 1")
        elif status_filter == 'inactive':
            where_conditions.append("d.is_active = 0")

        if search_term:
            where_conditions.append("""
                (d.device_name LIKE ? OR d.hostname LIKE ? OR 
                 d.serial_number LIKE ? OR d.model LIKE ?)
            """)
            search_pattern = f"%{search_term}%"
            params.extend([search_pattern] * 4)

        # Construct WHERE clause
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

        # For export=all or export=filtered, get all matching devices (no pagination)
        if export_type in ['all', 'filtered']:
            devices_query = f"""
                SELECT 
                    d.*,
                    di.ip_address as primary_ip,
                    cr.collection_time as last_collection,
                    cr.success as last_collection_success,
                    CASE 
                        WHEN cr.collection_time IS NULL THEN 'never'
                        WHEN cr.collection_time < datetime('now', '-7 days') THEN 'stale'
                        WHEN cr.success = 0 THEN 'failed'
                        ELSE 'recent'
                    END as collection_status
                FROM devices d
                LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
                LEFT JOIN (
                    SELECT device_id, collection_time, success,
                           ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY collection_time DESC) as rn
                    FROM collection_runs
                ) cr ON d.id = cr.device_id AND cr.rn = 1
                {where_clause}
                ORDER BY d.device_name
            """
            devices = execute_query(devices_query, params)
        else:
            # Regular paginated query
            devices_query = f"""
                SELECT 
                    d.*,
                    di.ip_address as primary_ip,
                    cr.collection_time as last_collection,
                    cr.success as last_collection_success,
                    CASE 
                        WHEN cr.collection_time IS NULL THEN 'never'
                        WHEN cr.collection_time < datetime('now', '-7 days') THEN 'stale'
                        WHEN cr.success = 0 THEN 'failed'
                        ELSE 'recent'
                    END as collection_status
                FROM devices d
                LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
                LEFT JOIN (
                    SELECT device_id, collection_time, success,
                           ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY collection_time DESC) as rn
                    FROM collection_runs
                ) cr ON d.id = cr.device_id AND cr.rn = 1
                {where_clause}
                ORDER BY d.device_name
                LIMIT ? OFFSET ?
            """
            offset = (page - 1) * per_page
            query_params = params + [per_page, offset]
            devices = execute_query(devices_query, query_params)

        # Handle CSV export
        if format_type == 'csv':
            return export_devices_as_csv(devices)

        # JSON response (default)
        if export_type in ['all', 'filtered']:
            total_devices = len(devices)
        else:
            count_query = f"""
                SELECT COUNT(*) as total
                FROM devices d
                {where_clause}
            """
            total_devices = execute_query(count_query, params)[0]['total']

        return jsonify({
            'devices': devices,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_devices
            }
        })

    except Exception as e:
        logging.error(f"Error in api_devices: {e}")
        return jsonify({'error': str(e)}), 500


def export_devices_as_csv(devices):
    """Export devices as CSV response"""
    import csv
    import io
    from flask import make_response

    # Create CSV content
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    headers = [
        'device_name', 'hostname', 'vendor', 'model', 'serial_number',
        'site_code', 'device_role', 'primary_ip', 'os_version', 'notes',
        'active', 'first_discovered', 'last_updated', 'collection_status'
    ]
    writer.writerow(headers)

    # Write device data
    for device in devices:
        row = [
            device.get('device_name', ''),
            device.get('hostname', ''),
            device.get('vendor', ''),
            device.get('model', ''),
            device.get('serial_number', ''),
            device.get('site_code', ''),
            device.get('device_role', ''),
            device.get('primary_ip', ''),
            device.get('os_version', ''),
            device.get('notes', ''),
            'Yes' if device.get('is_active') else 'No',
            device.get('first_discovered', ''),
            device.get('last_updated', ''),
            device.get('collection_status', '')
        ]
        writer.writerow(row)

    # Create response
    csv_content = output.getvalue()
    output.close()

    response = make_response(csv_content)
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = 'attachment; filename=devices_export.csv'

    return response


@device_crud_bp.route('/api/devices/<int:device_id>', methods=['GET'])
def api_device_detail(device_id):
    """API endpoint for single device details"""
    try:
        device = execute_query("SELECT * FROM latest_devices WHERE id = ?", [device_id])
        if not device:
            return jsonify({'error': 'Device not found'}), 404

        return jsonify({'device': device[0]})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@device_crud_bp.route('/api/devices', methods=['POST'])
def api_create_device():
    """API endpoint for creating devices"""
    try:
        data = request.get_json()



        return jsonify({'message': 'Device created successfully', 'device_id': device_id}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Register blueprint in your main app.py:
# app.register_blueprint(device_crud_bp, url_prefix='/devices')