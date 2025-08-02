-- NAPALM Network Device CMDB Schema for SQLite
-- Designed for multi-vendor network infrastructure management
-- Best practices implementation with proper constraints and data integrity

-- Enable foreign key constraints and other pragmas for data integrity
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA temp_store = MEMORY;
PRAGMA mmap_size = 268435456;

-- Main device inventory table
CREATE TABLE devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_key TEXT NOT NULL UNIQUE, -- Stable identifier: hash(vendor|serial|model)
    device_name TEXT NOT NULL UNIQUE, -- Network naming convention identifier
    hostname TEXT, -- Device's configured hostname
    fqdn TEXT, -- Fully qualified domain name
    vendor TEXT NOT NULL, -- Cisco, Juniper, Arista, etc.
    model TEXT, -- Device model number
    serial_number TEXT NOT NULL, -- Hardware serial number
    os_version TEXT, -- Operating system version
    uptime REAL, -- Uptime in seconds
    first_discovered DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_updated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    site_code TEXT NOT NULL, -- Location identifier (e.g., 'FRC', 'USC')
    device_role TEXT NOT NULL, -- core, access, distribution, firewall, router, etc.
    notes TEXT
    

);

-- Device IP addresses table (one-to-many relationship)
CREATE TABLE device_ips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    ip_address TEXT NOT NULL,
    ip_type TEXT NOT NULL, -- management, loopback, vlan, secondary, virtual
    interface_name TEXT, -- Which interface this IP belongs to
    subnet_mask TEXT, -- CIDR or dotted decimal
    vlan_id INTEGER,
    is_primary BOOLEAN NOT NULL DEFAULT 0, -- Only one primary IP per device
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT unique_ip_address UNIQUE(ip_address),
    CONSTRAINT check_ip_type_valid CHECK (ip_type IN ('management', 'loopback', 'vlan', 'secondary', 'virtual', 'hsrp', 'vrrp')),
    CONSTRAINT check_vlan_id_valid CHECK (vlan_id IS NULL OR (vlan_id >= 1 AND vlan_id <= 4094)),
    CONSTRAINT check_ip_format CHECK (
        ip_address GLOB '[0-9]*.[0-9]*.[0-9]*.[0-9]*' OR 
        ip_address GLOB '*:*:*'
    )
);

-- Collection runs tracking
CREATE TABLE collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    collection_ip TEXT NOT NULL, -- Which IP was used for this collection
    collection_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    success BOOLEAN NOT NULL,
    credential_used TEXT, -- Which credential set was successful
    errors TEXT, -- JSON array of errors encountered
    collection_duration REAL, -- Collection time in seconds
    methods_collected TEXT, -- JSON array of successfully collected NAPALM methods
    napalm_driver TEXT, -- Driver used (ios, eos, junos, etc.)
    collector_version TEXT, -- Version of collection script/tool
    
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT check_collection_duration CHECK (collection_duration IS NULL OR collection_duration >= 0),
    CONSTRAINT check_napalm_driver CHECK (napalm_driver IN ('ios', 'eos', 'junos', 'nxos', 'iosxr', 'vyos', 'fortios', 'panos'))
);

-- Interface inventory
CREATE TABLE interfaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    collection_run_id INTEGER NOT NULL,
    interface_name TEXT NOT NULL,
    interface_type TEXT NOT NULL, -- Physical, VLAN, Loopback, etc.
    admin_status TEXT NOT NULL, -- enabled/disabled
    oper_status TEXT NOT NULL, -- up/down
    description TEXT,
    mac_address TEXT, -- Normalized format (XX:XX:XX:XX:XX:XX)
    speed REAL, -- Speed in Mbps
    mtu INTEGER,
    last_flapped REAL, -- Seconds since last state change
    duplex TEXT, -- full, half, auto
    vlan_id INTEGER,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT check_interface_name_not_empty CHECK (TRIM(interface_name) != ''),
    CONSTRAINT check_interface_type_valid CHECK (interface_type IN ('Physical', 'VLAN', 'Loopback', 'Tunnel', 'PortChannel', 'Virtual', 'Management')),
    CONSTRAINT check_admin_status CHECK (admin_status IN ('enabled', 'disabled')),
    CONSTRAINT check_oper_status CHECK (oper_status IN ('up', 'down', 'testing')),
    CONSTRAINT check_mac_format CHECK (mac_address IS NULL OR mac_address GLOB '[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]'),
    CONSTRAINT check_speed_positive CHECK (speed IS NULL OR speed > 0),
    CONSTRAINT check_mtu_valid CHECK (mtu IS NULL OR (mtu >= 64 AND mtu <= 65535)),
    CONSTRAINT check_duplex_valid CHECK (duplex IS NULL OR duplex IN ('full', 'half', 'auto')),
    CONSTRAINT check_vlan_valid CHECK (vlan_id IS NULL OR (vlan_id >= 1 AND vlan_id <= 4094))
);

-- Interface IP addresses (separate from device_ips for interface-specific IPs)
CREATE TABLE interface_ips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interface_id INTEGER NOT NULL,
    ip_address TEXT NOT NULL,
    prefix_length INTEGER NOT NULL,
    ip_version INTEGER NOT NULL, -- 4 or 6
    is_secondary BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (interface_id) REFERENCES interfaces(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT check_prefix_length_v4 CHECK (
        (ip_version = 4 AND prefix_length >= 0 AND prefix_length <= 32) OR
        (ip_version = 6 AND prefix_length >= 0 AND prefix_length <= 128)
    ),
    CONSTRAINT check_ip_version CHECK (ip_version IN (4, 6))
);

-- LLDP neighbor relationships
CREATE TABLE lldp_neighbors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    collection_run_id INTEGER NOT NULL,
    local_interface TEXT NOT NULL,
    remote_hostname TEXT,
    remote_port TEXT,
    remote_system_description TEXT,
    remote_chassis_id TEXT,
    remote_port_id TEXT,
    remote_mgmt_ip TEXT,
    remote_capabilities TEXT, -- JSON array of capabilities
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT check_local_interface_not_empty CHECK (TRIM(local_interface) != '')
);

-- ARP table entries
CREATE TABLE arp_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    collection_run_id INTEGER NOT NULL,
    interface_name TEXT,
    ip_address TEXT NOT NULL,
    mac_address TEXT NOT NULL, -- Normalized format
    age REAL, -- Age in seconds
    entry_type TEXT, -- dynamic, static, permanent
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT check_mac_format_arp CHECK (mac_address GLOB '[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]'),
    CONSTRAINT check_age_positive CHECK (age IS NULL OR age >= 0),
    CONSTRAINT check_entry_type CHECK (entry_type IS NULL OR entry_type IN ('dynamic', 'static', 'permanent'))
);

-- MAC address table
CREATE TABLE mac_address_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    collection_run_id INTEGER NOT NULL,
    mac_address TEXT NOT NULL, -- Normalized format
    interface_name TEXT,
    vlan_id INTEGER,
    entry_type TEXT NOT NULL, -- dynamic, static, permanent
    is_active BOOLEAN NOT NULL DEFAULT 1,
    moves INTEGER DEFAULT 0,
    last_move REAL, -- Timestamp of last move
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT check_mac_format_table CHECK (mac_address GLOB '[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]'),
    CONSTRAINT check_vlan_id_table CHECK (vlan_id IS NULL OR (vlan_id >= 1 AND vlan_id <= 4094)),
    CONSTRAINT check_entry_type_table CHECK (entry_type IN ('dynamic', 'static', 'permanent')),
    CONSTRAINT check_moves_positive CHECK (moves >= 0)
);

-- Environment monitoring data
CREATE TABLE environment_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    collection_run_id INTEGER NOT NULL,
    cpu_usage REAL, -- Percentage (0-100)
    memory_used INTEGER, -- Bytes
    memory_available INTEGER, -- Bytes
    memory_total INTEGER, -- Bytes (calculated or provided)
    temperature_sensors TEXT, -- JSON object of sensor readings
    power_supplies TEXT, -- JSON object of PSU data
    fans TEXT, -- JSON object of fan data
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT check_cpu_usage CHECK (cpu_usage IS NULL OR (cpu_usage >= 0 AND cpu_usage <= 100)),
    CONSTRAINT check_memory_positive CHECK (
        (memory_used IS NULL OR memory_used >= 0) AND
        (memory_available IS NULL OR memory_available >= 0) AND
        (memory_total IS NULL OR memory_total >= 0)
    )
);

-- Device configurations (running, startup, candidate)
CREATE TABLE device_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    collection_run_id INTEGER NOT NULL,
    config_type TEXT NOT NULL, -- running, startup, candidate
    config_content TEXT NOT NULL,
    config_hash TEXT NOT NULL, -- SHA256 hash for change detection
    size_bytes INTEGER NOT NULL,
    line_count INTEGER NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT check_config_type CHECK (config_type IN ('running', 'startup', 'candidate')),
    CONSTRAINT check_size_positive CHECK (size_bytes > 0),
    CONSTRAINT check_lines_positive CHECK (line_count > 0),
    CONSTRAINT check_hash_format CHECK (LENGTH(config_hash) = 64) -- SHA256
);

-- User accounts discovered on devices
CREATE TABLE device_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    collection_run_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    privilege_level INTEGER,
    password_hash TEXT,
    ssh_keys TEXT, -- JSON array of SSH public keys
    user_type TEXT, -- local, domain, radius, tacacs
    is_active BOOLEAN NOT NULL DEFAULT 1,
    last_login DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT check_username_not_empty CHECK (TRIM(username) != ''),
    CONSTRAINT check_privilege_level CHECK (privilege_level IS NULL OR (privilege_level >= 0 AND privilege_level <= 15)),
    CONSTRAINT check_user_type CHECK (user_type IS NULL OR user_type IN ('local', 'domain', 'radius', 'tacacs', 'ldap'))
);

-- Hardware inventory (modules, transceivers, cards)
CREATE TABLE hardware_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    collection_run_id INTEGER NOT NULL,
    component_type TEXT NOT NULL, -- chassis, module, transceiver, fan, psu, linecard
    slot_position TEXT, -- Slot/port identifier
    part_number TEXT,
    serial_number TEXT,
    description TEXT,
    firmware_version TEXT,
    hardware_version TEXT,
    status TEXT NOT NULL, -- operational, failed, missing, unknown
    vendor TEXT,
    model TEXT,
    additional_data TEXT, -- JSON for vendor-specific fields
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT check_component_type CHECK (component_type IN ('chassis', 'module', 'transceiver', 'fan', 'psu', 'linecard', 'supervisor', 'fabric')),
    CONSTRAINT check_status_valid CHECK (status IN ('operational', 'failed', 'missing', 'unknown', 'disabled'))
);

-- VLAN database
CREATE TABLE vlans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    collection_run_id INTEGER NOT NULL,
    vlan_id INTEGER NOT NULL,
    vlan_name TEXT,
    status TEXT NOT NULL, -- active, suspended, shutdown
    interfaces TEXT, -- JSON array of associated interfaces
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT check_vlan_id_range CHECK (vlan_id >= 1 AND vlan_id <= 4094),
    CONSTRAINT check_vlan_status CHECK (status IN ('active', 'suspended', 'shutdown'))
);

-- Routing table entries
CREATE TABLE routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    collection_run_id INTEGER NOT NULL,
    destination_network TEXT NOT NULL,
    prefix_length INTEGER NOT NULL,
    next_hop TEXT,
    interface_name TEXT,
    protocol TEXT NOT NULL, -- static, ospf, bgp, eigrp, rip, connected, local
    metric INTEGER,
    administrative_distance INTEGER,
    age INTEGER, -- Route age in seconds
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT check_prefix_length_route CHECK (prefix_length >= 0 AND prefix_length <= 128),
    CONSTRAINT check_protocol_valid CHECK (protocol IN ('static', 'ospf', 'bgp', 'eigrp', 'rip', 'connected', 'local', 'isis')),
    CONSTRAINT check_metric_positive CHECK (metric IS NULL OR metric >= 0),
    CONSTRAINT check_admin_distance CHECK (administrative_distance IS NULL OR (administrative_distance >= 0 AND administrative_distance <= 255))
);

-- BGP peers information
CREATE TABLE bgp_peers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    collection_run_id INTEGER NOT NULL,
    peer_ip TEXT NOT NULL,
    peer_as INTEGER,
    local_as INTEGER NOT NULL,
    peer_state TEXT NOT NULL,
    session_state TEXT NOT NULL,
    received_prefixes INTEGER DEFAULT 0,
    sent_prefixes INTEGER DEFAULT 0,
    uptime INTEGER, -- Session uptime in seconds
    last_event TEXT,
    peer_description TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT check_as_numbers CHECK (
        (peer_as IS NULL OR (peer_as >= 1 AND peer_as <= 4294967295)) AND
        (local_as >= 1 AND local_as <= 4294967295)
    ),
    CONSTRAINT check_prefix_counts CHECK (
        received_prefixes >= 0 AND sent_prefixes >= 0
    ),
    CONSTRAINT check_uptime_positive CHECK (uptime IS NULL OR uptime >= 0)
);

-- Network topology edges (discovered relationships)
CREATE TABLE network_topology (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_device_id INTEGER NOT NULL,
    source_interface TEXT,
    destination_device_id INTEGER NOT NULL,
    destination_interface TEXT,
    connection_type TEXT NOT NULL, -- lldp, cdp, direct, bgp, ospf
    discovery_method TEXT NOT NULL, -- How this connection was discovered
    confidence_score INTEGER NOT NULL DEFAULT 50, -- 0-100 confidence level
    bandwidth REAL, -- Link bandwidth in Mbps if known
    last_seen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (source_device_id) REFERENCES devices(id) ON DELETE CASCADE,
    FOREIGN KEY (destination_device_id) REFERENCES devices(id) ON DELETE CASCADE,
    
    -- Constraints
    CONSTRAINT check_different_devices CHECK (source_device_id != destination_device_id),
    CONSTRAINT check_connection_type CHECK (connection_type IN ('lldp', 'cdp', 'direct', 'bgp', 'ospf', 'manual')),
    CONSTRAINT check_confidence_score CHECK (confidence_score >= 0 AND confidence_score <= 100),
    CONSTRAINT check_bandwidth_positive CHECK (bandwidth IS NULL OR bandwidth > 0)
);

-- Configuration change tracking
CREATE TABLE config_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    old_config_id INTEGER,
    new_config_id INTEGER NOT NULL,
    change_type TEXT NOT NULL, -- added, modified, deleted, replaced
    change_summary TEXT, -- Brief description of changes
    diff_content TEXT, -- Actual unified diff
    change_size INTEGER NOT NULL, -- Number of lines changed
    detected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    FOREIGN KEY (old_config_id) REFERENCES device_configs(id),
    FOREIGN KEY (new_config_id) REFERENCES device_configs(id),
    
    -- Constraints
    CONSTRAINT check_change_type CHECK (change_type IN ('added', 'modified', 'deleted', 'replaced')),
    CONSTRAINT check_change_size CHECK (change_size >= 0)
);

-- Data retention policies
CREATE TABLE retention_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL UNIQUE,
    retention_days INTEGER NOT NULL,
    keep_latest_count INTEGER, -- Always keep N latest records per device
    enabled BOOLEAN NOT NULL DEFAULT 1,
    last_cleanup DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT check_retention_days CHECK (retention_days > 0),
    CONSTRAINT check_keep_latest CHECK (keep_latest_count IS NULL OR keep_latest_count > 0)
);

-- =======================
-- INDEXES FOR PERFORMANCE
-- =======================

-- Primary lookup indexes
CREATE INDEX idx_devices_device_key ON devices(device_key);
CREATE INDEX idx_devices_device_name ON devices(device_name);
CREATE INDEX idx_devices_serial ON devices(vendor, serial_number);
CREATE INDEX idx_devices_site_role ON devices(site_code, device_role);
CREATE INDEX idx_devices_active ON devices(is_active);

-- Device IPs indexes
CREATE INDEX idx_device_ips_device ON device_ips(device_id);
CREATE INDEX idx_device_ips_address ON device_ips(ip_address);
CREATE INDEX idx_device_ips_primary ON device_ips(device_id, is_primary);
CREATE INDEX idx_device_ips_type ON device_ips(ip_type);

-- Collection runs indexes
CREATE INDEX idx_collection_device_time ON collection_runs(device_id, collection_time DESC);
CREATE INDEX idx_collection_time ON collection_runs(collection_time DESC);
CREATE INDEX idx_collection_success ON collection_runs(success);
CREATE INDEX idx_collection_ip ON collection_runs(collection_ip);

-- Interface indexes
CREATE INDEX idx_interfaces_device ON interfaces(device_id);
CREATE INDEX idx_interfaces_device_name ON interfaces(device_id, interface_name);
CREATE INDEX idx_interfaces_status ON interfaces(admin_status, oper_status);
CREATE INDEX idx_interfaces_type ON interfaces(interface_type);
CREATE INDEX idx_interfaces_vlan ON interfaces(vlan_id);
CREATE INDEX idx_interfaces_mac ON interfaces(mac_address);

-- Interface IPs indexes
CREATE INDEX idx_interface_ips_interface ON interface_ips(interface_id);
CREATE INDEX idx_interface_ips_address ON interface_ips(ip_address);

-- LLDP indexes
CREATE INDEX idx_lldp_device_interface ON lldp_neighbors(device_id, local_interface);
CREATE INDEX idx_lldp_remote ON lldp_neighbors(remote_hostname);
CREATE INDEX idx_lldp_chassis ON lldp_neighbors(remote_chassis_id);

-- ARP indexes
CREATE INDEX idx_arp_device ON arp_entries(device_id);
CREATE INDEX idx_arp_ip ON arp_entries(ip_address);
CREATE INDEX idx_arp_mac ON arp_entries(mac_address);
CREATE INDEX idx_arp_interface ON arp_entries(interface_name);

-- MAC table indexes
CREATE INDEX idx_mac_device ON mac_address_table(device_id);
CREATE INDEX idx_mac_address ON mac_address_table(mac_address);
CREATE INDEX idx_mac_vlan ON mac_address_table(vlan_id);
CREATE INDEX idx_mac_interface ON mac_address_table(interface_name);
CREATE INDEX idx_mac_type ON mac_address_table(entry_type);

-- Environment indexes
CREATE INDEX idx_env_device_time ON environment_data(device_id, created_at DESC);

-- Config indexes
CREATE INDEX idx_config_device_type ON device_configs(device_id, config_type);
CREATE INDEX idx_config_hash ON device_configs(config_hash);
CREATE INDEX idx_config_time ON device_configs(created_at DESC);

-- Hardware indexes
CREATE INDEX idx_hardware_device ON hardware_inventory(device_id);
CREATE INDEX idx_hardware_serial ON hardware_inventory(serial_number);
CREATE INDEX idx_hardware_type ON hardware_inventory(component_type);

-- Topology indexes
CREATE INDEX idx_topology_source ON network_topology(source_device_id, source_interface);
CREATE INDEX idx_topology_dest ON network_topology(destination_device_id, destination_interface);
CREATE INDEX idx_topology_type ON network_topology(connection_type);
CREATE INDEX idx_topology_active ON network_topology(is_active);

-- ===============
-- USEFUL VIEWS
-- ===============

-- Latest device information with primary IP
CREATE VIEW latest_devices AS
SELECT
    d.*,
    di.ip_address as primary_ip,
    di.ip_type as primary_ip_type,
    cr.collection_time as last_collection,
    cr.success as last_collection_success,
    cr.credential_used,
    cr.napalm_driver,
    cr.collection_ip as last_collection_ip,
    cr.collection_duration
FROM devices d
LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
LEFT JOIN (
    SELECT device_id, collection_time, success, credential_used, napalm_driver, 
           collection_ip, collection_duration,
           ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY collection_time DESC) as rn
    FROM collection_runs
) cr ON d.id = cr.device_id AND cr.rn = 1;

-- Latest interface status
CREATE VIEW latest_interfaces AS
SELECT
    i.*,
    d.device_name,
    d.site_code,
    cr.collection_time
FROM interfaces i
JOIN devices d ON i.device_id = d.id
JOIN (
    SELECT device_id, collection_time, id,
           ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY collection_time DESC) as rn
    FROM collection_runs
) cr ON i.collection_run_id = cr.id AND cr.rn = 1;

-- Active network topology from LLDP
CREATE VIEW current_topology AS
SELECT
    nt.*,
    d1.device_name as source_device_name,
    d1.site_code as source_site,
    d2.device_name as dest_device_name,
    d2.site_code as dest_site,
    CASE 
        WHEN d1.site_code = d2.site_code THEN 'intra_site'
        ELSE 'inter_site'
    END as link_type
FROM network_topology nt
JOIN devices d1 ON nt.source_device_id = d1.id
JOIN devices d2 ON nt.destination_device_id = d2.id
WHERE nt.is_active = 1;

-- Device health summary
CREATE VIEW device_health AS
SELECT
    d.id,
    d.device_name,
    d.site_code,
    d.device_role,
    d.vendor,
    d.model,
    ld.primary_ip,
    ed.cpu_usage,
    ed.memory_used,
    ed.memory_available,
    ed.memory_total,
    CASE 
        WHEN ed.memory_total > 0 THEN ROUND((ed.memory_used * 100.0 / ed.memory_total), 2)
        WHEN ed.memory_available > 0 THEN ROUND((ed.memory_used * 100.0 / (ed.memory_used + ed.memory_available)), 2)
        ELSE NULL
    END as memory_usage_percent,
    ROUND(d.uptime / 86400.0, 1) as uptime_days,
    ld.last_collection,
    ld.last_collection_success
FROM devices d
JOIN latest_devices ld ON d.id = ld.id
LEFT JOIN (
    SELECT device_id, cpu_usage, memory_used, memory_available, memory_total,
           ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY created_at DESC) as rn
    FROM environment_data
) ed ON d.id = ed.device_id AND ed.rn = 1
WHERE d.is_active = 1;

-- Configuration change summary
CREATE VIEW recent_config_changes AS
SELECT
    cc.*,
    d.device_name,
    d.site_code,
    nc.config_type,
    nc.created_at as config_created_at
FROM config_changes cc
JOIN devices d ON cc.device_id = d.id
JOIN device_configs nc ON cc.new_config_id = nc.id
WHERE cc.detected_at >= datetime('now', '-30 days')
ORDER BY cc.detected_at DESC;

-- =======================
-- TRIGGERS FOR DATA INTEGRITY
-- =======================

-- Ensure only one primary IP per device
CREATE TRIGGER enforce_single_primary_ip
    BEFORE INSERT ON device_ips
    FOR EACH ROW
    WHEN NEW.is_primary = 1
BEGIN
    UPDATE device_ips SET is_primary = 0 
    WHERE device_id = NEW.device_id AND is_primary = 1;
END;

-- Update device last_updated timestamp on collection
CREATE TRIGGER update_device_timestamp
    AFTER INSERT ON collection_runs
    FOR EACH ROW
BEGIN
    UPDATE devices
    SET last_updated = NEW.collection_time
    WHERE id = NEW.device_id;
END;

-- Auto-create topology entries from LLDP data
CREATE TRIGGER create_topology_from_lldp
    AFTER INSERT ON lldp_neighbors
    FOR EACH ROW
BEGIN
    INSERT OR REPLACE INTO network_topology (
        source_device_id,
        source_interface,
        destination_device_id,
        destination_interface,
        connection_type,
        discovery_method,
        confidence_score,
        last_seen
    )
    SELECT
        NEW.device_id,
        NEW.local_interface,
        d.id,
        NEW.remote_port,
        'lldp',
        'napalm_discovery',
        85,
        (SELECT collection_time FROM collection_runs WHERE id = NEW.collection_run_id)
    FROM devices d
    WHERE (d.hostname = NEW.remote_hostname
       OR d.device_name = NEW.remote_hostname
       OR d.fqdn = NEW.remote_hostname)
    AND d.id != NEW.device_id; -- Don't create self-loops
END;

-- Auto-detect configuration changes
CREATE TRIGGER detect_config_changes
    AFTER INSERT ON device_configs
    FOR EACH ROW
BEGIN
    INSERT INTO config_changes (
        device_id,
        old_config_id,
        new_config_id,
        change_type,
        change_size
    )
    SELECT
        NEW.device_id,
        old_config.id,
        NEW.id,
        CASE 
            WHEN old_config.id IS NULL THEN 'added'
            WHEN old_config.config_hash != NEW.config_hash THEN 'modified'
            ELSE 'replaced'
        END,
        ABS(NEW.line_count - COALESCE(old_config.line_count, 0))
    FROM (
        SELECT id, config_hash, line_count
        FROM device_configs
        WHERE device_id = NEW.device_id 
        AND config_type = NEW.config_type
        AND id != NEW.id
        ORDER BY created_at DESC
        LIMIT 1
    ) old_config
    WHERE old_config.config_hash IS NULL OR old_config.config_hash != NEW.config_hash;
END;

-- ========================
-- INITIAL DATA SETUP
-- ========================

-- Insert default retention policies
INSERT INTO retention_policies (table_name, retention_days, keep_latest_count) VALUES
('collection_runs', 90, 5),
('interfaces', 90, 1),
('arp_entries', 30, 3),
('mac_address_table', 30, 3),
('environment_data', 30, 10),
('device_configs', 365, 10),
('lldp_neighbors', 90, 1);

-- Performance optimization settings
ANALYZE;