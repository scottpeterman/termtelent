# RapidCMDB

**Enterprise Network Discovery and Configuration Management Database**

RapidCMDB is a closed-source network infrastructure discovery and management platform designed for network engineers and operations teams. It provides automated device discovery, configuration management, and network topology visualization with a focus on scalability and multi-vendor support.

## Overview

RapidCMDB serves as a comprehensive network inventory and monitoring solution that automatically discovers, catalogs, and monitors network infrastructure. Built with modern web technologies and designed for enterprise-scale deployments, it integrates seamlessly with existing network management workflows.

### Core Capabilities

- **Automated Network Discovery**: SNMP-based scanning with intelligent device fingerprinting
- **Multi-Vendor Device Support**: Cisco, Juniper, Arista, HP, Fortinet, Palo Alto, and others
- **Configuration Management**: Automated collection, versioning, and change detection
- **Topology Visualization**: Interactive network maps with LLDP/CDP relationship discovery
- **Real-Time Monitoring**: Performance metrics, interface status, and environmental data
- **Enterprise Integration**: NetBox and LogicMonitor synchronization

### Technical Architecture

- **Backend**: Python Flask with SQLite/PostgreSQL database
- **Frontend**: Bootstrap 5 with real-time WebSocket updates
- **Discovery Engine**: Multi-threaded SNMP/SSH scanning with configurable concurrency
- **Data Processing**: NAPALM-based device interaction and normalized data structures
- **API**: RESTful endpoints for programmatic access and integration

## Installation & Deployment

### System Requirements

- **Operating System**: Linux, Windows, or macOS
- **Python**: 3.8 or higher
- **Memory**: 4GB RAM minimum (8GB+ recommended for large networks)
- **Storage**: 1GB available space (scales with network size)
- **Network Access**: SNMP (161/UDP) and SSH (22/TCP) to target devices

### Quick Start

```bash
# Extract RapidCMDB package
tar -xzf rapidcmdb-latest.tar.gz
cd rapidcmdb/

# Install dependencies
pip install -r requirements.txt

# Initialize database
python db_manager.py --init-schema

# Start the application
python app.py
```

The web interface will be available at `http://localhost:5000`

### Production Deployment

For production environments, consider:

- **Database**: Migrate from SQLite to PostgreSQL for better concurrency
- **Web Server**: Deploy behind nginx or Apache with SSL termination
- **Process Management**: Use systemd, supervisord, or Docker for service management
- **Backup Strategy**: Regular database backups and configuration exports

## Configuration

### Network Discovery

Configure target networks and credentials in the scanner interface:

```yaml
# Example discovery configuration
networks:
  - target: "192.168.1.0/24"
    communities: ["public", "private"]
    timeout: 4
    concurrency: 50

credentials:
  - name: "primary"
    username: "admin"
    password: "encrypted_password"
    enable_secret: "encrypted_enable"
```

### Data Collection

NAPALM-based collection supports multiple device types automatically:

- **Cisco IOS/IOS-XE/NX-OS**: Full feature support
- **Juniper Junos**: Configuration and operational data
- **Arista EOS**: Complete API integration
- **HP/Aruba**: Basic monitoring and configuration
- **Fortinet**: Security appliance support

### Retention Policies

Database retention is configurable per data type:

```sql
-- Example retention settings
INSERT INTO retention_policies (table_name, retention_days, keep_latest_count) VALUES
('collection_runs', 90, 5),      -- Keep 90 days, minimum 5 latest
('device_configs', 365, 10),     -- Keep 1 year, minimum 10 versions
('environment_data', 30, 10);    -- Keep 30 days, minimum 10 samples
```

## Features

### Discovery Pipeline

1. **Network Scanning**: Parallel SNMP discovery with device fingerprinting
2. **Device Classification**: Vendor, model, and capability detection
3. **Topology Mapping**: LLDP/CDP neighbor discovery and relationship building
4. **Data Collection**: NAPALM-based configuration and operational data gathering
5. **Database Storage**: Normalized storage with automatic change detection

### Web Dashboard

- **Device Inventory**: Searchable device catalog with filtering and export
- **Network Topology**: Interactive topology viewer with layout algorithms
- **Configuration Management**: Version control with diff visualization
- **Monitoring**: Real-time device health and performance metrics
- **Reporting**: Automated report generation and scheduling

### API Access

RESTful API for programmatic access:

```bash
# Get device inventory
curl -X GET "http://localhost:5000/api/devices"

# Export topology data
curl -X GET "http://localhost:5000/api/topology/export/json?sites=FRC&network_only=true"

# Search configurations
curl -X POST "http://localhost:5000/api/search/comprehensive" \
  -H "Content-Type: application/json" \
  -d '{"search": "interface GigabitEthernet", "category": "config"}'
```

## Integration

### NetBox Synchronization

Bidirectional sync with NetBox IPAM/DCIM:

- Import device inventory from NetBox
- Export discovered devices to NetBox
- Synchronize IP address assignments
- Update device specifications and locations

### LogicMonitor Integration

Device and monitoring data exchange:

- Import device lists from LogicMonitor
- Export performance baselines
- Synchronize alert thresholds
- Cross-reference monitoring data

### External APIs

Standard protocols and formats:

- **SNMP v1/v2c/v3**: Device discovery and monitoring
- **SSH**: Secure device access and configuration collection
- **REST APIs**: Modern integration with network management platforms
- **Export Formats**: CSV, JSON, XML, DrawIO for data portability

## Scaling & Performance

### Tested Capacity

- **Devices**: Tested with 20,000+ devices in single deployment
- **Collection Rate**: ~100 devices per minute with standard hardware
- **Database Size**: Approximately 10KB per device (200MB for 20K devices)
- **Query Performance**: Sub-second response for standard operations

### Performance Optimization

- **Database Indexing**: Optimized indexes for common query patterns
- **Concurrent Collection**: Parallel NAPALM sessions with rate limiting
- **Memory Management**: Efficient data structures and caching strategies
- **Network Optimization**: Connection pooling and batch operations

### Hardware Recommendations

| Network Size | CPU Cores | RAM | Storage | Notes |
|--------------|-----------|-----|---------|-------|
| < 1,000 devices | 2 cores | 4GB | 50GB | Development/small office |
| 1,000 - 5,000 | 4 cores | 8GB | 100GB | Medium enterprise |
| 5,000 - 15,000 | 8 cores | 16GB | 200GB | Large enterprise |
| 15,000+ devices | 16+ cores | 32GB+ | 500GB+ | Service provider scale |

## Security Considerations

### Credential Management

- **Encryption**: AES-256 encryption for stored credentials
- **Access Control**: Role-based access to credential repositories
- **Rotation**: Automated credential rotation capabilities
- **Audit Trail**: Complete logging of credential usage

### Network Security

- **Firewall Rules**: Documented port requirements for device access
- **VPN Integration**: Support for VPN-based network access
- **Certificate Management**: SSL/TLS certificate validation
- **Network Segmentation**: Respect for network security boundaries

### Data Protection

- **Database Encryption**: Optional database-level encryption
- **Backup Security**: Encrypted backup storage options
- **Data Retention**: Configurable data lifecycle management
- **Export Controls**: Controlled data export with audit logging

## Troubleshooting

### Common Issues

**Discovery Problems:**
- Verify SNMP community strings and network connectivity
- Check firewall rules for UDP 161 and TCP 22
- Validate credential configuration and device access

**Collection Failures:**
- Review NAPALM driver compatibility with target devices
- Check SSH key authentication and enable passwords
- Monitor collection logs for specific error messages

**Performance Issues:**
- Adjust discovery concurrency based on network capacity
- Monitor database query performance and index usage
- Review memory usage during large collection runs

### Logging & Diagnostics

Log files location: `logs/`
- `app.log`: Main application log
- `discovery.log`: Network discovery operations
- `collection.log`: NAPALM collection activities
- `api.log`: API access and operations

Increase log verbosity with `LOG_LEVEL=DEBUG` environment variable.

## Support & Licensing

### Commercial License

RapidCMDB is proprietary software requiring a commercial license for use. Contact licensing for:

- **Evaluation Licenses**: 30-day trial deployments
- **Enterprise Licenses**: Production deployment rights
- **Support Contracts**: Professional support and maintenance
- **Custom Development**: Feature development and integration services

### Documentation

- **User Guide**: Detailed operational procedures
- **API Reference**: Complete REST API documentation
- **Integration Guide**: Third-party system integration
- **Best Practices**: Deployment and operational recommendations

### Professional Services

Available services include:

- **Implementation**: Guided deployment and configuration
- **Training**: Administrator and operator training programs
- **Custom Integration**: Bespoke integration development
- **Performance Optimization**: Deployment tuning and optimization

---

**Note**: RapidCMDB is designed to complement TerminalTelemetry (open source) for comprehensive network management workflows. Contact sales for licensing information and enterprise deployment assistance.