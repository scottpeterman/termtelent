from flask import Blueprint, request, jsonify, send_file
import tempfile
from pathlib import Path
from datetime import datetime
import logging

from .drawio_exporter import RapidCMDBDrawioExporter
from .topology import build_topology_map  # Import your existing function

logger = logging.getLogger(__name__)

drawio_bp = Blueprint('drawio', __name__, url_prefix='/api/drawio')


@drawio_bp.route('/export', methods=['POST'])
def export_topology():
    """Export topology to Draw.io format"""
    try:
        config = request.get_json() or {}

        # Build topology using existing RapidCMDB function
        topology_data = build_topology_map(
            include_patterns=config.get('include_patterns'),
            exclude_patterns=config.get('exclude_patterns'),
            sites=config.get('sites'),
            roles=config.get('roles'),
            network_only=config.get('network_only', False)
        )

        if not topology_data:
            return jsonify({
                'success': False,
                'error': 'No topology data found with current filters'
            }), 400

        # Create exporter and export
        exporter = RapidCMDBDrawioExporter()
        output_path = exporter.export_topology(
            topology_data,
            layout=config.get('layout', 'tree'),
            include_endpoints=not config.get('network_only', False)
        )

        # Return file
        return send_file(
            output_path,
            as_attachment=True,
            download_name=f"rapidcmdb-topology-{datetime.now().strftime('%Y%m%d')}.drawio",
            mimetype='application/xml'
        )

    except Exception as e:
        logger.error(f"Draw.io export error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@drawio_bp.route('/preview', methods=['POST'])
def preview_export():
    """Get preview information about the export"""
    try:
        config = request.get_json() or {}

        topology_data = build_topology_map(
            include_patterns=config.get('include_patterns'),
            exclude_patterns=config.get('exclude_patterns'),
            sites=config.get('sites'),
            roles=config.get('roles'),
            network_only=config.get('network_only', False)
        )

        device_count = len(topology_data)
        connection_count = sum(
            len(device_data.get('peers', {}))
            for device_data in topology_data.values()
        )

        return jsonify({
            'success': True,
            'preview': {
                'device_count': device_count,
                'connection_count': connection_count,
                'layout_options': ['tree', 'grid', 'balloon'],
                'filters_applied': {
                    'sites': config.get('sites', []),
                    'network_only': config.get('network_only', False)
                }
            }
        })

    except Exception as e:
        logger.error(f"Preview error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500