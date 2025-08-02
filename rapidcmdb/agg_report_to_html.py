#!/usr/bin/env python3
"""
Enhanced Interactive HTML Network Report Generator
Creates a portable HTML report with Chart.js visualizations and working export capabilities
"""

import json
import sys
from pathlib import Path
import argparse
import yaml
from datetime import datetime
import base64


class NetworkReportGenerator:
    """Generate interactive HTML reports from network device data"""

    def __init__(self, config_path="config/vendor_fingerprints.yaml"):
        self.vendors = {}
        self.vendor_config = {}
        self.load_fingerprints(config_path)

    def load_fingerprints(self, config_path):
        """Load vendor fingerprint configuration"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.vendor_config = yaml.safe_load(f)
            self.vendors = self.vendor_config.get('vendors', {})
            print(f"✓ Loaded fingerprints for {len(self.vendors)} vendors")
        except Exception as e:
            print(f"Warning: Could not load fingerprints: {e}")
            self.vendors = {}
            self.vendor_config = {}

    def get_vendor_display_name(self, vendor_key):
        """Get the proper display name for a vendor"""
        if vendor_key in self.vendors:
            return self.vendors[vendor_key].get('display_name', vendor_key.title())
        return vendor_key.title() if vendor_key else 'Unknown'

    def get_vendor_color_mapping(self):
        """Generate consistent color mapping for vendors based on fingerprint file"""
        vendor_keys = list(self.vendors.keys())
        # Add common vendors that might not be in fingerprints
        common_vendors = ['unknown', '', 'cisco', 'hp', 'dell', 'aruba', 'fortinet', 'palo_alto']
        all_vendors = vendor_keys + [v for v in common_vendors if v not in vendor_keys]

        colors = [
            '#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
            '#06b6d4', '#84cc16', '#f97316', '#ec4899', '#6366f1',
            '#14b8a6', '#f97545', '#8b5a2b', '#059669', '#7c3aed',
            '#db2777', '#0891b2', '#65a30d', '#ea580c', '#a21caf'
        ]

        return {vendor: colors[i % len(colors)] for i, vendor in enumerate(all_vendors)}

    def analyze_data(self, data):
        """Analyze the network data to extract insights"""
        devices = data.get('devices', {})
        sessions = data.get('sessions', [])
        statistics = data.get('statistics', {})

        analysis = {
            'summary': {
                'total_devices': len(devices),
                'total_sessions': len(sessions),
                'devices_with_sysdesc': sum(1 for d in devices.values() if d.get('sys_descr')),
                'devices_with_snmp': sum(1 for d in devices.values() if d.get('snmp_data_by_ip')),
                'last_updated': data.get('last_updated', 'Unknown'),
                'version': data.get('version', 'Unknown'),
                'fingerprint_version': self.vendor_config.get('version', 'Unknown'),
                'total_fingerprints': len(self.vendors)
            },
            'vendor_breakdown': self.enhance_vendor_breakdown(statistics.get('vendor_breakdown', {})),
            'type_breakdown': statistics.get('type_breakdown', {}),
            'subnet_breakdown': statistics.get('devices_per_subnet', {}),
            'confidence_analysis': self.analyze_confidence(devices),
            'detection_methods': self.analyze_detection_methods(devices),
            'top_subnets': self.get_top_subnets(statistics.get('devices_per_subnet', {})),
            'snmp_coverage': self.analyze_snmp_coverage(devices),
            'scan_timeline': self.analyze_scan_timeline(sessions),
            'device_details': self.get_device_samples(devices),
            'vendor_fingerprint_analysis': self.analyze_vendor_fingerprints(devices),
            'management_interfaces': self.analyze_management_interfaces(devices)
        }

        return analysis

    def enhance_vendor_breakdown(self, vendor_breakdown):
        """Enhance vendor breakdown with display names and fingerprint data"""
        enhanced = {}
        for vendor_key, count in vendor_breakdown.items():
            display_name = self.get_vendor_display_name(vendor_key)
            enhanced[vendor_key] = {
                'count': count,
                'display_name': display_name,
                'enterprise_oid': self.vendors.get(vendor_key, {}).get('enterprise_oid', ''),
                'device_types': self.vendors.get(vendor_key, {}).get('device_types', [])
            }
        return enhanced

    def analyze_confidence(self, devices):
        """Analyze confidence score distribution"""
        confidence_ranges = {'0-20': 0, '21-40': 0, '41-60': 0, '61-80': 0, '81-100': 0}

        for device in devices.values():
            score = device.get('confidence_score', 0)
            if score <= 20:
                confidence_ranges['0-20'] += 1
            elif score <= 40:
                confidence_ranges['21-40'] += 1
            elif score <= 60:
                confidence_ranges['41-60'] += 1
            elif score <= 80:
                confidence_ranges['61-80'] += 1
            else:
                confidence_ranges['81-100'] += 1

        return confidence_ranges

    def analyze_detection_methods(self, devices):
        """Analyze detection method distribution"""
        methods = {}
        for device in devices.values():
            method = device.get('detection_method', 'unknown')
            methods[method] = methods.get(method, 0) + 1
        return methods

    def get_top_subnets(self, subnet_data, limit=10):
        """Get top subnets by device count"""
        return dict(sorted(subnet_data.items(), key=lambda x: x[1], reverse=True)[:limit])

    def analyze_snmp_coverage(self, devices):
        """Analyze SNMP data coverage"""
        total_devices = len(devices)
        with_snmp = sum(1 for d in devices.values() if d.get('snmp_data_by_ip'))
        return {
            'with_snmp': with_snmp,
            'without_snmp': total_devices - with_snmp,
            'coverage_percent': round((with_snmp / total_devices) * 100, 1) if total_devices > 0 else 0
        }

    def analyze_scan_timeline(self, sessions):
        """Analyze scanning activity over time"""
        timeline = {}
        for session in sessions[-50:]:  # Last 50 sessions for timeline
            timestamp = session.get('timestamp', '')
            if timestamp:
                date = timestamp.split('T')[0]  # Extract date part
                timeline[date] = timeline.get(date, 0) + session.get('devices_found', 0)
        return dict(sorted(timeline.items()))

    def analyze_vendor_fingerprints(self, devices):
        """Analyze fingerprint coverage by vendor"""
        fingerprint_analysis = {}
        for device in devices.values():
            vendor = device.get('vendor', 'unknown')
            if vendor not in fingerprint_analysis:
                fingerprint_analysis[vendor] = {
                    'total_devices': 0,
                    'with_fingerprints': 0,
                    'avg_confidence': 0
                }

            fingerprint_analysis[vendor]['total_devices'] += 1
            confidence = device.get('confidence_score', 0)
            fingerprint_analysis[vendor]['avg_confidence'] += confidence

            if device.get('snmp_data_by_ip'):
                fingerprint_analysis[vendor]['with_fingerprints'] += 1

        # Calculate averages
        for vendor_data in fingerprint_analysis.values():
            if vendor_data['total_devices'] > 0:
                vendor_data['avg_confidence'] = round(
                    vendor_data['avg_confidence'] / vendor_data['total_devices'], 1
                )

        return fingerprint_analysis

    def analyze_management_interfaces(self, devices):
        """Analyze management interface detection"""
        mgmt_types = {}
        for device in devices.values():
            device_type = device.get('device_type', '')
            vendor = device.get('vendor', '')

            if any(keyword in device_type.lower() for keyword in ['management', 'bmc', 'ilo', 'idrac', 'cimc']):
                key = f"{vendor}_{device_type}"
                mgmt_types[key] = mgmt_types.get(key, 0) + 1

        return mgmt_types

    def get_device_samples(self, devices, limit=10):
        """Get sample devices for detailed view"""
        samples = []
        count = 0
        for device_id, device in devices.items():
            if count >= limit:
                break
            if device.get('sys_descr') and device.get('vendor'):
                samples.append({
                    'id': device_id,
                    'ip': device.get('primary_ip', ''),
                    'vendor': self.get_vendor_display_name(device.get('vendor', '')),
                    'vendor_key': device.get('vendor', ''),
                    'type': device.get('device_type', ''),
                    'model': device.get('model', ''),
                    'sys_descr': device.get('sys_descr', '')[:100] + '...' if len(
                        device.get('sys_descr', '')) > 100 else device.get('sys_descr', ''),
                    'confidence': device.get('confidence_score', 0)
                })
                count += 1
        return samples

    def generate_html_report(self, data, output_file):
        """Generate the HTML report"""
        analysis = self.analyze_data(data)
        vendor_colors = self.get_vendor_color_mapping()

        # Prepare data for charts
        vendor_chart_data = []
        vendor_chart_labels = []
        vendor_chart_colors = []

        for vendor_key, vendor_data in analysis['vendor_breakdown'].items():
            vendor_chart_labels.append(vendor_data['display_name'])
            vendor_chart_data.append(vendor_data['count'])
            vendor_chart_colors.append(vendor_colors.get(vendor_key, '#64748b'))

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Network Device Report - {analysis['summary']['last_updated'].split('T')[0]}</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
    <style>
        :root {{
            --primary-color: #2563eb;
            --secondary-color: #f1f5f9;
            --accent-color: #10b981;
            --warning-color: #f59e0b;
            --danger-color: #ef4444;
            --text-color: #1e293b;
            --border-color: #e2e8f0;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: var(--text-color);
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}

        .header {{
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            text-align: center;
        }}

        .header h1 {{
            color: var(--primary-color);
            font-size: 2.5em;
            margin-bottom: 10px;
            font-weight: 300;
        }}

        .header .subtitle {{
            color: #64748b;
            font-size: 1.1em;
            margin-bottom: 5px;
        }}

        .fingerprint-info {{
            background: #f0f9ff;
            border: 1px solid #0ea5e9;
            border-radius: 8px;
            padding: 10px;
            margin-top: 15px;
            font-size: 0.9em;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .stat-card {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 8px 20px rgba(0,0,0,0.1);
            text-align: center;
            transition: transform 0.3s ease;
        }}

        .stat-card:hover {{
            transform: translateY(-5px);
        }}

        .stat-number {{
            font-size: 2.5em;
            font-weight: bold;
            margin-bottom: 10px;
        }}

        .stat-label {{
            color: #64748b;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        .chart-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .chart-card {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 8px 20px rgba(0,0,0,0.1);
        }}

        .chart-card.wide {{
            grid-column: 1 / -1;
        }}

        .chart-title {{
            font-size: 1.3em;
            font-weight: 600;
            margin-bottom: 20px;
            color: var(--text-color);
            text-align: center;
        }}

        .chart-container {{
            position: relative;
            height: 300px;
        }}

        .chart-container.tall {{
            height: 400px;
        }}

        .table-card {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 8px 20px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}

        .device-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}

        .device-table th, .device-table td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}

        .device-table th {{
            background: var(--secondary-color);
            font-weight: 600;
            color: var(--text-color);
        }}

        .device-table tr:hover {{
            background: #f8fafc;
        }}

        .confidence-badge {{
            padding: 4px 8px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: 600;
        }}

        .confidence-high {{
            background: #dcfce7;
            color: #166534;
        }}

        .confidence-medium {{
            background: #fef3c7;
            color: #92400e;
        }}

        .confidence-low {{
            background: #fecaca;
            color: #991b1b;
        }}

        .export-section {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 8px 20px rgba(0,0,0,0.1);
            text-align: center;
            margin-bottom: 20px;
        }}

        .export-btn {{
            background: var(--primary-color);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 1em;
            cursor: pointer;
            margin: 0 10px;
            transition: background-color 0.3s ease;
        }}

        .export-btn:hover {{
            background: #1d4ed8;
        }}

        .export-btn:disabled {{
            background: #94a3b8;
            cursor: not-allowed;
        }}

        .footer {{
            text-align: center;
            color: white;
            margin-top: 30px;
            opacity: 0.8;
        }}

        .vendor-legend {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 15px;
            justify-content: center;
        }}

        .vendor-legend-item {{
            display: flex;
            align-items: center;
            gap: 5px;
            font-size: 0.8em;
        }}

        .vendor-color {{
            width: 12px;
            height: 12px;
            border-radius: 2px;
        }}

        @media (max-width: 768px) {{
            .chart-grid {{
                grid-template-columns: 1fr;
            }}

            .stats-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}

            .header h1 {{
                font-size: 2em;
            }}

            .export-btn {{
                margin: 5px;
                padding: 10px 20px;
            }}
        }}

        @media print {{
            body {{ background: white !important; }}
            .container {{ max-width: none !important; }}
            .export-section {{ display: none !important; }}
            .chart-grid {{ grid-template-columns: 1fr 1fr !important; }}
            .chart-card {{ break-inside: avoid; page-break-inside: avoid; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌐 Network Device Report</h1>
            <p class="subtitle">Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
            <p class="subtitle">Data Version: {analysis['summary']['version']} | Last Updated: {analysis['summary']['last_updated']}</p>
            <div class="fingerprint-info">
                📋 Using {analysis['summary']['total_fingerprints']} vendor fingerprints (v{analysis['summary']['fingerprint_version']})
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number" style="color: var(--primary-color);">{analysis['summary']['total_devices']:,}</div>
                <div class="stat-label">Total Devices</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" style="color: var(--accent-color);">{analysis['summary']['devices_with_sysdesc']:,}</div>
                <div class="stat-label">With System Description</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" style="color: var(--warning-color);">{analysis['summary']['devices_with_snmp']:,}</div>
                <div class="stat-label">With SNMP Data</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" style="color: var(--danger-color);">{analysis['summary']['total_sessions']:,}</div>
                <div class="stat-label">Scan Sessions</div>
            </div>
        </div>

        <div class="chart-grid">
            <div class="chart-card">
                <h3 class="chart-title">📊 Vendor Distribution</h3>
                <div class="chart-container">
                    <canvas id="vendorChart"></canvas>
                </div>
                <div class="vendor-legend" id="vendorLegend"></div>
            </div>

            <div class="chart-card">
                <h3 class="chart-title">🏷️ Device Types</h3>
                <div class="chart-container">
                    <canvas id="typeChart"></canvas>
                </div>
            </div>

            <div class="chart-card">
                <h3 class="chart-title">🎯 Confidence Scores</h3>
                <div class="chart-container">
                    <canvas id="confidenceChart"></canvas>
                </div>
            </div>

            <div class="chart-card">
                <h3 class="chart-title">🔍 Detection Methods</h3>
                <div class="chart-container">
                    <canvas id="detectionChart"></canvas>
                </div>
            </div>

            <div class="chart-card">
                <h3 class="chart-title">🌐 Top Subnets</h3>
                <div class="chart-container">
                    <canvas id="subnetChart"></canvas>
                </div>
            </div>

            <div class="chart-card">
                <h3 class="chart-title">📈 Scan Timeline</h3>
                <div class="chart-container">
                    <canvas id="timelineChart"></canvas>
                </div>
            </div>

            <div class="chart-card wide">
                <h3 class="chart-title">🔧 Management Interfaces</h3>
                <div class="chart-container tall">
                    <canvas id="managementChart"></canvas>
                </div>
            </div>
        </div>

        <div class="table-card">
            <h3 class="chart-title">🔍 Sample Device Details</h3>
            <table class="device-table">
                <thead>
                    <tr>
                        <th>Device ID</th>
                        <th>IP Address</th>
                        <th>Vendor</th>
                        <th>Type</th>
                        <th>Model</th>
                        <th>Confidence</th>
                        <th>Description</th>
                    </tr>
                </thead>
                <tbody>
                    {self.generate_device_table_rows(analysis['device_details'])}
                </tbody>
            </table>
        </div>

        <div class="export-section">
            <h3 class="chart-title">💾 Export Options</h3>
            <button class="export-btn" onclick="exportReport('png')" id="pngBtn">📸 Export as PNG</button>
            <button class="export-btn" onclick="exportReport('pdf')" id="pdfBtn">📄 Save as PDF</button>
            <button class="export-btn" onclick="exportData()">📊 Download Summary CSV</button>
            <button class="export-btn" onclick="exportDetailedData()">📋 Download Detailed CSV</button>
            <div id="exportStatus" style="margin-top: 10px; font-size: 0.9em;"></div>
        </div>

        <div class="footer">
            <p>Generated by RapidCMDB Network Scanner | {len(self.vendors)} vendor fingerprints loaded</p>
        </div>
    </div>

    <script>
    
        // Chart configuration
        Chart.defaults.responsive = true;
        Chart.defaults.maintainAspectRatio = false;

        // Color mapping from Python
        const vendorColors = {json.dumps(vendor_colors)};

        // Vendor Distribution Chart with dynamic colors
        const vendorData = {json.dumps([(k, v['display_name'], v['count']) for k, v in analysis['vendor_breakdown'].items()][:10])};
        const vendorChart = new Chart(document.getElementById('vendorChart'), {{
            type: 'doughnut',
            data: {{
                labels: vendorData.map(item => item[1]),
                datasets: [{{
                    data: vendorData.map(item => item[2]),
                    backgroundColor: vendorData.map(item => vendorColors[item[0]] || '#64748b'),
                    borderWidth: 2,
                    borderColor: '#fff'
                }}]
            }},
            options: {{
                plugins: {{
                    legend: {{ display: false }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = ((context.parsed * 100) / total).toFixed(1);
                                return context.label + ': ' + context.parsed + ' (' + percentage + '%)';
                            }}
                        }}
                    }}
                }}
            }}
        }});

        // Create vendor legend
        const vendorLegend = document.getElementById('vendorLegend');
        vendorData.forEach(item => {{
            const legendItem = document.createElement('div');
            legendItem.className = 'vendor-legend-item';
            legendItem.innerHTML = `
                <div class="vendor-color" style="background-color: ${{vendorColors[item[0]] || '#64748b'}}"></div>
                <span>${{item[1]}} (${{item[2]}})</span>
            `;
            vendorLegend.appendChild(legendItem);
        }});

        // Device Types Chart
        const typeData = {json.dumps(list(analysis['type_breakdown'].items())[:8])};
        new Chart(document.getElementById('typeChart'), {{
            type: 'bar',
            data: {{
                labels: typeData.map(item => item[0].replace(/_/g, ' ')),
                datasets: [{{
                    data: typeData.map(item => item[1]),
                    backgroundColor: '#10b981',
                    borderRadius: 5
                }}]
            }},
            options: {{
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ 
                        ticks: {{ 
                            maxRotation: 45,
                            minRotation: 45
                        }}
                    }},
                    y: {{
                        beginAtZero: true,
                        ticks: {{ precision: 0 }}
                    }}
                }}
            }}
        }});

        // Confidence Scores Chart
        const confidenceData = {json.dumps(list(analysis['confidence_analysis'].items()))};
        new Chart(document.getElementById('confidenceChart'), {{
            type: 'pie',
            data: {{
                labels: confidenceData.map(item => item[0] + '%'),
                datasets: [{{
                    data: confidenceData.map(item => item[1]),
                    backgroundColor: ['#ef4444', '#f59e0b', '#8b5cf6', '#06b6d4', '#10b981'],
                    borderWidth: 2,
                    borderColor: '#fff'
                }}]
            }},
            options: {{
                plugins: {{ 
                    legend: {{ position: 'bottom' }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = ((context.parsed * 100) / total).toFixed(1);
                                return context.label + ': ' + context.parsed + ' devices (' + percentage + '%)';
                            }}
                        }}
                    }}
                }}
            }}
        }});

        // Detection Methods Chart
        const detectionData = {json.dumps(list(analysis['detection_methods'].items()))};
        new Chart(document.getElementById('detectionChart'), {{
            type: 'polarArea',
            data: {{
                labels: detectionData.map(item => item[0].replace(/_/g, ' ')),
                datasets: [{{
                    data: detectionData.map(item => item[1]),
                    backgroundColor: ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'].slice(0, detectionData.length)
                }}]
            }},
            options: {{
                plugins: {{ legend: {{ position: 'bottom' }} }}
            }}
        }});

        // Top Subnets Chart
        const subnetData = {json.dumps(list(analysis['top_subnets'].items()))};
        new Chart(document.getElementById('subnetChart'), {{
            type: 'bar',
            data: {{
                labels: subnetData.map(item => item[0]),
                datasets: [{{
                    data: subnetData.map(item => item[1]),
                    backgroundColor: '#2563eb',
                    borderRadius: 5
                }}]
            }},
            options: {{
                plugins: {{ legend: {{ display: false }} }},
                indexAxis: 'y',
                scales: {{
                    x: {{
                        beginAtZero: true,
                        ticks: {{ precision: 0 }}
                    }}
                }}
            }}
        }});

        // Timeline Chart
        const timelineData = {json.dumps(list(analysis['scan_timeline'].items()))};
        new Chart(document.getElementById('timelineChart'), {{
            type: 'line',
            data: {{
                labels: timelineData.map(item => item[0]),
                datasets: [{{
                    label: 'Devices Found',
                    data: timelineData.map(item => item[1]),
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    fill: true,
                    tension: 0.4
                }}]
            }},
            options: {{
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ 
                        ticks: {{ maxRotation: 45 }}
                    }},
                    y: {{
                        beginAtZero: true,
                        ticks: {{ precision: 0 }}
                    }}
                }}
            }}
        }});

        // Management Interfaces Chart
        const managementData = {json.dumps(list(analysis['management_interfaces'].items()))};
        if (managementData.length > 0) {{
            new Chart(document.getElementById('managementChart'), {{
                type: 'bar',
                data: {{
                    labels: managementData.map(item => item[0].replace(/_/g, ' ')),
                    datasets: [{{
                        label: 'Management Interfaces',
                        data: managementData.map(item => item[1]),
                        backgroundColor: '#8b5cf6',
                        borderRadius: 5
                    }}]
                }},
                options: {{
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{
                        x: {{ 
                            ticks: {{ 
                                maxRotation: 45,
                                minRotation: 45
                            }}
                        }},
                        y: {{
                            beginAtZero: true,
                            ticks: {{ precision: 0 }}
                        }}
                    }}
                }}
            }});
        }} else {{
            document.getElementById('managementChart').parentElement.innerHTML = '<p style="text-align: center; color: #64748b; padding: 50px;">No management interfaces detected</p>';
        }}

        // Export functions
        function updateExportStatus(message, isError = false) {{
            const status = document.getElementById('exportStatus');
            status.textContent = message;
            status.style.color = isError ? '#ef4444' : '#10b981';
            setTimeout(() => status.textContent = '', 3000);
        }}

        function exportReport(format) {{
            const btn = document.getElementById(format + 'Btn');
            btn.disabled = true;
            updateExportStatus('Generating ' + format.toUpperCase() + '...');

            if (format === 'png') {{
                html2canvas(document.body, {{
                    scale: 1,
                    useCORS: true,
                    allowTaint: true,
                    backgroundColor: '#ffffff'
                }}).then(canvas => {{
                    const link = document.createElement('a');
                    link.download = 'network-report-' + new Date().toISOString().split('T')[0] + '.png';
                    link.href = canvas.toDataURL('image/png');
                    link.click();
                    updateExportStatus('PNG exported successfully!');
                    btn.disabled = false;
                }}).catch(error => {{
                    updateExportStatus('PNG export failed: ' + error.message, true);
                    btn.disabled = false;
                }});
            }} else if (format === 'pdf') {{
                try {{
                    window.print();
                    updateExportStatus('PDF export initiated');
                    btn.disabled = false;
                }} catch (error) {{
                    updateExportStatus('PDF export failed: ' + error.message, true);
                    btn.disabled = false;
                }}
            }}
        }}

        function exportData() {{
            try {{
                const csvData = {json.dumps(self.generate_csv_export_data(analysis))};
                const blob = new Blob([csvData], {{ type: 'text/csv;charset=utf-8;' }});
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = 'network-report-data-' + new Date().toISOString().split('T')[0] + '.csv';
                link.click();
                window.URL.revokeObjectURL(url);
                updateExportStatus('CSV data exported successfully!');
            }} catch (error) {{
                updateExportStatus('CSV export failed: ' + error.message, true);
            }}
        }}
        function exportDetailedData() {{
    try {{
        // Generate detailed device data CSV
        const deviceData = {json.dumps([{
            'device_id': d['id'], 
            'ip': d['ip'], 
            'vendor_key': d['vendor_key'], 
            'vendor_display': d['vendor'], 
            'type': d['type'], 
            'model': d['model'], 
            'confidence': d['confidence']
        } for d in analysis['device_details']])};
        
        const lines = ["Device_ID,IP_Address,Vendor_Key,Vendor_Display,Device_Type,Model,Confidence_Score"];
        
        deviceData.forEach(device => {{
            const deviceType = device.type.replace(/_/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase());
            lines.push(`"${{device.device_id}}",${{device.ip}},${{device.vendor_key}},"${{device.vendor_display}}","${{deviceType}}","${{device.model}}",${{device.confidence}}`);
        }});
        
        const csvData = lines.join('\\n');
        const blob = new Blob([csvData], {{ type: 'text/csv;charset=utf-8;' }});
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'network-devices-detailed-' + new Date().toISOString().split('T')[0] + '.csv';
        link.click();
        window.URL.revokeObjectURL(url);
        updateExportStatus('Detailed CSV exported successfully!');
    }} catch (error) {{
        updateExportStatus('Detailed CSV export failed: ' + error.message, true);
    }}
}}
    </script>
</body>
</html>"""

        # Write HTML file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"✓ Interactive HTML report generated: {output_file}")
        return True

    def generate_device_table_rows(self, devices):
        """Generate HTML table rows for device details"""
        rows = []
        for device in devices:
            confidence = device['confidence']
            if confidence >= 80:
                confidence_class = "confidence-high"
            elif confidence >= 50:
                confidence_class = "confidence-medium"
            else:
                confidence_class = "confidence-low"

            rows.append(f"""
                <tr>
                    <td><strong>{device['id']}</strong></td>
                    <td>{device['ip']}</td>
                    <td>{device['vendor']}</td>
                    <td>{device['type'].replace('_', ' ').title()}</td>
                    <td>{device['model']}</td>
                    <td><span class="confidence-badge {confidence_class}">{confidence}%</span></td>
                    <td title="{device['sys_descr']}">{device['sys_descr']}</td>
                </tr>
            """)
        return ''.join(rows)

    def generate_csv_export_data(self, analysis):
        """Generate CSV data for export"""
        csv_lines = ["Category,Key,Name,Count,Percentage,Enterprise_OID"]

        total_devices = analysis['summary']['total_devices']

        # Add vendor data with fingerprint info
        for vendor_key, vendor_data in analysis['vendor_breakdown'].items():
            percentage = round((vendor_data['count'] / total_devices) * 100, 2) if total_devices > 0 else 0
            enterprise_oid = vendor_data.get('enterprise_oid', '')
            # Escape commas in names by wrapping in quotes
            display_name = f'"{vendor_data["display_name"]}"' if ',' in vendor_data['display_name'] else vendor_data[
                'display_name']
            csv_lines.append(f"Vendor,{vendor_key},{display_name},{vendor_data['count']},{percentage},{enterprise_oid}")

        # Add device type data
        for device_type, count in analysis['type_breakdown'].items():
            percentage = round((count / total_devices) * 100, 2) if total_devices > 0 else 0
            display_type = device_type.replace('_', ' ').title()
            csv_lines.append(f"Device Type,{device_type},{display_type},{count},{percentage},")

        return '\n'.join(csv_lines)


def generate_html_report(input_file, output_file=None, config_path="config/vendor_fingerprints.yaml"):
    """Generate HTML report from aggregate JSON data"""

    # Read JSON data
    try:
        print(f"Reading aggregate report: {input_file}")
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading file: {e}")
        return False

    # Generate output filename if not provided
    if not output_file:
        input_path = Path(input_file)
        output_file = input_path.with_suffix('.html')

    # Create report generator and generate HTML
    generator = NetworkReportGenerator(config_path)
    return generator.generate_html_report(data, output_file)


def main():
    parser = argparse.ArgumentParser(
        description='Generate interactive HTML network device report with working exports',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python html_report_generator.py testagg.json
  python html_report_generator.py report.json -o network_report.html
  python html_report_generator.py data.json --config custom_fingerprints.yaml

Enhanced Features:
  ✓ Dynamic vendor categorization from YAML fingerprints
  ✓ Working PNG and PDF export functionality
  ✓ Management interface detection (iDRAC, iLO, CIMC)
  ✓ Consistent color mapping across charts
  ✓ Enhanced error handling and status updates
  ✓ Mobile-responsive design
        """
    )

    parser.add_argument('input_file', help='Input aggregate report JSON file')
    parser.add_argument('-o', '--output', help='Output HTML file (default: input_file.html)')
    parser.add_argument('--config', default='config/vendor_fingerprints.yaml',
                        help='Path to vendor fingerprints YAML file')

    args = parser.parse_args()

    # Validate input file
    if not Path(args.input_file).exists():
        print(f"Error: Input file '{args.input_file}' does not exist.")
        sys.exit(1)

    # Generate report
    success = generate_html_report(args.input_file, args.output, args.config)

    if success:
        print("\\n🎉 Enhanced HTML report generated successfully!")
        print("\\nNew features:")
        print("  📊 Dynamic vendor categorization from fingerprint YAML")
        print("  💾 Working PNG and PDF export functionality")
        print("  🔧 Management interface detection and analysis")
        print("  🎨 Consistent color mapping and enhanced UI")
        print("  📱 Mobile-responsive design")
        print("\\nOpen the HTML file in your browser to view the enhanced report!")
    else:
        print("❌ Failed to generate HTML report")
        sys.exit(1)


if __name__ == "__main__":
    main()