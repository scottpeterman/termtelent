#!/usr/bin/env python3
"""
Pipeline Management Blueprint - FIXED with Credential Support for Regular Collector
Handles network discovery, NAPALM collection, and data import pipeline
"""
from pprint import pprint

from flask import Blueprint, render_template, request, jsonify
import subprocess
import threading
import json
import os
import time
from datetime import datetime
from pathlib import Path
import logging
import yaml
import signal
import psutil
import glob
import math

from termtel.helpers.credslib import SecureCredentials
import os
import re
# Create blueprint
pipeline_bp = Blueprint('pipeline', __name__, url_prefix='/pipeline')

# Global variables for process management
active_processes = {}
socketio = None  # Will be injected from main app
# Credential managers
session_cred_manager = None
network_cred_manager = None


def init_socketio(socketio_instance):
    """Initialize SocketIO instance and register event handlers"""
    global socketio
    socketio = socketio_instance
    initialize_credential_managers()
    register_socketio_events()
    register_database_socketio_events()


def register_socketio_events():
    """Register SocketIO event handlers after socketio is initialized"""
    global socketio
    from flask_socketio import emit

    # ✅ MISSING HANDLER - Scanner events
    @socketio.on('start_scanner')
    def handle_start_scanner(data):
        """Handle scanner start request"""
        try:
            session_id = request.sid

            emit('scanner_output', {
                'message': 'Preparing network scanner...',
                'type': 'info'
            })

            # Build scanner command
            command = build_scanner_command(data)

            emit('scanner_output', {
                'message': f'Starting scanner: {" ".join(command)}',
                'type': 'info'
            })

            # Start scanner process
            start_scanner_process(command, session_id)

        except Exception as e:
            logging.error(f"Error starting scanner: {e}")
            emit('scanner_error', {'message': str(e)})

    # ✅ UPDATED HANDLER - JSON Collection events with credential support
    @socketio.on('start_collector')
    def handle_start_collector(data):
        """Handle JSON collection start request - UPDATED with credential support"""
        try:
            session_id = request.sid

            emit('collection_output', {
                'message': 'Preparing JSON collection...',
                'type': 'info'
            })

            # Validate scan file exists
            scan_file = data.get('scan_file', '')
            if not scan_file:
                emit('collection_error', {'message': 'No scan file specified'})
                return

            # Check if credential manager should be used
            use_credentials = data.get('use_credentials', True)  # Default to True for backward compatibility

            if use_credentials:
                # Check credential manager status first
                if not unlock_credential_manager_if_needed():
                    emit('collection_output', {
                        'message': 'Warning: Network credential manager is not available or unlocked. Running without secure credentials.',
                        'type': 'warning'
                    })
                    # Continue without credentials rather than failing
                    use_credentials = False

            # Build collector command
            command = build_collector_command(data)

            emit('collection_output', {
                'message': f'Starting JSON collector: {" ".join(command)}',
                'type': 'info'
            })

            # Start collector process with or without credentials
            if use_credentials:
                start_collector_process_with_creds(command, session_id)
            else:
                start_collector_process(command, session_id)

        except Exception as e:
            logging.error(f"Error starting JSON collector: {e}")
            emit('collection_error', {'message': str(e)})

    # Stop handlers
    @socketio.on('stop_scanner')
    def handle_stop_scanner():
        """Handle scanner stop request"""
        try:
            session_id = request.sid
            stop_process('scanner', session_id)
            emit('scanner_output', {
                'message': 'Scanner stopped by user',
                'type': 'warning'
            })
        except Exception as e:
            logging.error(f"Error stopping scanner: {e}")
            emit('scanner_error', {'message': str(e)})

    @socketio.on('stop_collector')
    def handle_stop_collector():
        """Handle JSON collection stop request"""
        try:
            session_id = request.sid
            stop_process('collector', session_id)
            emit('collection_output', {
                'message': 'JSON collection stopped by user',
                'type': 'warning'
            })
        except Exception as e:
            logging.error(f"Error stopping JSON collection: {e}")
            emit('collection_error', {'message': str(e)})

    # Credential management handlers
    @socketio.on('unlock_credential_manager')
    def handle_unlock_credential_manager(data):
        """Handle credential manager unlock request"""
        try:
            session_id = request.sid
            manager_type = data.get('manager_type', 'network')
            password = data.get('password', '')

            if manager_type == 'network' and network_cred_manager:
                if network_cred_manager.unlock(password):
                    emit('credential_unlock_success', {
                        'manager_type': manager_type,
                        'message': 'Network credential manager unlocked successfully'
                    })

                    try:
                        credentials_list = get_network_credentials()
                        emit('credentials_loaded', {
                            'count': len(credentials_list),
                            'names': [cred.get('name', 'unnamed') for cred in credentials_list]
                        })
                    except Exception as e:
                        logging.error(f"Error loading credentials after unlock: {e}")

                else:
                    emit('credential_unlock_error', {
                        'manager_type': manager_type,
                        'message': 'Invalid password or unlock failed'
                    })

            elif manager_type == 'session' and session_cred_manager:
                if session_cred_manager.unlock(password):
                    emit('credential_unlock_success', {
                        'manager_type': manager_type,
                        'message': 'Session credential manager unlocked successfully'
                    })
                else:
                    emit('credential_unlock_error', {
                        'manager_type': manager_type,
                        'message': 'Invalid password or unlock failed'
                    })

            else:
                emit('credential_unlock_error', {
                    'manager_type': manager_type,
                    'message': f'{manager_type.title()} credential manager not available'
                })

        except Exception as e:
            logging.error(f"Error unlocking credential manager: {e}")
            emit('credential_unlock_error', {
                'manager_type': data.get('manager_type', 'unknown'),
                'message': str(e)
            })

    @socketio.on('get_credential_status')
    def handle_get_credential_status():
        """Handle credential status request"""
        try:
            session_id = request.sid

            status = {
                'network_manager_available': network_cred_manager is not None,
                'network_manager_initialized': network_cred_manager.is_initialized if network_cred_manager else False,
                'network_manager_unlocked': network_cred_manager.is_unlocked() if network_cred_manager else False,
                'network_credentials_count': 0
            }

            if network_cred_manager and network_cred_manager.is_unlocked():
                try:
                    credentials_list = get_network_credentials()
                    status['network_credentials_count'] = len(credentials_list)
                    status['credential_names'] = [cred.get('name', 'unnamed') for cred in credentials_list]
                except Exception:
                    pass

            emit('credential_status_update', status)

        except Exception as e:
            logging.error(f"Error getting credential status: {e}")
            emit('credential_status_error', {'message': str(e)})

    # Database collection handler with credential integration
    @socketio.on('start_database_collection')
    def handle_start_database_collection(data):
        """Handle database-driven collection start request with credential manager integration"""
        try:
            session_id = request.sid

            emit('database_collection_output', {
                'message': 'Preparing database-driven collection...',
                'type': 'info'
            })

            # Check credential manager status first
            if not unlock_credential_manager_if_needed():
                emit('database_collection_error', {
                    'message': 'Network credential manager is not available or unlocked. Please unlock credentials first.'
                })
                return

            # Use the credential-aware command builder
            command = build_database_collector_command_with_creds(data)

            emit('database_collection_output', {
                'message': f'Starting database collector with secure credentials: {" ".join(command)}',
                'type': 'info'
            })

            # Use the credential-aware process starter
            start_database_collector_process_with_creds(command, session_id)

        except Exception as e:
            logging.error(f"Error starting database collection: {e}")
            emit('database_collection_error', {'message': str(e)})


def build_collector_command(data):
    """Build NAPALM collector command from form data - FIXED"""
    import sys
    import os

    # Get the directory where app.py is located
    app_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(app_dir)  # Go up one level from blueprints
    scans_dir = os.path.join(parent_dir, 'scans')

    # Use the current Python interpreter
    python_exe = sys.executable

    # Find the collector script
    collector_script = None
    possible_names = ['npcollector1.py']

    # Check in parent directory first (where app.py is)
    for name in possible_names:
        script_path = os.path.join(parent_dir, name)
        if os.path.exists(script_path):
            collector_script = script_path
            break

    # Check current directory as fallback
    if not collector_script:
        for name in possible_names:
            if os.path.exists(name):
                collector_script = os.path.abspath(name)
                break

    if not collector_script:
        available_files = []
        for pattern in ['*.py', '*collector*']:
            available_files.extend(glob.glob(os.path.join(parent_dir, pattern)))
        raise FileNotFoundError(
            f"Collector script not found. Tried: {possible_names}. Available Python files: {available_files}")

    logging.info(f"Found collector script: {collector_script}")

    # Get the scan file
    scan_file = data['scan_file']
    logging.info(f"Original scan_file from data: {scan_file}")

    # Build the full path to the scan file - IMPROVED LOGIC
    final_scan_file = resolve_scan_file_path(scan_file, parent_dir, scans_dir)
    logging.info(f"Using scan file: {final_scan_file}")

    # Build command: python npcollector1.py <json_file>
    command = [python_exe, collector_script, final_scan_file]

    # Add workers parameter if specified
    workers = data.get('max_workers', 10)
    if workers and workers != 10:  # Only add if different from default
        command.extend(['--workers', str(workers)])

    # Add config file parameter if using credentials
    use_credentials = data.get('use_credentials', True)
    if use_credentials:
        config_path = create_collector_config_with_creds(data)
        command.extend(['--config', config_path])

    logging.info(f"Final collector command: {' '.join(command)}")
    return command


def create_collector_config_with_creds(data):
    """Create temporary collector configuration file for regular collector"""
    import tempfile
    import yaml
    import os

    # Get database path
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Get collection methods from data, or use sensible defaults
    collection_methods = data.get('collection_methods', {})

    if not collection_methods:
        collection_methods = {
            'get_config': True,
            'get_facts': True,
            'get_interfaces': True,
            'get_interfaces_ip': True,
            'get_arp_table': True,
            'get_mac_address_table': True,
            'get_lldp_neighbors': True,
            'get_environment': False,
            'get_users': False,
            'get_optics': False,
            'get_network_instances': False,
            'get_inventory': True
        }

    pprint(data)

    # Create config WITHOUT embedded credentials - they'll come from environment variables
    config = {
        'timeout': data.get('timeout', 60),
        'max_workers': data.get('max_workers', 10),
        'enhanced_inventory': True,
        'device_ip_resolution': {
            'use_ip_address_field': True,
            'use_device_name': True,
            'use_hostname': True,
            'use_fqdn': True,
            'enable_dns_resolution': False
        },
        'device_filters': {
            'active_only': True,
            'include_non_network': False
        },
        'credentials': [],  # Empty - will be loaded from environment variables
        'collection_methods': collection_methods,  # ← USE the variable, not data.get()
        'vendor_overrides': {
            'hp_procurve': 'procurve',
            'hp_aruba_cx': 'arubaoss',
            'cisco_ios': 'ios',
            'cisco_nxos': 'nxos',
            'cisco_asa': 'asa'
        },
        'driver_options': {
            'eos': {'transport': 'ssh'},
            'arubaoss': {'transport': 'ssh'}
        }
    }

    # Create temporary config file
    temp_dir = tempfile.gettempdir()
    config_path = os.path.join(temp_dir, f'collector_config_secure_{int(time.time())}.yaml')

    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

    return config_path

def start_collector_process_with_creds(command, session_id):
    """Start NAPALM collector process with credentials from environment variables"""

    def run_collector():
        try:
            # Get the directory where app.py is located for working directory
            app_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(app_dir)  # Go up one level from blueprints

            logging.info(f"Starting collector with credentials from credential manager")
            logging.info(f"Command: {' '.join(command)}")
            logging.info(f"Working directory: {parent_dir}")

            # Get credentials from credential manager
            credentials_list = get_network_credentials()
            if not credentials_list:
                socketio.emit('collection_output', {
                    'message': 'Warning: No network credentials found in credential manager',
                    'type': 'warning'
                }, room=session_id)
            else:
                socketio.emit('collection_output', {
                    'message': f'Using {len(credentials_list)} credential sets from secure credential manager',
                    'type': 'info'
                }, room=session_id)

            # Create environment variables for credentials
            credential_env_vars = create_credential_env_vars(credentials_list)

            # Prepare environment - inherit current environment and add credentials
            process_env = os.environ.copy()
            process_env.update(credential_env_vars)

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                cwd=parent_dir,  # Set working directory to where app.py is
                encoding='utf-8',
                errors='replace',
                env=process_env  # Pass environment with credentials
            )

            # Store process for management
            active_processes[f'collector_{session_id}'] = process

            # Initialize counters
            stats = {
                'processed': 0,
                'failed': 0,
                'data_methods': 0,
                'total': 0,
                'rate': 0.0,
                'eta': 0
            }

            start_time = time.time()

            # Read output line by line
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                # Clean the line to remove any problematic characters (similar to scanner)
                try:
                    line = line.replace('📋', '[CONFIG]')
                    line = line.replace('🔍', '[SCAN]')
                    line = line.replace('✅', '[OK]')
                    line = line.replace('❌', '[ERROR]')
                    line = line.replace('⚙️', '[CONFIG]')
                    line = line.replace('🌐', '[NETWORK]')
                    line = line.replace('🎉', '[COMPLETE]')
                    line = line.encode('ascii', 'replace').decode('ascii')
                except UnicodeError:
                    line = "Collector output (encoding issue)"

                logging.debug(f"Collector output: {line}")

                # Parse collector output and update stats
                updated_stats = parse_collector_output(line, stats, start_time)

                # Emit output and progress
                socketio.emit('collection_output', {
                    'message': line,
                    'type': 'info'
                }, room=session_id)

                if updated_stats != stats:
                    stats = updated_stats
                    socketio.emit('collection_progress', stats, room=session_id)

            # Wait for process completion
            return_code = process.wait()
            logging.info(f"Collector process completed with return code: {return_code}")

            # Clean up temporary config file if it exists
            cleanup_temp_files(command)

            # Clean up process
            if f'collector_{session_id}' in active_processes:
                del active_processes[f'collector_{session_id}']

            if return_code == 0:
                socketio.emit('collection_complete', {
                    'processed': stats['processed'],
                    'successful': stats['processed'] - stats['failed']
                }, room=session_id)

                # Trigger database import
                trigger_database_import(session_id)
            else:
                socketio.emit('collection_error', {
                    'message': f'Collection failed with return code {return_code}'
                }, room=session_id)

        except FileNotFoundError as e:
            logging.error(f"Collector script or input file not found: {e}")
            socketio.emit('collection_error', {
                'message': f'Collector script or input file not found: {str(e)}'
            }, room=session_id)
        except Exception as e:
            logging.error(f"Collector process error: {e}")
            socketio.emit('collection_error', {
                'message': f'Collector process error: {str(e)}'
            }, room=session_id)

    # Start in background thread
    thread = threading.Thread(target=run_collector)
    thread.daemon = True
    thread.start()


def start_collector_process(command, session_id):
    """Start NAPALM collector process with real-time output (original version without credentials)"""

    def run_collector():
        try:
            # Get the directory where app.py is located for working directory
            app_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(app_dir)  # Go up one level from blueprints

            logging.info(f"Starting collector with command: {' '.join(command)}")
            logging.info(f"Working directory: {parent_dir}")

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                cwd=parent_dir,  # Set working directory to where app.py is
                encoding='utf-8',
                errors='replace'
            )

            # Store process for management
            active_processes[f'collector_{session_id}'] = process

            # Initialize counters
            stats = {
                'processed': 0,
                'failed': 0,
                'data_methods': 0,
                'total': 0,
                'rate': 0.0,
                'eta': 0
            }

            start_time = time.time()

            # Read output line by line
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                # Clean the line to remove any problematic characters (similar to scanner)
                try:
                    line = line.replace('📋', '[CONFIG]')
                    line = line.replace('🔍', '[SCAN]')
                    line = line.replace('✅', '[OK]')
                    line = line.replace('❌', '[ERROR]')
                    line = line.replace('⚙️', '[CONFIG]')
                    line = line.replace('🌐', '[NETWORK]')
                    line = line.replace('🎉', '[COMPLETE]')
                    line = line.encode('ascii', 'replace').decode('ascii')
                except UnicodeError:
                    line = "Collector output (encoding issue)"

                logging.debug(f"Collector output: {line}")

                # Parse collector output and update stats
                updated_stats = parse_collector_output(line, stats, start_time)

                # Emit output and progress
                socketio.emit('collection_output', {
                    'message': line,
                    'type': 'info'
                }, room=session_id)

                if updated_stats != stats:
                    stats = updated_stats
                    socketio.emit('collection_progress', stats, room=session_id)

            # Wait for process completion
            return_code = process.wait()
            logging.info(f"Collector process completed with return code: {return_code}")

            # Clean up temporary config file if it exists
            cleanup_temp_files(command)

            # Clean up process
            if f'collector_{session_id}' in active_processes:
                del active_processes[f'collector_{session_id}']

            if return_code == 0:
                socketio.emit('collection_complete', {
                    'processed': stats['processed'],
                    'successful': stats['processed'] - stats['failed']
                }, room=session_id)

                # Trigger database import
                trigger_database_import(session_id)
            else:
                socketio.emit('collection_error', {
                    'message': f'Collection failed with return code {return_code}'
                }, room=session_id)

        except FileNotFoundError as e:
            logging.error(f"Collector script or input file not found: {e}")
            socketio.emit('collection_error', {
                'message': f'Collector script or input file not found: {str(e)}'
            }, room=session_id)
        except Exception as e:
            logging.error(f"Collector process error: {e}")
            socketio.emit('collection_error', {
                'message': f'Collector process error: {str(e)}'
            }, room=session_id)

    # Start in background thread
    thread = threading.Thread(target=run_collector)
    thread.daemon = True
    thread.start()


def resolve_scan_file_path(scan_file, parent_dir, scans_dir):
    """Resolve scan file path with improved error handling"""
    # Check if it's already an absolute path
    if os.path.isabs(scan_file):
        if os.path.exists(scan_file):
            return os.path.abspath(scan_file)
        else:
            raise FileNotFoundError(f"Absolute path scan file not found: {scan_file}")

    # Check if it has path separators (relative path)
    if os.path.sep in scan_file:
        full_path = os.path.join(parent_dir, scan_file)
        if os.path.exists(full_path):
            return os.path.abspath(full_path)
        else:
            raise FileNotFoundError(f"Relative path scan file not found: {full_path}")

    # Just a filename - search in order of preference
    search_paths = [
        os.path.join(scans_dir, scan_file),  # scans directory first
        os.path.join(parent_dir, scan_file),  # parent directory
        os.path.join(os.getcwd(), scan_file)  # current working directory
    ]

    for path in search_paths:
        if os.path.exists(path):
            logging.info(f"Found scan file at: {path}")
            return os.path.abspath(path)

    # File not found anywhere
    raise FileNotFoundError(
        f"Scan file '{scan_file}' not found in any of these locations: {search_paths}"
    )


def parse_collector_output(line, stats, start_time):
    """Parse collector output to extract progress information - IMPROVED"""
    new_stats = stats.copy()

    # Look for collection progress indicators with more patterns
    if ('Successfully collected' in line or
            'Processed device' in line or
            'Device processed:' in line or
            'Completed processing' in line):
        new_stats['processed'] += 1

    elif ('Failed to connect' in line or
          'Error processing' in line or
          'Connection failed' in line or
          'Authentication failed' in line or
          'Timeout connecting' in line):
        new_stats['failed'] += 1

    elif ('get_facts' in line or 'get_config' in line or
          'get_interfaces' in line or 'get_lldp' in line or
          'get_arp' in line or 'get_mac' in line):
        new_stats['data_methods'] += 1

    elif ('devices found in scan file' in line or
          'total devices to process' in line or
          'Processing' in line and 'devices' in line):
        try:
            # Extract total count if mentioned
            import re
            # Look for number followed by 'devices'
            match = re.search(r'(\d+)\s+devices?', line)
            if match:
                new_stats['total'] = int(match.group(1))
        except (ValueError, AttributeError):
            pass

    # Calculate rate
    elapsed = time.time() - start_time
    if elapsed > 0:
        new_stats['rate'] = new_stats['processed'] / (elapsed / 60)  # devices per minute

    return new_stats


def build_scanner_command(data):
    """Build Python scanner command from form data - UPDATED for pyscanner3.py"""
    import sys
    import os
    import glob

    # Get the directory where app.py is located
    app_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(app_dir)  # Go up one level from blueprints

    # Use the current Python interpreter
    python_exe = sys.executable

    # Find the Python scanner script
    scanner_script = None
    possible_names = ['pyscanner3.py']

    # Check in parent directory first (where app.py is)
    for name in possible_names:
        script_path = os.path.join(parent_dir, name)
        if os.path.exists(script_path):
            scanner_script = script_path
            break

    # Check current directory as fallback
    if not scanner_script:
        for name in possible_names:
            if os.path.exists(name):
                scanner_script = os.path.abspath(name)
                break

    if not scanner_script:
        available_files = []
        for pattern in ['*.py', '*scanner*']:
            available_files.extend(glob.glob(os.path.join(parent_dir, pattern)))
        raise FileNotFoundError(
            f"Python scanner script not found. Tried: {possible_names}. Available Python files: {available_files}")

    logging.info(f"Found Python scanner script: {scanner_script}")

    # Build command: python pyscanner3.py --cidr <target> [options]
    command = [python_exe, scanner_script]

    # Required parameter: target becomes --cidr
    command.extend(['--cidr', data['target']])

    # Timeout parameter
    timeout_val = data.get('timeout', '4s')
    # Convert Go-style timeout to seconds for Python scanner
    if timeout_val.endswith('s'):
        timeout_seconds = int(timeout_val[:-1])
    else:
        timeout_seconds = int(timeout_val)
    command.extend(['--snmp-timeout', str(timeout_seconds)])

    # Concurrent scans (Python scanner uses --concurrent instead of -concurrency)
    concurrency = data.get('concurrency', 80)
    command.extend(['--concurrent', str(concurrency)])

    # SNMP version and credentials handling
    snmp_version = data.get('snmpVersion', 'mixed')
    logging.info(f"SNMP Version from form: {snmp_version}")

    if snmp_version == '3' or snmp_version == 'v3':
        # Force SNMPv3 only with no fallback
        command.extend(['--snmp-version', 'v3'])
        command.extend(['--no-fallback'])  # Disable v2c fallback

        username = data.get('username', '')
        if username:
            command.extend(['--username', username])

            # Auth protocol and key
            auth_protocol = data.get('authProtocol', 'SHA')
            command.extend(['--auth-protocol', auth_protocol])

            auth_key = data.get('authKey', '')
            if auth_key:
                command.extend(['--auth-key', auth_key])

            # Privacy protocol and key
            priv_protocol = data.get('privProtocol', 'AES')
            command.extend(['--priv-protocol', priv_protocol])

            priv_key = data.get('privKey', '')
            if priv_key:
                command.extend(['--priv-key', priv_key])

    elif snmp_version == '2' or snmp_version == 'v2c':
        # Force SNMPv2c only
        command.extend(['--snmp-version', 'v2c'])
        command.extend(['--no-fallback'])  # Disable v3 fallback

        # Community strings
        communities = data.get('communities', 'public').split(',')
        communities = [c.strip() for c in communities if c.strip()]
        if communities:
            command.extend(['--community', communities[0]])  # Primary community
            if len(communities) > 1:
                command.extend(['--communities'] + communities)  # All communities

    else:
        # Mixed mode - Python scanner will try v3 first, then v2c fallback
        username = data.get('username', '')
        if username:
            command.extend(['--username', username])

            # Only add auth-key and priv-key, skip protocols for simplicity
            auth_key = data.get('authKey', '')
            if auth_key:
                command.extend(['--auth-key', auth_key])

            priv_key = data.get('privKey', '')
            if priv_key:
                command.extend(['--priv-key', priv_key])

        # Add v2c communities for fallback
        communities = data.get('communities', 'public').split(',')
        communities = [c.strip() for c in communities if c.strip()]
        if communities:
            # Only add --communities (not --community for primary)
            command.extend(['--communities'] + communities)


    # Output format and file
    output_file = data.get('database', 'scan_results.json')
    command.extend(['--output', output_file])

    # rules_file = ('config','vendor_fingerprints.yaml')
    # rules_path = os.path.join(parent_dir, rules_file)
    command.extend(['--rules config/vendor_fingerprints.yaml'])

    # TCP pre-filtering options (new in Python scanner)
    tcp_timeout = data.get('tcpTimeout', 2)
    command.extend(['--tcp-timeout', str(tcp_timeout)])

    # Skip TCP check if requested
    if data.get('skipTcpCheck', False):
        command.append('--skip-tcp-check')

    # Custom TCP ports if specified
    tcp_ports = data.get('tcpPorts', '')
    if tcp_ports:
        ports = [p.strip() for p in tcp_ports.split(',') if p.strip().isdigit()]
        if ports:
            command.extend(['--tcp-ports'] + ports)

    # Verbose output if debugging
    if data.get('verbose', False):
        command.append('--verbose')

    # Debug: Log the final command
    logging.info(f"Final Python scanner command: {' '.join(command)}")

    return command


def parse_scanner_output(line, stats, start_time):
    """Parse Python scanner output to extract progress information - UPDATED"""
    new_stats = stats.copy()
    import re
    try:
        # The Python scanner has different output format
        # Look for progress indicators in the output

        # Progress lines look like: "✓ 192.168.1.1    | OK   | v2c  | cisco       | switch         | (1/254)"
        if '|' in line and '(' in line and ')' in line:
            # Extract progress from the end: (current/total)
            import re
            progress_match = re.search(r'\((\d+)/(\d+)\)', line)
            if progress_match:
                current = int(progress_match.group(1))
                total = int(progress_match.group(2))
                new_stats['scanned'] = current
                new_stats['total'] = total

            # Check if this was a successful scan (starts with ✓ or contains SNMP version)
            if line.startswith('✓') or ' v2c ' in line or ' v3 ' in line:
                # This is a found device - increment found count
                # Count unique successful scans by checking if we haven't seen this IP
                if not hasattr(parse_scanner_output, '_seen_ips'):
                    parse_scanner_output._seen_ips = set()

                # Extract IP address (first column after ✓)
                ip_match = re.search(r'✓\s+(\d+\.\d+\.\d+\.\d+)', line)
                if ip_match:
                    ip = ip_match.group(1)
                    if ip not in parse_scanner_output._seen_ips:
                        parse_scanner_output._seen_ips.add(ip)
                        new_stats['found'] += 1

                        # Check if SNMP is working (not 'FAIL')
                        if ' FAIL ' not in line:
                            new_stats['snmp_ready'] += 1

        # Look for summary progress lines
        elif 'Progress:' in line and '%' in line:
            # Lines like: "Progress: 45.3% | TCP OK: 23 | SNMP: 12 (v3: 5, v2c: 7) | TCP Failed: 45 | ETA: 2m 15s"
            import re

            # Extract TCP OK count
            tcp_match = re.search(r'TCP OK:\s*(\d+)', line)
            if tcp_match:
                new_stats['found'] = int(tcp_match.group(1))

            # Extract SNMP successful count
            snmp_match = re.search(r'SNMP:\s*(\d+)', line)
            if snmp_match:
                new_stats['snmp_ready'] = int(snmp_match.group(1))

        # Look for final summary lines
        elif 'Hosts scanned:' in line:
            numbers = re.findall(r'\d+', line)
            if numbers:
                new_stats['total'] = int(numbers[0])
        elif 'TCP responsive:' in line:
            numbers = re.findall(r'\d+', line)
            if numbers:
                new_stats['found'] = int(numbers[0])
        elif 'SNMP devices found:' in line:
            numbers = re.findall(r'\d+', line)
            if numbers:
                new_stats['snmp_ready'] = int(numbers[0])

        # Calculate rate if we have progress
        if new_stats['scanned'] > 0:
            elapsed = time.time() - start_time
            if elapsed > 0:
                new_stats['rate'] = new_stats['scanned'] / elapsed  # scans per second

    except (ValueError, IndexError, AttributeError) as e:
        logging.debug(f"Error parsing Python scanner output: {e}")

    return new_stats


def start_scanner_process(command, session_id):
    """Start scanner process with real-time output"""

    def run_scanner():
        try:
            # Get the directory where app.py is located for working directory
            app_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(app_dir)  # Go up one level from blueprints

            # Convert command list to properly escaped string
            import shlex
            command_str = ' '.join(shlex.quote(arg) for arg in command)
            command_str = command_str.replace("'", "")
            logging.info(f"Starting scanner with command: {command_str}")
            logging.info(f"Working directory: {parent_dir}")

            process = subprocess.Popen(
                command_str,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                cwd=parent_dir,
                encoding='utf-8',
                errors='replace',
                shell=True
            )

            # Store process for management
            active_processes[f'scanner_{session_id}'] = process

            # Initialize counters
            stats = {
                'scanned': 0,
                'found': 0,
                'snmp_ready': 0,
                'total': 0,
                'rate': 0.0,
                'eta': 0
            }

            start_time = time.time()

            # Read output line by line
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                # Clean the line to remove any problematic characters
                try:
                    line = line.replace('📋', '[CONFIG]')
                    line = line.replace('🔍', '[SCAN]')
                    line = line.replace('✅', '[OK]')
                    line = line.replace('❌', '[ERROR]')
                    line = line.replace('⚙️', '[CONFIG]')
                    line = line.replace('🌐', '[NETWORK]')
                    line = line.replace('🎉', '[COMPLETE]')
                    line = line.encode('ascii', 'replace').decode('ascii')
                except UnicodeError:
                    line = "Scanner output (encoding issue)"

                logging.debug(f"Scanner output: {line}")

                # Parse scanner output and update stats
                updated_stats = parse_scanner_output(line, stats, start_time)

                # Emit output and progress
                socketio.emit('scanner_output', {
                    'message': line,
                    'type': 'info'
                }, room=session_id)

                if updated_stats != stats:
                    stats = updated_stats
                    socketio.emit('scanner_progress', stats, room=session_id)

            # Wait for process completion
            return_code = process.wait()
            logging.info(f"Scanner process completed with return code: {return_code}")

            # Clean up
            if f'scanner_{session_id}' in active_processes:
                del active_processes[f'scanner_{session_id}']

            if return_code == 0:
                socketio.emit('scanner_complete', {
                    'found': stats['found'],
                    'snmp_ready': stats['snmp_ready'],
                    'output_file': extract_output_file_from_command(command)
                }, room=session_id)
            else:
                socketio.emit('scanner_error', {
                    'message': f'Scanner failed with return code {return_code}'
                }, room=session_id)

        except FileNotFoundError as e:
            logging.error(f"Scanner executable not found: {e}")
            socketio.emit('scanner_error', {
                'message': f'Scanner executable not found. Please ensure gosnmpcli.exe is in the application directory. Error: {str(e)}'
            }, room=session_id)
        except Exception as e:
            logging.error(f"Scanner process error: {e}")
            socketio.emit('scanner_error', {
                'message': f'Scanner process error: {str(e)}'
            }, room=session_id)

    # Start in background thread
    thread = threading.Thread(target=run_scanner)
    thread.daemon = True
    thread.start()



def stop_process(process_type, session_id):
    """Stop a running process"""
    process_key = f'{process_type}_{session_id}'

    if process_key in active_processes:
        process = active_processes[process_key]
        try:
            # Try graceful termination first
            process.terminate()

            # Wait for termination, then force kill if necessary
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

            del active_processes[process_key]
            logging.info(f"Stopped {process_type} process for session {session_id}")

        except Exception as e:
            logging.error(f"Error stopping {process_type} process: {e}")


def cleanup_temp_files(command):
    """Clean up temporary configuration files"""
    try:
        for arg in command:
            if (arg.startswith('/tmp/collector_config_') or
                arg.startswith('/tmp/db_collector_config_')) and arg.endswith('.yaml'):
                if os.path.exists(arg):
                    os.remove(arg)
                    logging.debug(f"Cleaned up temp config: {arg}")
    except Exception as e:
        logging.error(f"Error cleaning up temp files: {e}")


def extract_output_file_from_command(command):
    """Extract output file name from command"""
    try:
        for i, arg in enumerate(command):
            if arg == '-output-file' and i + 1 < len(command):
                return command[i + 1]
    except:
        pass
    return 'scan_results.json'


# Add route handlers
@pipeline_bp.route('/')
def index():
    """Pipeline management main page"""
    return render_template('pipeline/index.html')


@pipeline_bp.route('/scan-files')
def scan_files():
    """HTTP API endpoint to get available scan files"""
    try:
        files = get_available_scan_files()
        logging.info(f"Returning {len(files)} files via HTTP: {files}")
        return {'files': files, 'status': 'success'}
    except Exception as e:
        logging.error(f"Error getting scan files via HTTP: {e}")
        return {'files': [], 'error': str(e), 'status': 'error'}, 500


@pipeline_bp.route('/status')
def status():
    """Get current pipeline status"""
    status_info = {
        'active_processes': list(active_processes.keys()),
        'scanner_available': check_scanner_available(),
        'collector_available': check_collector_available(),
        'database_collector_available': check_database_collector_available(),
        'database_available': check_database_available()
    }
    print(status_info)
    return jsonify(status_info)


# Initialize credential management functions
def initialize_credential_managers():
    """Initialize both credential managers"""
    global session_cred_manager, network_cred_manager

    try:
        session_cred_manager = SecureCredentials("termtel")
        network_cred_manager = SecureCredentials("rapidcmdb_collector")
        logging.info("Credential managers initialized")
    except Exception as e:
        logging.error(f"Failed to initialize credential managers: {e}")


def get_network_credentials():
    """Retrieve network device credentials from secure credential manager"""
    if not network_cred_manager or not network_cred_manager.is_unlocked():
        logging.warning("Network credential manager not available or not unlocked")
        return []

    try:
        creds_path = network_cred_manager.config_dir / "network_credentials.yaml"
        if not creds_path.exists():
            logging.warning(f"Network credentials file not found: {creds_path}")
            return []

        credentials_list = network_cred_manager.load_credentials(creds_path)
        credentials_list.sort(key=lambda x: x.get('priority', 999))

        logging.info(f"Loaded {len(credentials_list)} network credentials from secure store")
        return credentials_list

    except Exception as e:
        logging.error(f"Failed to load network credentials: {e}")
        return []


def unlock_credential_manager_if_needed():
    """Attempt to unlock the network credential manager if it's locked"""
    global network_cred_manager

    if not network_cred_manager:
        logging.error("Network credential manager not initialized")
        return False

    if not network_cred_manager.is_initialized:
        logging.error("Network credential manager not initialized - please run credential setup first")
        return False

    if network_cred_manager.is_unlocked():
        return True

    logging.warning("Network credential manager is locked - credentials not available")
    return False


def create_credential_env_vars(credentials_list):
    """Convert credentials list to environment variables for CLI tools"""
    env_vars = {}

    if not credentials_list:
        logging.warning("No credentials available for environment variables")
        return env_vars

    # Create environment variables for each credential set
    for i, cred in enumerate(credentials_list):
        name = cred.get('name', f'CRED_{i}').upper()
        username = cred.get('username', '')
        password = cred.get('password', '')
        enable_password = cred.get('enable_password', '')
        priority = cred.get('priority', 999)

        # Create the environment variable patterns that both collectors expect
        env_vars[f'NAPALM_USERNAME_{name}'] = username
        env_vars[f'NAPALM_PASSWORD_{name}'] = password
        if enable_password:
            env_vars[f'NAPALM_ENABLE_{name}'] = enable_password
        env_vars[f'NAPALM_PRIORITY_{name}'] = str(priority)

        logging.debug(f"Created env vars for credential '{name}' with priority {priority}")

    logging.info(f"Created environment variables for {len(credentials_list)} credential sets")
    return env_vars


# File discovery and validation functions
def get_available_scan_files():
    """Get list of available JSON scan files with metadata"""
    import glob
    import os
    from datetime import datetime

    # Get the directory where app.py is located
    app_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(app_dir)  # Go up one level from blueprints

    # Look in the scans subdirectory
    scans_dir = os.path.join(parent_dir, 'scans')

    logging.info(f"Looking for scan files in directory: {scans_dir}")

    # Create scans directory if it doesn't exist
    if not os.path.exists(scans_dir):
        os.makedirs(scans_dir)
        logging.info(f"Created scans directory: {scans_dir}")

    # Look for JSON files that appear to be scanner database files
    search_patterns = [
        os.path.join(scans_dir, '*scanner*devices*.json'),
        os.path.join(scans_dir, 'scanner_*.json'),
        os.path.join(scans_dir, '*_devices.json'),
        os.path.join(scans_dir, 'scanned_*.json'),
        os.path.join(scans_dir, '*.json')  # All JSON files as fallback
    ]

    found_files = []
    seen_files = set()

    for pattern in search_patterns:
        logging.info(f"Searching pattern: {pattern}")
        matches = glob.glob(pattern)
        logging.info(f"Found {len(matches)} files for pattern: {matches}")

        for filepath in matches:
            filename = os.path.basename(filepath)

            # Skip if we've already seen this file
            if filename in seen_files:
                continue

            # Skip common non-scanner JSON files
            if filename.lower() in ['package.json', 'config.json', 'settings.json', 'package-lock.json']:
                logging.info(f"Skipping common non-scanner file: {filename}")
                continue

            try:
                # Get file info
                stat_info = os.stat(filepath)
                file_size = format_file_size(stat_info.st_size)
                modified_time = datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M')

                # Try to validate it's a scanner file by checking content
                is_scanner_file = validate_scanner_file(filepath)
                logging.info(
                    f"File {filename}: size={file_size}, modified={modified_time}, is_scanner={is_scanner_file}")

                file_info = f"{filename}|{file_size}|{modified_time}"
                found_files.append(file_info)
                seen_files.add(filename)

            except Exception as e:
                logging.error(f"Error processing file {filepath}: {e}")
                continue

    logging.info(f"Total files found: {len(found_files)}")

    # Sort by modification time (newest first)
    found_files.sort(key=lambda x: x.split('|')[2] if len(x.split('|')) > 2 else '', reverse=True)

    return found_files


def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0B"

    size_names = ["B", "KB", "MB", "GB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s}{size_names[i]}"


def validate_scanner_file(filepath):
    """Validate that a JSON file appears to be a scanner database file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read(2048)  # Read first 2KB

            if not content.strip():
                logging.debug(f"File {filepath} is empty")
                return False

            # Look for scanner-specific patterns
            scanner_indicators = [
                '"ip":', '"hostname":', '"vendor":', '"model":',
                '"snmp_version":', '"device_type":', '"platform":',
                '"system_description":', '"uptime":', '"location":',
                '"address":', '"community":', '"description":', '"contact":'
            ]

            # Count indicators found
            indicator_count = sum(1 for indicator in scanner_indicators if indicator in content)
            logging.debug(f"File {filepath} has {indicator_count} scanner indicators")

            # Need at least 1 indicator or valid JSON structure
            if indicator_count >= 1:
                return True

            # Also check if it looks like a JSON array/object with network-like data
            if ((content.strip().startswith('[') or content.strip().startswith('{')) and
                    ('.' in content and ('10.' in content or '192.' in content or '172.' in content))):
                logging.debug(f"File {filepath} looks like network data JSON")
                return True

            return False

    except Exception as e:
        logging.error(f"Error validating scanner file {filepath}: {e}")
        return False


# Utility functions

def check_scanner_available():
    """Check if Python scanner script is available - UPDATED"""
    # Check for Python scanner script
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    python_scanner = os.path.join(app_dir, 'pyscanner3.py')

    if os.path.exists(python_scanner):
        return True

    # Check current directory
    if os.path.exists('pyscanner3.py'):
        return True

    return False


def check_collector_available():
    """Check if collector script is available"""
    return os.path.exists('./npcollector1.py')


def check_database_available():
    """Check if database manager is available"""
    return os.path.exists('./db_manager.py')


def check_database_collector_available():
    """Check if database collector script is available"""
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.exists(os.path.join(app_dir, 'npcollector_db.py'))


# Include database collection functions (keeping existing working code)
def build_database_collector_command_with_creds(data):
    """Build database collector command with credentials from credential manager"""
    import sys
    import os

    # Get the directory where app.py is located
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Use the current Python interpreter
    python_exe = sys.executable

    # Find the database collector script
    collector_script = None
    possible_names = ['npcollector_db.py']

    for name in possible_names:
        script_path = os.path.join(app_dir, name)
        if os.path.exists(script_path):
            collector_script = script_path
            break

    if not collector_script:
        raise FileNotFoundError(f"Database collector script not found. Tried: {possible_names} in {app_dir}")

    logging.info(f"Found database collector script: {collector_script}")

    # Build command: python npcollector_db.py [options]
    command = [python_exe, collector_script]

    # Add database path
    db_path = data.get('database_path', 'napalm_cmdb.db')
    if not os.path.isabs(db_path):
        db_path = os.path.join(app_dir, db_path)
    command.extend(['--database', db_path])

    # Add workers parameter
    workers = data.get('max_workers', 10)
    command.extend(['--workers', str(workers)])

    # Add filters
    filters = data.get('filters', {})
    for filter_type, values in filters.items():
        if values and isinstance(values, list):
            if filter_type == 'name':
                command.extend(['--name'] + values)
            elif filter_type == 'site':
                command.extend(['--site'] + values)
            elif filter_type == 'vendor':
                command.extend(['--vendor'] + values)
            elif filter_type == 'role':
                command.extend(['--role'] + values)
            elif filter_type == 'model':
                command.extend(['--model'] + values)
            elif filter_type == 'ip':
                command.extend(['--ip'] + values)

    # Create temporary config file with collection settings (but NO credentials)
    config_path = create_database_collector_config_no_creds(data)
    command.extend(['--config', config_path])

    return command


def create_database_collector_config_no_creds(data):
    """Create temporary collector configuration file WITHOUT embedded credentials"""
    import tempfile
    import yaml
    import os

    # Build collection methods from form data
    collection_methods = data.get('collection_methods', {})
    if not collection_methods:
        collection_methods = {
            'get_config': True,
            'get_facts': True,
            'get_interfaces': True,
            'get_interfaces_ip': True,
            'get_arp_table': True,
            'get_mac_address_table': True,
            'get_lldp_neighbors': True,
            'get_environment': False,
            'get_users': False,
            'get_optics': False,
            'get_network_instances': False,
            'get_inventory': True
        }
    pprint(data)
    # Get database path
    db_path = data.get('database_path', 'napalm_cmdb.db')
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isabs(db_path):
        db_path = os.path.join(app_dir, db_path)

    # Create config WITHOUT credentials - they'll come from environment variables
    config = {
        'timeout': data.get('timeout', 60),
        'max_workers': data.get('max_workers', 10),
        'enhanced_inventory': True,
        'database_path': db_path,
        'device_ip_resolution': {
            'use_ip_address_field': True,
            'use_device_name': True,
            'use_hostname': True,
            'use_fqdn': True,
            'enable_dns_resolution': False
        },
        'device_filters': {
            'active_only': True,
            'include_non_network': False
        },
        'credentials': [],  # Empty - will be loaded from environment variables
        'collection_methods': collection_methods,
        'vendor_overrides': {
            'hp_procurve': 'procurve',
            'hp_aruba_cx': 'arubaoss',
            'cisco_ios': 'ios',
            'cisco_nxos': 'nxos',
            'cisco_asa': 'asa'
        },
        'driver_options': {
            'eos': {'transport': 'ssh'},
            'arubaoss': {'transport': 'ssh'}
        }
    }

    # Create temporary config file
    temp_dir = tempfile.gettempdir()
    config_path = os.path.join(temp_dir, f'db_collector_config_secure_{int(time.time())}.yaml')

    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

    return config_path


def start_database_collector_process_with_creds(command, session_id):
    """Start database collector process with credentials from environment variables"""

    def run_database_collector():
        try:
            # Get working directory
            app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            logging.info(f"Starting database collector with command: {' '.join(command)}")
            logging.info(f"Working directory: {app_dir}")

            # Get credentials from credential manager
            if not unlock_credential_manager_if_needed():
                socketio.emit('database_collection_error', {
                    'message': 'Failed to unlock credential manager. Please unlock network credentials first.'
                }, room=session_id)
                return

            credentials_list = get_network_credentials()
            if not credentials_list:
                socketio.emit('database_collection_error', {
                    'message': 'No network credentials found. Please add credentials in the credential manager.'
                }, room=session_id)
                return

            # Create environment variables for credentials
            credential_env_vars = create_credential_env_vars(credentials_list)

            # Prepare environment - inherit current environment and add credentials
            process_env = os.environ.copy()
            process_env.update(credential_env_vars)

            socketio.emit('database_collection_output', {
                'message': f'Using {len(credentials_list)} credential sets from secure credential manager',
                'type': 'info'
            }, room=session_id)

            # Start the process with credentials in environment
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                cwd=app_dir,
                encoding='utf-8',
                errors='replace',
                env=process_env  # Pass environment with credentials
            )

            # Store process for management
            active_processes[f'database_collector_{session_id}'] = process

            # Initialize counters
            stats = {
                'processed': 0,
                'failed': 0,
                'data_methods': 0,
                'total': 0,
                'rate': 0.0,
                'eta': 0
            }

            start_time = time.time()

            # Read output line by line
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                # Clean the line to remove any problematic characters
                try:
                    line = line.replace('📋', '[CONFIG]')
                    line = line.replace('🔍', '[SCAN]')
                    line = line.replace('✅', '[OK]')
                    line = line.replace('❌', '[ERROR]')
                    line = line.replace('⚙️', '[CONFIG]')
                    line = line.replace('🌐', '[NETWORK]')
                    line = line.replace('🎉', '[COMPLETE]')
                    line = line.encode('ascii', 'replace').decode('ascii')
                except UnicodeError:
                    line = "Database collector output (encoding issue)"

                logging.debug(f"Database collector output: {line}")

                # Parse database collector output and update stats
                updated_stats = parse_database_collector_output(line, stats, start_time)

                # Emit output and progress
                socketio.emit('database_collection_output', {
                    'message': line,
                    'type': 'info'
                }, room=session_id)

                if updated_stats != stats:
                    stats = updated_stats
                    socketio.emit('database_collection_progress', stats, room=session_id)

            # Wait for process completion
            return_code = process.wait()
            logging.info(f"Database collector process completed with return code: {return_code}")

            # Clean up temporary config file
            cleanup_temp_files(command)

            # Clean up process
            if f'database_collector_{session_id}' in active_processes:
                del active_processes[f'database_collector_{session_id}']

            if return_code == 0:
                socketio.emit('database_collection_complete', {
                    'processed': stats['processed'],
                    'successful': stats['processed'] - stats['failed']
                }, room=session_id)
                trigger_database_import(session_id, 'database_collection_output')

            else:
                socketio.emit('database_collection_error', {
                    'message': f'Database collection failed with return code {return_code}'
                }, room=session_id)

        except FileNotFoundError as e:
            logging.error(f"Database collector script not found: {e}")
            socketio.emit('database_collection_error', {
                'message': f'Database collector script not found: {str(e)}'
            }, room=session_id)
        except Exception as e:
            logging.error(f"Database collector process error: {e}")
            socketio.emit('database_collection_error', {
                'message': f'Database collector process error: {str(e)}'
            }, room=session_id)

    # Start in background thread
    thread = threading.Thread(target=run_database_collector)
    thread.daemon = True
    thread.start()


def parse_database_collector_output(line, stats, start_time):
    """Parse database collector output to extract progress information"""
    new_stats = stats.copy()

    # Look for collection progress indicators
    if 'Successfully collected' in line or 'Processed device' in line:
        new_stats['processed'] += 1
    elif 'Failed to connect' in line or 'Error processing' in line or 'Connection failed' in line:
        new_stats['failed'] += 1
    elif 'get_facts' in line or 'get_config' in line or 'get_interfaces' in line:
        new_stats['data_methods'] += 1
    elif 'devices from database' in line or 'collectible devices' in line:
        try:
            # Extract total count if mentioned
            parts = line.split()
            for i, part in enumerate(parts):
                if part.isdigit() and i > 0 and ('devices' in parts[i + 1] or 'collectible' in parts[i + 1]):
                    new_stats['total'] = int(part)
                    break
        except (ValueError, IndexError):
            pass

    # Calculate rate
    elapsed = time.time() - start_time
    if elapsed > 0:
        new_stats['rate'] = new_stats['processed'] / (elapsed / 60)  # devices per minute

    return new_stats


def register_database_socketio_events():
    """Register additional SocketIO event handlers for database collection"""
    global socketio
    from flask_socketio import emit
    from flask import request

    @socketio.on('test_database_connection')
    def handle_test_database_connection(data):
        """Test database connection and return statistics"""
        try:
            session_id = request.sid
            db_path = data.get('database_path', 'napalm_cmdb.db')

            emit('database_collection_output', {
                'message': f'Testing database connection: {db_path}',
                'type': 'info'
            })

            # Test database connection
            db_stats = test_database_connection_internal(db_path)

            if db_stats['status'] == 'connected':
                emit('database_status', db_stats)
            else:
                emit('database_status', {
                    'status': 'failed',
                    'message': db_stats.get('error', 'Unknown error')
                })

        except Exception as e:
            logging.error(f"Error testing database connection: {e}")
            emit('database_status', {
                'status': 'failed',
                'message': str(e)
            })

    @socketio.on('get_filtered_device_count')
    def handle_get_filtered_device_count(data):
        """Get count of devices matching filters"""
        try:
            session_id = request.sid
            db_path = data.get('database_path', 'napalm_cmdb.db')
            filters = data.get('filters', {})

            count = get_filtered_device_count_internal(db_path, filters)

            emit('filtered_device_count', {'count': count})

        except Exception as e:
            logging.error(f"Error getting filtered device count: {e}")
            emit('filtered_device_count', {'count': 0, 'error': str(e)})

    @socketio.on('get_filtered_devices')
    def handle_get_filtered_devices(data):
        """Get list of devices matching filters for preview"""
        try:
            session_id = request.sid
            db_path = data.get('database_path', 'napalm_cmdb.db')
            filters = data.get('filters', {})

            devices = get_filtered_devices_internal(db_path, filters)

            emit('device_preview', {'devices': devices})

        except Exception as e:
            logging.error(f"Error getting filtered devices: {e}")
            emit('device_preview', {'devices': [], 'error': str(e)})

    @socketio.on('stop_database_collection')
    def handle_stop_database_collection():
        """Handle database collection stop request"""
        try:
            session_id = request.sid
            stop_process('database_collector', session_id)
            emit('database_collection_output', {
                'message': 'Database collection stopped by user',
                'type': 'warning'
            })
        except Exception as e:
            logging.error(f"Error stopping database collection: {e}")
            emit('database_collection_error', {'message': str(e)})


def test_database_connection_internal(db_path):
    """Test database connection and return statistics"""
    import sqlite3
    import os

    try:
        # Get absolute path relative to app directory
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Go up from blueprints
        if not os.path.isabs(db_path):
            db_path = os.path.join(app_dir, db_path)

        if not os.path.exists(db_path):
            return {
                'status': 'failed',
                'error': f'Database file not found: {db_path}'
            }

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get device counts
        cursor.execute("SELECT COUNT(*) as total FROM devices")
        total_devices = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as active FROM devices WHERE is_active = 1")
        active_devices = cursor.fetchone()['active']

        # Count collectible devices (those with NAPALM driver support)
        collectible_vendors = [
            'cisco', 'arista', 'juniper', 'hp', 'hp_network', 'aruba',
            'fortinet', 'palo_alto'
        ]

        placeholders = ','.join(['?' for _ in collectible_vendors])
        cursor.execute(f"""
            SELECT COUNT(*) as collectible 
            FROM devices 
            WHERE is_active = 1 
            AND LOWER(vendor) IN ({placeholders})
        """, collectible_vendors)
        collectible_devices = cursor.fetchone()['collectible']

        conn.close()

        return {
            'status': 'connected',
            'total_devices': total_devices,
            'active_devices': active_devices,
            'collectible_devices': collectible_devices,
            'database_path': db_path
        }

    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e)
        }


def get_filtered_device_count_internal(db_path, filters):
    """Get count of devices matching filters"""
    import sqlite3
    import os

    try:
        # Get absolute path
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not os.path.isabs(db_path):
            db_path = os.path.join(app_dir, db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        query, params = build_filter_query(filters)
        cursor.execute(f"SELECT COUNT(*) as count FROM devices d {query}", params)

        count = cursor.fetchone()[0]
        conn.close()

        return count

    except Exception as e:
        logging.error(f"Error getting filtered device count: {e}")
        return 0


def get_filtered_devices_internal(db_path, filters, limit=100):
    """Get list of devices matching filters"""
    import sqlite3
    import os

    try:
        # Get absolute path
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not os.path.isabs(db_path):
            db_path = os.path.join(app_dir, db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query, params = build_filter_query(filters)

        # Join with device_ips to get IP addresses
        full_query = f"""
            SELECT d.*, 
                   COALESCE(
                       mgmt_ip.ip_address,
                       primary_ip.ip_address,
                       any_ip.ip_address
                   ) as primary_ip
            FROM devices d
            LEFT JOIN (
                SELECT device_id, ip_address 
                FROM device_ips 
                WHERE ip_type = 'management'
                ORDER BY is_primary DESC, id
            ) mgmt_ip ON d.id = mgmt_ip.device_id
            LEFT JOIN (
                SELECT device_id, ip_address 
                FROM device_ips 
                WHERE is_primary = 1
                ORDER BY id
            ) primary_ip ON d.id = primary_ip.device_id
            LEFT JOIN (
                SELECT device_id, ip_address 
                FROM device_ips 
                WHERE ip_type NOT IN ('virtual', 'hsrp', 'vrrp')
                ORDER BY 
                    CASE ip_type 
                        WHEN 'management' THEN 1
                        WHEN 'loopback' THEN 2
                        WHEN 'vlan' THEN 3
                        ELSE 4
                    END,
                    is_primary DESC, 
                    id
            ) any_ip ON d.id = any_ip.device_id
            {query}
            ORDER BY d.site_code, d.device_name
            LIMIT ?
        """

        cursor.execute(full_query, params + [limit])
        devices = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return devices

    except Exception as e:
        logging.error(f"Error getting filtered devices: {e}")
        return []


def build_filter_query(filters):
    """Build SQL WHERE clause and parameters from filters"""
    where_conditions = []
    params = []

    # Base condition - only active devices
    where_conditions.append("d.is_active = 1")

    # Apply each filter type
    for filter_type, values in filters.items():
        if not values or not isinstance(values, list):
            continue

        if filter_type == 'name':
            name_conditions = []
            for value in values:
                name_conditions.append("LOWER(d.device_name) LIKE ?")
                params.append(f"%{value.lower()}%")
            if name_conditions:
                where_conditions.append(f"({' OR '.join(name_conditions)})")

        elif filter_type == 'site':
            placeholders = ','.join(['?' for _ in values])
            where_conditions.append(f"LOWER(d.site_code) IN ({placeholders})")
            params.extend([v.lower() for v in values])

        elif filter_type == 'vendor':
            placeholders = ','.join(['?' for _ in values])
            where_conditions.append(f"LOWER(d.vendor) IN ({placeholders})")
            params.extend([v.lower() for v in values])

        elif filter_type == 'role':
            placeholders = ','.join(['?' for _ in values])
            where_conditions.append(f"LOWER(d.device_role) IN ({placeholders})")
            params.extend([v.lower() for v in values])

        elif filter_type == 'model':
            model_conditions = []
            for value in values:
                model_conditions.append("LOWER(d.model) LIKE ?")
                params.append(f"%{value.lower()}%")
            if model_conditions:
                where_conditions.append(f"({' OR '.join(model_conditions)})")

        elif filter_type == 'ip':
            # This requires a subquery to check device_ips table
            ip_conditions = []
            for value in values:
                ip_conditions.append("""
                    EXISTS (
                        SELECT 1 FROM device_ips di 
                        WHERE di.device_id = d.id 
                        AND di.ip_address LIKE ?
                    )
                """)
                params.append(f"%{value}%")
            if ip_conditions:
                where_conditions.append(f"({' OR '.join(ip_conditions)})")

    # Build WHERE clause
    where_clause = ""
    if where_conditions:
        where_clause = f"WHERE {' AND '.join(where_conditions)}"

    return where_clause, params


import os


def trigger_database_import(session_id, emit_channel='collection_output'):
    """Trigger database import of collected data"""
    try:
        socketio.emit(emit_channel, {
            'message': 'Starting database import...',
            'type': 'info'
        }, room=session_id)

        # Verify captures folder exists
        captures_path = './captures'
        if not os.path.exists(captures_path):
            error_msg = f'Captures folder "{captures_path}" does not exist'
            logging.error(error_msg)
            socketio.emit(emit_channel, {
                'message': error_msg,
                'type': 'error'
            }, room=session_id)
            return False

        if not os.path.isdir(captures_path):
            error_msg = f'Captures path "{captures_path}" exists but is not a directory'
            logging.error(error_msg)
            socketio.emit(emit_channel, {
                'message': error_msg,
                'type': 'error'
            }, room=session_id)
            return False

        # Confirm folder exists and check contents
        abs_captures_path = os.path.abspath(captures_path)
        try:
            capture_files = os.listdir(captures_path)
            device_folders = [f for f in capture_files if os.path.isdir(os.path.join(captures_path, f))]
            json_files = [f for f in capture_files if f.endswith('.json')]

            socketio.emit(emit_channel, {
                'message': f'✓ Captures folder exists: {abs_captures_path}',
                'type': 'info'
            }, room=session_id)

            socketio.emit(emit_channel, {
                'message': f'✓ Found {len(device_folders)} device folders and {len(json_files)} JSON files',
                'type': 'info'
            }, room=session_id)

            if len(device_folders) == 0 and len(json_files) == 0:
                socketio.emit(emit_channel, {
                    'message': 'Warning: Captures folder is empty - no data to import',
                    'type': 'warning'
                }, room=session_id)

        except Exception as e:
            logging.error(f"Error checking captures folder contents: {e}")
            socketio.emit(emit_channel, {
                'message': f'Warning: Could not read captures folder contents: {str(e)}',
                'type': 'warning'
            }, room=session_id)

        # Run database import
        success = run_database_import(captures_path, session_id)
        if success:
            socketio.emit('collection_output', {
                'message': 'Database import completed successfully',
                'type': 'success'
            }, room=session_id)
        else:
            socketio.emit('collection_output', {
                'message': 'Database import failed',
                'type': 'error'
            }, room=session_id)

        return success

    except Exception as e:
        logging.error(f"Database import error: {e}")
        socketio.emit('collection_output', {
            'message': f'Database import error: {str(e)}',
            'type': 'error'
        }, room=session_id)
        return False

def run_database_import(captures_dir, session_id):
    """Run database import using db_manager.py"""
    try:
        import sys

        # Find the database manager script
        db_manager_script = None
        possible_names = ['db_manager.py', './db_manager.py']

        for name in possible_names:
            if os.path.exists(name):
                db_manager_script = os.path.abspath(name)
                break

        if not db_manager_script:
            logging.error("db_manager.py not found")
            return False

        command = [
            sys.executable, db_manager_script,
            '--import-dir', captures_dir,
            '--db-path', 'napalm_cmdb.db'
        ]


        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            cwd=os.getcwd()
        )
        # Emit debug info
        socketio.emit('pipeline_output', {
            'message': f'DEBUG: Command: {" ".join(command)}',
            'type': 'info'
        }, room=session_id)

        socketio.emit('pipeline_output', {
            'message': f'DEBUG: Working directory: {os.getcwd()}',
            'type': 'info'
        }, room=session_id)

        socketio.emit('pipeline_output', {
            'message': f'DEBUG: Captures dir exists: {os.path.exists(captures_dir)}',
            'type': 'info'
        }, room=session_id)

        socketio.emit('pipeline_output', {
            'message': f'DEBUG: DB manager script exists: {os.path.exists(db_manager_script)}',
            'type': 'info'
        }, room=session_id)


        print(f"Current working directory: {os.getcwd()}")
        print(f"Database exists: {os.path.exists('napalm_cmdb.db')}")
        print(f"Captures directory: {captures_dir}")
        print(f"Captures dir contents: {os.listdir(captures_dir) if os.path.exists(captures_dir) else 'NOT FOUND'}")
        # Stream output
        for line in iter(process.stdout.readline, ''):
            if not line:
                break
            line = line.strip()
            if line:
                socketio.emit('pipeline_output', {
                    'message': f'Import: {line}',
                    'type': 'info'
                }, room=session_id)

        return_code = process.wait()
        return return_code == 0

    except Exception as e:
        logging.error(f"Database import process error: {e}")
        return False

