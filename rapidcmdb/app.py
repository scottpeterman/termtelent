#!/usr/bin/env python3
"""
NAPALM CMDB Admin Dashboard with Pipeline Management
Flask application with blueprints for network device management and real-time pipeline execution
"""
import traceback

from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from datetime import datetime, timedelta
import os
import sqlite3
import json
import logging
from theme_manager_web import setup_theme_context

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///napalm_cmdb.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize theme management ONCE
setup_theme_context(app)

# Initialize extensions
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pipeline.log'),
        logging.StreamHandler()
    ]
)

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
        results = cursor.fetchall()
        conn.commit()
        return [dict(row) for row in results]
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# Import blueprints
from blueprints.dashboard import dashboard_bp
from blueprints.devices import devices_bp
from blueprints.network import network_bp
from blueprints.config import config_bp
from blueprints.reports import reports_bp
from blueprints.drawio import drawio_bp
from blueprints.pipeline import pipeline_bp, init_socketio
from blueprints.topology import topology_bp
from blueprints.search import search_bp
from blueprints.device_crud import device_crud_bp
from blueprints.uptime import uptime_bp

# Initialize SocketIO with pipeline
init_socketio(socketio)

# Register blueprints
app.register_blueprint(dashboard_bp, url_prefix='/')
app.register_blueprint(devices_bp, url_prefix='/devices')
app.register_blueprint(network_bp, url_prefix='/network')
# app.register_blueprint(config_bp, url_prefix='/config')
app.register_blueprint(reports_bp, url_prefix='/reports')
app.register_blueprint(pipeline_bp, url_prefix='/pipeline')
app.register_blueprint(topology_bp, url_prefix='/topology')
app.register_blueprint(search_bp, url_prefix='/search')
app.register_blueprint(drawio_bp)
app.register_blueprint(device_crud_bp, url_prefix='/admin')
app.register_blueprint(uptime_bp, url_prefix='/uptime')

@app.context_processor
def inject_globals():
    """Inject global variables into all templates"""
    return {
        'app_name': 'NAPALM CMDB',
        'version': '1.0.0',
        'current_year': datetime.now().year,
        'now': datetime.now
    }

@app.before_request
def set_default_theme():
    """Set default theme if none exists in session"""
    if 'theme' not in session:
        session['theme'] = 'dark'

@app.template_filter('number_format')
def number_format_filter(value):
    """Format numbers with thousands separators"""
    if value is None:
        return 'N/A'
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return value

@app.template_filter('datetime')
def datetime_filter(value):
    """Format datetime for templates"""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except:
            return value
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return value

@app.template_filter('relative_time')
def relative_time_filter(value):
    """Show relative time (e.g., '2 hours ago')"""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except:
            return value

    if isinstance(value, datetime):
        now = datetime.now()
        diff = now - value

        if diff.days > 0:
            return f"{diff.days} days ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hours ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minutes ago"
        else:
            return "Just now"
    return value

@app.template_filter('file_size')
def file_size_filter(value):
    """Format file size in human readable format"""
    if not value:
        return "0 B"

    for unit in ['B', 'KB', 'MB', 'GB']:
        if value < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"

@app.route('/api/sites')
def api_sites():
    """API endpoint for site list"""
    try:
        sites_query = """
            SELECT 
                site_code,
                COUNT(*) as device_count,
                COUNT(CASE WHEN device_role = 'core' THEN 1 END) as core_count,
                COUNT(CASE WHEN device_role = 'access' THEN 1 END) as access_count
            FROM devices
            WHERE is_active = 1
            GROUP BY site_code
            ORDER BY site_code
        """
        sites = execute_query(sites_query)
        return jsonify(sites)
    except Exception as e:
        logging.error(f"Error fetching sites: {e}")
        return jsonify({'error': str(e)}), 500

# API endpoints for dashboard data
@app.route('/api/metrics')
def api_metrics():
    """API endpoint for dashboard metrics"""
    try:
        # Device statistics
        device_stats = execute_query("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN is_active = 1 THEN 1 END) as active,
                COUNT(CASE WHEN first_discovered > datetime('now', '-7 days') THEN 1 END) as recent
            FROM devices
        """)[0]

        # Vendor distribution
        vendor_dist = execute_query("""
            SELECT vendor, COUNT(*) as count 
            FROM devices 
            WHERE is_active = 1 
            GROUP BY vendor 
            ORDER BY count DESC
        """)

        # Role distribution
        role_dist = execute_query("""
            SELECT device_role, COUNT(*) as count 
            FROM devices 
            WHERE is_active = 1 
            GROUP BY device_role 
            ORDER BY count DESC
        """)

        # Collection statistics
        collection_stats = execute_query("""
            SELECT 
                AVG(CASE WHEN success = 1 THEN 100.0 ELSE 0.0 END) as success_rate,
                AVG(collection_duration) as avg_duration
            FROM collection_runs 
            WHERE collection_time > datetime('now', '-24 hours')
        """)

        success_rate = collection_stats[0]['success_rate'] if collection_stats else 0
        avg_duration = collection_stats[0]['avg_duration'] if collection_stats else 0

        # Health metrics
        health_stats = execute_query("""
            SELECT 
                AVG(cpu_usage) as avg_cpu,
                AVG(CASE 
                    WHEN memory_total > 0 THEN (memory_used * 100.0 / memory_total)
                    WHEN memory_available > 0 THEN (memory_used * 100.0 / (memory_used + memory_available))
                    ELSE NULL
                END) as avg_memory,
                COUNT(DISTINCT device_id) as monitored_devices
            FROM environment_data 
            WHERE created_at > datetime('now', '-24 hours')
        """)

        health_metrics = health_stats[0] if health_stats else {}

        return jsonify({
            'device_stats': {
                'total': device_stats['total'],
                'recent': device_stats['recent'],
                'vendors': vendor_dist,
                'roles': role_dist
            },
            'collection_stats': {
                'success_rate': success_rate or 0,
                'avg_duration': avg_duration or 0
            },
            'health_metrics': {
                'avg_cpu': health_metrics.get('avg_cpu', 0) or 0,
                'avg_memory': health_metrics.get('avg_memory', 0) or 0,
                'monitored_devices': health_metrics.get('monitored_devices', 0) or 0
            }
        })
    except Exception as e:
        logging.error(f"Error fetching metrics: {e}")
        return jsonify({'error': str(e)}), 500


# Add this route to your Flask app.py

@app.route('/api/theme/<theme_name>/chart-colors')
def api_theme_chart_colors(theme_name):
    """API endpoint to get chart colors for a specific theme"""
    try:
        # You'll need to import and initialize your ThemeLibrary
        # from termtel.themes3 import ThemeLibrary
        # theme_lib = ThemeLibrary()

        # For now, create a basic palette generator
        theme_file = os.path.join('themes', f'{theme_name}.json')
        if not os.path.exists(theme_file):
            return jsonify({'error': f'Theme {theme_name} not found'}), 404

        with open(theme_file, 'r') as f:
            theme_data = json.load(f)

        # Generate chart palette from theme
        chart_colors = generate_chart_colors_from_theme(theme_data)

        return jsonify({
            'theme_name': theme_name,
            'chart_palette': chart_colors,
            'primary_colors': {
                'primary': theme_data.get('primary', '#000000'),
                'secondary': theme_data.get('secondary', '#666666'),
                'success': theme_data.get('success', '#22c55e'),
                'error': theme_data.get('error', '#ef4444'),
                'line': theme_data.get('line', '#3b82f6'),
                'text': theme_data.get('text', '#ffffff')
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def generate_chart_colors_from_theme(theme_data):
    """Generate diverse chart colors from theme data"""
    # Base colors from theme
    base_colors = [
        theme_data.get('line', '#3b82f6'),  # Primary accent
        theme_data.get('success', '#22c55e'),  # Success/positive
        theme_data.get('error', '#ef4444'),  # Error/negative
        theme_data.get('primary', '#1f1f1f'),  # Primary brand
        theme_data.get('secondary', '#2b2b2b'),  # Secondary brand
        theme_data.get('grid', '#333333'),  # Grid/subtle accent
    ]

    # Helper functions
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6:
            return (0, 0, 0)
        try:
            return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return (0, 0, 0)

    def rgb_to_hex(r, g, b):
        return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"

    # Generate variations
    additional_colors = []
    for color in base_colors[:3]:  # Use first 3 colors
        if color.startswith('#'):
            r, g, b = hex_to_rgb(color)

            # Lighter version
            lighter_r = min(255, int(r * 1.4))
            lighter_g = min(255, int(g * 1.4))
            lighter_b = min(255, int(b * 1.4))
            additional_colors.append(rgb_to_hex(lighter_r, lighter_g, lighter_b))

            # Darker version
            darker_r = max(0, int(r * 0.6))
            darker_g = max(0, int(g * 0.6))
            darker_b = max(0, int(b * 0.6))
            additional_colors.append(rgb_to_hex(darker_r, darker_g, darker_b))

    # Combine and deduplicate
    all_colors = base_colors + additional_colors
    unique_colors = list(dict.fromkeys(all_colors))  # Remove duplicates

    # Add fallback colors if needed
    fallback_colors = [
        '#8b5cf6', '#06b6d4', '#f59e0b', '#84cc16',
        '#ec4899', '#6366f1', '#14b8a6', '#f97316'
    ]

    while len(unique_colors) < 12:
        for fallback in fallback_colors:
            if fallback not in unique_colors:
                unique_colors.append(fallback)
                if len(unique_colors) >= 12:
                    break

    return unique_colors[:12]

@app.route('/api/alerts')
def api_alerts():
    """API endpoint for system alerts"""
    try:
        alerts = []

        # Check for failed collections
        failed_collections = execute_query("""
            SELECT COUNT(*) as count
            FROM collection_runs 
            WHERE success = 0 AND collection_time > datetime('now', '-24 hours')
        """)[0]['count']

        if failed_collections > 0:
            alerts.append({
                'type': 'warning',
                'title': 'Collection Failures',
                'message': f'{failed_collections} devices failed collection in last 24h',
                'count': failed_collections
            })

        # Check for devices not seen recently
        stale_devices = execute_query("""
            SELECT COUNT(*) as count
            FROM devices 
            WHERE is_active = 1 AND last_updated < datetime('now', '-7 days')
        """)[0]['count']

        if stale_devices > 0:
            alerts.append({
                'type': 'info',
                'title': 'Stale Devices',
                'message': f'{stale_devices} devices not updated in 7+ days',
                'count': stale_devices
            })

        # Check for high CPU usage
        high_cpu_devices = execute_query("""
            SELECT COUNT(DISTINCT device_id) as count
            FROM environment_data 
            WHERE cpu_usage > 80 AND created_at > datetime('now', '-1 hour')
        """)[0]['count']

        if high_cpu_devices > 0:
            alerts.append({
                'type': 'danger',
                'title': 'High CPU Usage',
                'message': f'{high_cpu_devices} devices with CPU > 80%',
                'count': high_cpu_devices
            })

        return jsonify({'alerts': alerts})
    except Exception as e:
        logging.error(f"Error fetching alerts: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/activities')
def api_activities():
    """API endpoint for recent activities"""
    try:
        activities = []

        # Recent device discoveries
        recent_devices = execute_query("""
            SELECT device_name, first_discovered
            FROM devices 
            WHERE first_discovered > datetime('now', '-7 days')
            ORDER BY first_discovered DESC
            LIMIT 10
        """)

        for device in recent_devices:
            activities.append({
                'activity_type': 'device_discovery',
                'device_name': device['device_name'],
                'description': 'New device discovered',
                'timestamp': device['first_discovered']
            })

        # Recent config changes
        config_changes = execute_query("""
            SELECT d.device_name, cc.change_type, cc.detected_at, cc.change_size
            FROM config_changes cc
            JOIN devices d ON cc.device_id = d.id
            WHERE cc.detected_at > datetime('now', '-7 days')
            ORDER BY cc.detected_at DESC
            LIMIT 10
        """)

        for change in config_changes:
            activities.append({
                'activity_type': 'config_change',
                'device_name': change['device_name'],
                'description': f'Configuration {change["change_type"]} ({change["change_size"]} lines)',
                'timestamp': change['detected_at']
            })

        # Sort by timestamp
        activities.sort(key=lambda x: x['timestamp'], reverse=True)

        return jsonify({'activities': activities[:10]})
    except Exception as e:
        logging.error(f"Error fetching activities: {e}")
        return jsonify({'error': str(e)}), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('errors/500.html'), 500



# Theme discovery and API endpoints
@app.route('/api/themes')
def api_themes():
    """API endpoint to list all available themes"""
    try:
        themes_dir = 'themes'
        if not os.path.exists(themes_dir):
            return jsonify({'themes': [], 'error': 'Themes directory not found'}), 404

        theme_files = []
        for filename in os.listdir(themes_dir):
            if filename.endswith('.json'):
                theme_name = filename[:-5]  # Remove .json extension
                theme_files.append({
                    'name': theme_name,
                    'display_name': theme_name.replace('_', ' ').title(),
                    'filename': filename
                })

        # Sort themes alphabetically
        theme_files.sort(key=lambda x: x['name'])

        return jsonify({
            'themes': theme_files,
            'current_theme': session.get('theme', 'dark'),
            'count': len(theme_files)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/theme/<theme_name>')
def api_theme_data(theme_name):
    """API endpoint to get specific theme data"""
    try:
        theme_file = os.path.join('themes', f'{theme_name}.json')
        if not os.path.exists(theme_file):
            return jsonify({'error': f'Theme {theme_name} not found'}), 404

        with open(theme_file, 'r') as f:
            theme_data = json.load(f)

        return jsonify({
            'name': theme_name,
            'data': theme_data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/theme/preview/<theme_name>')
def api_theme_preview(theme_name):
    """API endpoint to preview a theme without applying it"""
    try:
        theme_file = os.path.join('themes', f'{theme_name}.json')
        if not os.path.exists(theme_file):
            return jsonify({'error': f'Theme {theme_name} not found'}), 404

        with open(theme_file, 'r') as f:
            theme_data = json.load(f)

        # Return CSS variables for preview
        css_vars = {}
        for key, value in theme_data.items():
            if isinstance(value, str) and not key == 'terminal':
                css_key = key.replace('_', '-')
                css_vars[f'--{css_key}'] = value

        return jsonify({
            'name': theme_name,
            'css_variables': css_vars,
            'colors': {
                'primary': theme_data.get('primary', '#000000'),
                'background': theme_data.get('background', '#ffffff'),
                'text': theme_data.get('text', '#000000'),
                'success': theme_data.get('success', '#22c55e'),
                'error': theme_data.get('error', '#ef4444')
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Replace the theme context processor in your app.py with this updated version

@app.context_processor
def inject_theme():
    """Enhanced theme context processor with query string support"""
    try:
        # Check for theme in query string first, then session
        theme_from_query = request.args.get('theme')
        if theme_from_query:
            # Update session with new theme
            session['theme'] = theme_from_query
            current_theme_name = theme_from_query
        else:
            current_theme_name = session.get('theme', 'dark')

        # Get all available themes
        themes_dir = 'themes'
        available_themes = []
        if os.path.exists(themes_dir):
            for filename in os.listdir(themes_dir):
                if filename.endswith('.json'):
                    theme_name = filename[:-5]
                    available_themes.append({
                        'name': theme_name,
                        'display_name': theme_name.replace('_', ' ').replace('-', ' ').title()
                    })

        # Sort themes
        available_themes.sort(key=lambda x: x['name'])

        # Load current theme data
        current_theme_file = os.path.join(themes_dir, f'{current_theme_name}.json')
        theme_data = {}

        if os.path.exists(current_theme_file):
            with open(current_theme_file, 'r') as f:
                theme_data = json.load(f)
        else:
            # Fallback to default dark theme
            theme_data = {
                "primary": "#0F172A",
                "secondary": "#1E293B",
                "background": "#0F172A",
                "darker_bg": "#0D1526",
                "lighter_bg": "#1E293B",
                "text": "#E2E8F0",
                "line": "#3B82F6",
                "success": "#22C55E",
                "error": "#EF4444",
                "border_light": "rgba(226, 232, 240, 0.4)"
            }

        return {
            'theme': theme_data,
            'current_theme_name': current_theme_name,
            'available_themes': available_themes,
            'theme_count': len(available_themes)
        }
    except Exception as e:
        # Return minimal fallback
        return {
            'theme': {"primary": "#0F172A", "background": "#0F172A", "text": "#E2E8F0"},
            'current_theme_name': 'dark',
            'available_themes': [],
            'theme_count': 0
        }


# Simplified theme switching route (optional - for POST requests)
@app.route('/api/theme', methods=['GET', 'POST'])
def api_theme():
    """Simple theme API - mainly for compatibility"""
    if request.method == 'POST':
        data = request.get_json()
        theme_name = data.get('theme')
        if theme_name:
            # Redirect to same page with theme query string
            return jsonify({
                'success': True,
                'theme': theme_name,
                'redirect_url': f'{request.referrer or "/"}?theme={theme_name}'
            })
        return jsonify({'success': False, 'error': 'No theme specified'}), 400
    else:
        # GET request - return current theme info
        return jsonify({
            'current_theme': session.get('theme', 'dark'),
            'available_themes': [t['name'] for t in inject_theme()['available_themes']],
            'theme_count': inject_theme()['theme_count']
        })


# Simple theme switching function for templates
@app.template_global()
def theme_url(theme_name, **kwargs):
    """Generate URL with theme parameter"""
    args = request.args.copy()
    args['theme'] = theme_name

    # Add any additional parameters
    for key, value in kwargs.items():
        args[key] = value

    return url_for(request.endpoint, **args)
# Health check endpoint
@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Test database connection
        conn = get_db_connection()
        conn.execute('SELECT 1')
        conn.close()

        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'database': 'connected',
            'pipeline': 'available'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }), 500

# Pipeline logs endpoint
@app.route('/logs')
def view_logs():
    """View pipeline logs"""
    try:
        with open('pipeline.log', 'r') as f:
            logs = f.readlines()

        # Get last 500 lines
        recent_logs = logs[-500:] if len(logs) > 500 else logs

        return render_template('logs.html', logs=recent_logs)
    except FileNotFoundError:
        return render_template('logs.html', logs=['No logs available'])
    except Exception as e:
        return render_template('logs.html', logs=[f'Error reading logs: {str(e)}'])

# WebSocket event handlers for real-time updates
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    emit('connection_response', {'data': 'Connected to pipeline server'})
    logging.info(f'Client connected: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logging.info(f'Client disconnected: {request.sid}')

# Development and production considerations
if __name__ == '__main__':
    # Ensure database exists
    try:
        if not os.path.exists('napalm_cmdb.db'):
            logging.warning("Database file not found. Please create the database using cmdb.sql")
            print("Warning: Database file not found. Please create the database using cmdb.sql")

        # Create necessary directories
        os.makedirs('captures', exist_ok=True)
        os.makedirs('logs', exist_ok=True)
        os.makedirs('themes', exist_ok=True)  # Create themes directory

        # Check if running in PyCharm debugger
        import sys

        is_debugging = 'pydevd' in sys.modules or '--debug' in sys.argv

        # Run with SocketIO for real-time features
        # Disable reloader when debugging to avoid path issues
        socketio.run(
            app,
            debug=True,
            host='0.0.0.0',
            port=5000,
            allow_unsafe_werkzeug=True,
            use_reloader=not is_debugging  # Disable reloader when debugging
        )
    except Exception as e:
        traceback.print_exc()
        print(f"Error starting application: {e}")