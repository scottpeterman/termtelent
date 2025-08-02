# blueprints/config.py
"""
Configuration Blueprint - Configuration management and changes
"""

from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
import sqlite3
from datetime import datetime, timedelta

config_bp = Blueprint('config', __name__, template_folder='../templates')


def get_db_connection():
    conn = sqlite3.connect('napalm_cmdb.db')
    conn.row_factory = sqlite3.Row
    return conn


def execute_query(query, params=None):
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


@config_bp.route('/')
def index():
    """Configuration management overview with search"""
    try:
        # Get search parameters
        search_term = request.args.get('search', '').strip()
        device_filter = request.args.get('device', '')
        config_type_filter = request.args.get('config_type', '')
        search_mode = request.args.get('mode', 'contains')

        search_results = []

        # Perform search if search term provided
        if search_term:
            search_results = search_configurations(search_term, device_filter, config_type_filter, search_mode)

        # Get recent configuration changes - FIXED with explicit table aliases
        changes_query = """
            SELECT 
                cc.id,
                cc.device_id,
                cc.old_config_id,
                cc.new_config_id,
                cc.change_type,
                cc.change_summary,
                cc.change_size,
                cc.detected_at,
                d.device_name,
                d.site_code,
                nc.config_type,
                nc.size_bytes as new_size,
                oc.size_bytes as old_size
            FROM config_changes cc
            JOIN devices d ON cc.device_id = d.id
            JOIN device_configs nc ON cc.new_config_id = nc.id
            LEFT JOIN device_configs oc ON cc.old_config_id = oc.id
            ORDER BY cc.detected_at DESC
            LIMIT 20
        """
        recent_changes = execute_query(changes_query)

        # Get configuration statistics - FIXED with explicit table aliases
        stats_query = """
            SELECT 
                COUNT(DISTINCT dc.device_id) as devices_with_configs,
                COUNT(*) as total_configs,
                SUM(dc.size_bytes) as total_size,
                AVG(dc.size_bytes) as avg_size
            FROM device_configs dc
            JOIN (
                SELECT device_id, config_type, MAX(created_at) as max_time
                FROM device_configs
                GROUP BY device_id, config_type
            ) latest ON dc.device_id = latest.device_id 
                      AND dc.config_type = latest.config_type 
                      AND dc.created_at = latest.max_time
        """
        stats_result = execute_query(stats_query)
        stats = stats_result[0] if stats_result else {}

        # Get change statistics by time period
        change_stats_query = """
            SELECT 
                COUNT(*) as total_changes,
                COUNT(CASE WHEN detected_at >= datetime('now', '-24 hours') THEN 1 END) as changes_24h,
                COUNT(CASE WHEN detected_at >= datetime('now', '-7 days') THEN 1 END) as changes_7d,
                COUNT(CASE WHEN detected_at >= datetime('now', '-30 days') THEN 1 END) as changes_30d
            FROM config_changes
        """
        change_stats_result = execute_query(change_stats_query)
        change_stats = change_stats_result[0] if change_stats_result else {}

        return render_template('config/index.html',
                               search_results=search_results,
                               recent_changes=recent_changes,
                               stats=stats,
                               change_stats=change_stats)
    except Exception as e:
        flash(f"Error loading configurations: {str(e)}", 'error')
        return render_template('config/index.html',
                               search_results=[],
                               recent_changes=[],
                               stats={},
                               change_stats={})


def search_configurations(search_term, device_filter='', config_type_filter='', search_mode='contains'):
    """Search configurations with various modes - only latest configs, no duplicates"""
    try:
        # Fixed query with proper table aliases to avoid ambiguous column names
        base_query = """
            WITH latest_configs AS (
                SELECT 
                    dc.device_id,
                    dc.config_type,
                    MAX(dc.created_at) as latest_time
                FROM device_configs dc
                GROUP BY dc.device_id, dc.config_type
            ),
            latest_config_ids AS (
                SELECT 
                    dc.id,
                    dc.device_id,
                    dc.config_type,
                    dc.created_at
                FROM device_configs dc
                INNER JOIN latest_configs lc ON 
                    dc.device_id = lc.device_id 
                    AND dc.config_type = lc.config_type 
                    AND dc.created_at = lc.latest_time
            )
            SELECT DISTINCT
                dc.id as config_id,
                dc.config_type,
                dc.size_bytes as config_size,
                dc.created_at,
                d.device_name,
                d.vendor,
                d.model,
                1 as match_count
            FROM device_configs dc
            INNER JOIN devices d ON dc.device_id = d.id
            INNER JOIN latest_config_ids lci ON dc.id = lci.id
            WHERE 1=1
        """

        params = []
        conditions = []

        # Search mode conditions
        if search_mode == 'contains':
            conditions.append("dc.config_content LIKE ?")
            params.append(f"%{search_term}%")
        elif search_mode == 'exact':
            conditions.append("dc.config_content LIKE ?")
            params.append(f"%{search_term}%")
        elif search_mode == 'regex':
            conditions.append("dc.config_content LIKE ?")
            params.append(f"%{search_term}%")
        elif search_mode == 'ip':
            # Search for IP patterns
            ip_patterns = [
                f"%{search_term}%",
                f"%ip address {search_term}%",
                f"%{search_term}/%"
            ]
            ip_conditions = " OR ".join(["dc.config_content LIKE ?" for _ in ip_patterns])
            conditions.append(f"({ip_conditions})")
            params.extend(ip_patterns)

        # Device filter - use the alias 'd' to be explicit
        if device_filter:
            conditions.append("d.device_name = ?")
            params.append(device_filter)

        # Config type filter - use the alias 'dc' to be explicit
        if config_type_filter:
            conditions.append("dc.config_type = ?")
            params.append(config_type_filter)

        # Add conditions to query
        if conditions:
            base_query += " AND " + " AND ".join(conditions)

        base_query += """
            ORDER BY d.device_name, dc.config_type
            LIMIT 50
        """

        results = execute_query(base_query, params)

        # Remove any remaining duplicates and calculate match counts
        seen = set()
        unique_results = []

        for result in results:
            key = f"{result['device_name']}_{result['config_type']}"
            if key not in seen:
                seen.add(key)
                # Calculate actual match count
                try:
                    match_count = count_matches_in_config(result['config_id'], search_term, search_mode)
                    if match_count > 0:  # Only include if there are actual matches
                        result['match_count'] = match_count
                        unique_results.append(result)
                except Exception as e:
                    print(f"Error counting matches for config {result['config_id']}: {e}")
                    # Include with default count if match counting fails
                    result['match_count'] = 1
                    unique_results.append(result)

        return unique_results

    except Exception as e:
        print(f"Error searching configurations: {e}")
        return []


def count_matches_in_config(config_id, search_term, search_mode):
    """Count actual matches in a specific configuration"""
    try:
        config_query = "SELECT config_content FROM device_configs WHERE id = ?"
        config_result = execute_query(config_query, [config_id])

        if not config_result:
            return 0

        config_content = config_result[0]['config_content']

        if search_mode == 'contains':
            # Count occurrences (case insensitive)
            return config_content.lower().count(search_term.lower())
        elif search_mode == 'exact':
            # Count exact phrase matches (case insensitive)
            return config_content.lower().count(search_term.lower())
        elif search_mode == 'ip':
            # Count IP-related matches
            count = 0
            search_lower = search_term.lower()
            content_lower = config_content.lower()

            # Count various IP patterns
            count += content_lower.count(search_lower)
            count += content_lower.count(f"ip address {search_lower}")
            count += content_lower.count(f"{search_lower}/")

            return count
        else:
            # Default to simple count
            return config_content.lower().count(search_term.lower())

    except Exception as e:
        print(f"Error counting matches: {e}")
        return 0


@config_bp.route('/api/config/<int:config_id>')
def api_get_config(config_id):
    """API endpoint to get configuration content"""
    try:
        config_query = """
            SELECT 
                dc.id,
                dc.device_id,
                dc.collection_run_id,
                dc.config_type,
                dc.config_content,
                dc.config_hash,
                dc.size_bytes,
                dc.line_count,
                dc.created_at,
                d.device_name
            FROM device_configs dc
            JOIN devices d ON dc.device_id = d.id
            WHERE dc.id = ?
        """
        config_result = execute_query(config_query, [config_id])

        if not config_result:
            return jsonify({'error': 'Configuration not found'}), 404

        config = config_result[0]

        return jsonify({
            'config_id': config['id'],
            'device_name': config['device_name'],
            'config_type': config['config_type'],
            'config_content': config['config_content'],
            'size_bytes': config['size_bytes'],
            'created_at': config['created_at']
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@config_bp.route('/device/<device_name>')
def device_configs(device_name):
    """Show configurations for a specific device"""
    try:
        # Get device info
        device_query = "SELECT id, device_name FROM devices WHERE device_name = ? AND is_active = 1"
        device_result = execute_query(device_query, [device_name])

        if not device_result:
            flash(f"Device '{device_name}' not found", 'error')
            return redirect(url_for('config.index'))

        device = device_result[0]
        device_id = device['id']

        # Get configurations - FIXED with explicit table aliases
        configs_query = """
            SELECT 
                dc.id,
                dc.device_id,
                dc.collection_run_id,
                dc.config_type,
                dc.config_hash,
                dc.size_bytes,
                dc.line_count,
                dc.created_at,
                cr.collection_time
            FROM device_configs dc
            JOIN collection_runs cr ON dc.collection_run_id = cr.id
            WHERE dc.device_id = ?
            ORDER BY dc.created_at DESC, dc.config_type
        """
        configs = execute_query(configs_query, [device_id])

        # Get configuration changes - FIXED with explicit table aliases
        changes_query = """
            SELECT 
                cc.id,
                cc.device_id,
                cc.old_config_id,
                cc.new_config_id,
                cc.change_type,
                cc.change_summary,
                cc.change_size,
                cc.detected_at,
                nc.config_type,
                nc.created_at as new_config_time,
                oc.created_at as old_config_time
            FROM config_changes cc
            JOIN device_configs nc ON cc.new_config_id = nc.id
            LEFT JOIN device_configs oc ON cc.old_config_id = oc.id
            WHERE cc.device_id = ?
            ORDER BY cc.detected_at DESC
        """
        changes = execute_query(changes_query, [device_id])

        return render_template('config/device.html',
                               device=device,
                               configs=configs,
                               changes=changes)

    except Exception as e:
        flash(f"Error loading configurations: {str(e)}", 'error')
        return redirect(url_for('config.index'))


@config_bp.route('/view/<int:config_id>')
def view_config(config_id):
    """View a specific configuration"""
    try:
        config_query = """
            SELECT 
                dc.id,
                dc.device_id,
                dc.collection_run_id,
                dc.config_type,
                dc.config_content,
                dc.config_hash,
                dc.size_bytes,
                dc.line_count,
                dc.created_at,
                d.device_name,
                cr.collection_time
            FROM device_configs dc
            JOIN devices d ON dc.device_id = d.id
            JOIN collection_runs cr ON dc.collection_run_id = cr.id
            WHERE dc.id = ?
        """
        config_result = execute_query(config_query, [config_id])

        if not config_result:
            flash("Configuration not found", 'error')
            return redirect(url_for('config.index'))

        config = config_result[0]

        return render_template('config/view.html', config=config)

    except Exception as e:
        flash(f"Error loading configuration: {str(e)}", 'error')
        return redirect(url_for('config.index'))


@config_bp.route('/compare/<int:old_id>/<int:new_id>')
def compare_configs(old_id, new_id):
    """Compare two configurations"""
    try:
        # Get both configurations - FIXED with explicit table aliases
        config_query = """
            SELECT 
                dc.id,
                dc.device_id,
                dc.collection_run_id,
                dc.config_type,
                dc.config_content,
                dc.config_hash,
                dc.size_bytes,
                dc.line_count,
                dc.created_at,
                d.device_name,
                cr.collection_time
            FROM device_configs dc
            JOIN devices d ON dc.device_id = d.id
            JOIN collection_runs cr ON dc.collection_run_id = cr.id
            WHERE dc.id IN (?, ?)
            ORDER BY dc.created_at
        """
        configs = execute_query(config_query, [old_id, new_id])

        if len(configs) != 2:
            flash("One or both configurations not found", 'error')
            return redirect(url_for('config.index'))

        old_config = configs[0]
        new_config = configs[1]

        # Get change details if available
        change_query = """
            SELECT * FROM config_changes
            WHERE old_config_id = ? AND new_config_id = ?
        """
        change_result = execute_query(change_query, [old_id, new_id])
        change = change_result[0] if change_result else None

        return render_template('config/compare.html',
                               old_config=old_config,
                               new_config=new_config,
                               change=change)

    except Exception as e:
        flash(f"Error comparing configurations: {str(e)}", 'error')
        return redirect(url_for('config.index'))