// Enhanced search.js for NAPALM CMDB
// Handles comprehensive search functionality and integrates with table viewers

let currentSearchResults = null;
let searchStartTime = null;

document.addEventListener('DOMContentLoaded', function() {
    initializeSearch();
    loadInitialData();
    setupEventListeners();
});

function initializeSearch() {
    // Load filter options
    loadSites();
    loadDevices();

    // Check for URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const searchTerm = urlParams.get('search');
    const category = urlParams.get('category');

    if (searchTerm) {
        document.getElementById('searchTerm').value = searchTerm;
        if (category) {
            document.getElementById('searchCategory').value = category;
        }
        performSearch();
    }
}

function setupEventListeners() {
    // Search form submission
    document.getElementById('unifiedSearchForm').addEventListener('submit', function(e) {
        e.preventDefault();
        performSearch();
    });

    // Live search on input
    let searchTimeout;
    document.getElementById('searchTerm').addEventListener('input', function() {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            if (this.value.length >= 3) {
                performSearch();
            }
        }, 500);
    });

    // Category change
    document.getElementById('searchCategory').addEventListener('change', function() {
        if (document.getElementById('searchTerm').value) {
            performSearch();
        }
    });
}

async function loadSites() {
    try {
        const response = await fetch('/search/api/sites');
        const sites = await response.json();
        const siteFilter = document.getElementById('siteFilter');

        sites.forEach(site => {
            const option = document.createElement('option');
            option.value = site.site_code;
            option.textContent = `${site.site_code} (${site.device_count} devices)`;
            siteFilter.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading sites:', error);
    }
}

async function loadDevices() {
    try {
        const response = await fetch('/devices/api/search?q=');
        const devices = await response.json();
        const deviceFilter = document.getElementById('deviceFilter');

        devices.slice(0, 20).forEach(device => {
            const option = document.createElement('option');
            option.value = device.device_name;
            option.textContent = `${device.device_name} (${device.vendor})`;
            deviceFilter.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading devices:', error);
    }
}

async function performSearch() {
    const searchTerm = document.getElementById('searchTerm').value.trim();
    if (!searchTerm) {
        hideSearchResults();
        return;
    }

    showSearching();
    searchStartTime = performance.now();

    try {
        const params = new URLSearchParams({
            search: searchTerm,
            category: document.getElementById('searchCategory').value,
            device: document.getElementById('deviceFilter').value,
            site: document.getElementById('siteFilter').value,
            mode: document.getElementById('searchMode').value,
            time_range: document.getElementById('timeRange').value,
            vendor: document.getElementById('vendorFilter').value,
            status: document.getElementById('statusFilter').value,
            include_inactive: document.getElementById('includeInactive').checked
        });

        const response = await fetch(`/search/api/comprehensive?${params}`);
        const results = await response.json();

        if (response.ok) {
            currentSearchResults = results;
            displaySearchResults(results);
        } else {
            throw new Error(results.error || 'Search failed');
        }
    } catch (error) {
        console.error('Search error:', error);
        showAlert('Search failed: ' + error.message, 'danger');
        hideSearchResults();
    }
}

function showSearching() {
    document.getElementById('searchStats').style.display = 'block';
    document.getElementById('searchResults').style.display = 'block';

    // Show loading in summary
    document.getElementById('summaryContent').innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Searching...</span>
            </div>
            <p class="mt-2">Searching across all data types...</p>
        </div>
    `;
}

function displaySearchResults(results) {
    const searchTime = Math.round(performance.now() - searchStartTime);

    // Update statistics
    document.getElementById('totalResults').textContent = results.total_results || 0;
    document.getElementById('deviceCount').textContent = results.device_count || 0;
    document.getElementById('dataTypes').textContent = results.data_types_found || 0;
    document.getElementById('configMatches').textContent = results.configurations?.length || 0;
    document.getElementById('networkMatches').textContent = results.network_data?.length || 0;
    document.getElementById('searchTime').textContent = `${searchTime}ms`;

    // Update tab badges
    document.getElementById('summaryCount').textContent = results.total_results || 0;
    document.getElementById('configsCount').textContent = results.configurations?.length || 0;
    document.getElementById('networkCount').textContent = results.network_data?.length || 0;
    document.getElementById('interfacesCount').textContent = results.interfaces?.length || 0;
    document.getElementById('topologyCount').textContent = results.topology?.length || 0;
    document.getElementById('hardwareCount').textContent = results.hardware?.length || 0;

    // Display results in tabs
    displaySummaryTab(results);
    displayConfigurationsTab(results.configurations || []);
    displayNetworkTab(results.network_data || []);
    displayInterfacesTab(results.interfaces || []);
    displayTopologyTab(results.topology || []);
    displayHardwareTab(results.hardware || []);

    // Show search results
    document.getElementById('searchStats').style.display = 'block';
    document.getElementById('searchResults').style.display = 'block';
}

function displaySummaryTab(results) {
    const summaryContent = document.getElementById('summaryContent');

    if (results.total_results === 0) {
        summaryContent.innerHTML = `
            <div class="text-center text-muted py-4">
                <i class="bi bi-search fs-1"></i>
                <h4 class="mt-3">No Results Found</h4>
                <p>No data matches your search criteria. Try:</p>
                <ul class="list-unstyled">
                    <li>• Using different search terms</li>
                    <li>• Changing the search mode</li>
                    <li>• Broadening your filters</li>
                </ul>
            </div>
        `;
        return;
    }

    let summaryHtml = `
        <div class="row mb-4">
            <div class="col-12">
                <h5>Search Summary</h5>
                <p class="text-muted">Found ${results.total_results} results across ${results.data_types_found} data types from ${results.device_count} devices.</p>
            </div>
        </div>
    `;

    // Data type breakdown
    const dataTypes = [
        { key: 'configurations', label: 'Configurations', icon: 'bi-file-earmark-code', color: 'primary' },
        { key: 'network_data', label: 'Network Data', icon: 'bi-globe', color: 'info' },
        { key: 'interfaces', label: 'Interfaces', icon: 'bi-ethernet', color: 'success' },
        { key: 'topology', label: 'Topology', icon: 'bi-diagram-3', color: 'warning' },
        { key: 'hardware', label: 'Hardware', icon: 'bi-cpu', color: 'danger' },
        { key: 'routing', label: 'Routing', icon: 'bi-signpost', color: 'secondary' }
    ];

    summaryHtml += '<div class="row">';
    dataTypes.forEach(type => {
        const count = results[type.key]?.length || 0;
        if (count > 0) {
            summaryHtml += `
                <div class="col-md-4 mb-3">
                    <div class="card h-100">
                        <div class="card-body">
                            <div class="d-flex align-items-center">
                                <i class="bi ${type.icon} fs-2 text-${type.color} me-3"></i>
                                <div>
                                    <h5 class="card-title mb-1">${type.label}</h5>
                                    <p class="card-text text-muted">${count} matches found</p>
                                    <button class="btn btn-outline-${type.color} btn-sm" onclick="switchToTab('${type.key}')">
                                        View Details
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }
    });
    summaryHtml += '</div>';

    // Quick actions
    summaryHtml += `
        <div class="row mt-4">
            <div class="col-12">
                <h6>Quick Actions</h6>
                <div class="btn-group" role="group">
                    <button class="btn btn-outline-primary btn-sm" onclick="viewAllResults('arp')">
                        <i class="bi bi-table me-1"></i>View ARP Data
                    </button>
                    <button class="btn btn-outline-primary btn-sm" onclick="viewAllResults('mac_table')">
                        <i class="bi bi-table me-1"></i>View MAC Table
                    </button>
                    <button class="btn btn-outline-primary btn-sm" onclick="viewAllResults('lldp')">
                        <i class="bi bi-table me-1"></i>View LLDP Data
                    </button>
                    <button class="btn btn-outline-success btn-sm" onclick="exportResults()">
                        <i class="bi bi-download me-1"></i>Export Results
                    </button>
                </div>
            </div>
        </div>
    `;

    summaryContent.innerHTML = summaryHtml;
}

function displayConfigurationsTab(configurations) {
    const content = document.getElementById('configsContent');

    if (configurations.length === 0) {
        content.innerHTML = '<div class="text-center text-muted py-4"><p>No configuration matches found.</p></div>';
        return;
    }

    let html = `
        <div class="table-responsive">
            <table class="table table-dark table-hover">
                <thead>
                    <tr>
                        <th>Device</th>
                        <th>Config Type</th>
                        <th>Size</th>
                        <th>Matches</th>
                        <th>Last Updated</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
    `;

    configurations.forEach(config => {
        html += `
            <tr>
                <td>
                    <a href="/devices/detail/${config.device_name}" class="text-decoration-none">
                        <strong>${config.device_name}</strong>
                    </a>
                    <br><small class="text-muted">${config.site_code}</small>
                </td>
                <td>
                    <span class="badge ${config.config_type === 'running' ? 'bg-success' : 'bg-warning'}">
                        ${config.config_type.charAt(0).toUpperCase() + config.config_type.slice(1)}
                    </span>
                </td>
                <td>${formatFileSize(config.config_size)}</td>
                <td><span class="badge bg-primary">${config.match_count}</span></td>
                <td>
                    ${formatDateTime(config.created_at)}
                    <br><small class="text-muted">${formatRelativeTime(config.created_at)}</small>
                </td>
                <td>
                    <div class="btn-group btn-group-sm">
                        <a href="/search/config/view/${config.config_id}" class="btn btn-outline-primary" title="View Config">
                            <i class="bi bi-eye"></i>
                        </a>
                        <button class="btn btn-outline-secondary" onclick="downloadConfig(${config.config_id})" title="Download">
                            <i class="bi bi-download"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    });

    html += '</tbody></table></div>';
    content.innerHTML = html;
}

function displayNetworkTab(networkData) {
    const content = document.getElementById('networkContent');

    if (networkData.length === 0) {
        content.innerHTML = '<div class="text-center text-muted py-4"><p>No network data matches found.</p></div>';
        return;
    }

    let html = `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <h6>Network Data Results</h6>
            <div class="btn-group btn-group-sm">
                <button class="btn btn-outline-primary" onclick="viewAllResults('arp')">
                    <i class="bi bi-table me-1"></i>View All ARP
                </button>
                <button class="btn btn-outline-primary" onclick="viewAllResults('mac_table')">
                    <i class="bi bi-table me-1"></i>View All MAC
                </button>
                <button class="btn btn-outline-primary" onclick="viewAllResults('vlans')">
                    <i class="bi bi-table me-1"></i>View All VLANs
                </button>
            </div>
        </div>
        <div class="table-responsive">
            <table class="table table-dark table-hover">
                <thead>
                    <tr>
                        <th>Type</th>
                        <th>Device</th>
                        <th>Data</th>
                        <th>Interface</th>
                        <th>VLAN</th>
                        <th>Last Seen</th>
                    </tr>
                </thead>
                <tbody>
    `;

    networkData.forEach(item => {
    const dataTypeLabels = {
        'device_ip': 'Device IP',
        'arp_ip': 'ARP Entry',
        'arp_mac': 'ARP MAC',
        'mac_table': 'MAC Table',
        'vlan': 'VLAN'
    };

    // Smart data display logic to avoid duplication
    let dataDisplay = '';

    // Check what data we have
    const hasIp = item.ip_address && item.ip_address.trim();
    const hasMac = item.mac_address && item.mac_address.trim();
    const hasSearchMatch = item.search_match && item.search_match.trim();

    // Determine if search_match is the same as ip_address or mac_address
    const searchMatchIsIp = hasSearchMatch && hasIp && item.search_match === item.ip_address;
    const searchMatchIsMac = hasSearchMatch && hasMac && item.search_match === item.mac_address;

    // Display IP address (prefer search_match if it's an IP, otherwise use ip_address)
    if (hasSearchMatch && !searchMatchIsMac) {
        dataDisplay += `<code>${item.search_match}</code>`;
    } else if (hasIp && !searchMatchIsIp) {
        dataDisplay += `<code>${item.ip_address}</code>`;
    }

    // Display MAC address (only if not already shown as search_match)
    if (hasMac && !searchMatchIsMac) {
        if (dataDisplay) dataDisplay += '<br>';
        dataDisplay += `<code>${item.mac_address}</code>`;
    }

    // Add VLAN name if available
    if (item.vlan_name) {
        dataDisplay += `<br><small>${item.vlan_name}</small>`;
    }

    // Fallback if no data to display
    if (!dataDisplay && hasSearchMatch) {
        dataDisplay = `<code>${item.search_match}</code>`;
    }

    html += `
        <tr>
            <td>
                <span class="badge bg-info">${dataTypeLabels[item.data_type] || item.data_type}</span>
            </td>
            <td>
                <a href="/devices/detail/${item.device_name}" class="text-decoration-none">
                    ${item.device_name}
                </a>
                <br><small class="text-muted">${item.site_code}</small>
            </td>
            <td>
                ${dataDisplay || '-'}
            </td>
            <td>${item.interface_name || '-'}</td>
            <td>
                ${item.vlan_id ? `<span class="badge bg-secondary">${item.vlan_id}</span>` : '-'}
            </td>
            <td>
                ${formatDateTime(item.last_seen)}
                <br><small class="text-muted">${formatRelativeTime(item.last_seen)}</small>
            </td>
        </tr>
    `;
});

    html += '</tbody></table></div>';
    content.innerHTML = html;
}

function displayInterfacesTab(interfaces) {
    const content = document.getElementById('interfacesContent');

    if (interfaces.length === 0) {
        content.innerHTML = '<div class="text-center text-muted py-4"><p>No interface matches found.</p></div>';
        return;
    }

    let html = `
        <div class="table-responsive">
            <table class="table table-dark table-hover">
                <thead>
                    <tr>
                        <th>Device</th>
                        <th>Interface</th>
                        <th>Type</th>
                        <th>Description</th>
                        <th>Status</th>
                        <th>Speed</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
    `;

    interfaces.forEach(intf => {
        html += `
            <tr>
                <td>
                    <a href="/devices/detail/${intf.device_name}" class="text-decoration-none">
                        ${intf.device_name}
                    </a>
                    <br><small class="text-muted">${intf.site_code}</small>
                </td>
                <td><code>${intf.interface_name}</code></td>
                <td>
                    <span class="badge ${getInterfaceTypeBadge(intf.interface_type)}">
                        ${intf.interface_type}
                    </span>
                </td>
                <td>
                    ${intf.description ?
                        (intf.description.length > 30 ?
                            `<span title="${intf.description}">${intf.description.substring(0, 30)}...</span>` :
                            intf.description
                        ) :
                        '<span class="text-muted">No description</span>'
                    }
                </td>
                <td>
                    ${getStatusBadge(intf.admin_status, intf.oper_status)}
                </td>
                <td>
                    ${intf.speed ? `${intf.speed >= 1000 ? (intf.speed / 1000) + ' Gbps' : intf.speed + ' Mbps'}` : '-'}
                </td>
                <td>
                    <a href="/devices/detail/${intf.device_name}/interfaces" class="btn btn-outline-info btn-sm">
                        <i class="bi bi-list"></i>
                    </a>
                </td>
            </tr>
        `;
    });

    html += '</tbody></table></div>';
    content.innerHTML = html;
}

function displayTopologyTab(topology) {
    const content = document.getElementById('topologyContent');

    if (topology.length === 0) {
        content.innerHTML = '<div class="text-center text-muted py-4"><p>No topology matches found.</p></div>';
        return;
    }

    let html = `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <h6>LLDP Topology Results</h6>
            <button class="btn btn-outline-primary btn-sm" onclick="viewAllResults('lldp')">
                <i class="bi bi-table me-1"></i>View All LLDP Data
            </button>
        </div>
        <div class="table-responsive">
            <table class="table table-dark table-hover">
                <thead>
                    <tr>
                        <th>Local Device</th>
                        <th>Local Interface</th>
                        <th>Remote Device</th>
                        <th>Remote Interface</th>
                        <th>Remote Description</th>
                        <th>Last Seen</th>
                    </tr>
                </thead>
                <tbody>
    `;

    topology.forEach(link => {
        html += `
            <tr>
                <td>
                    <a href="/devices/detail/${link.local_device}" class="text-decoration-none">
                        <strong>${link.local_device}</strong>
                    </a>
                    <br><small class="text-muted">${link.local_site}</small>
                </td>
                <td><code>${link.local_interface}</code></td>
                <td>
                    <strong>${link.remote_device}</strong>
                </td>
                <td><code>${link.remote_interface || 'Unknown'}</code></td>
                <td>
                    ${link.remote_system_description ?
                        (link.remote_system_description.length > 40 ?
                            `<span title="${link.remote_system_description}">${link.remote_system_description.substring(0, 40)}...</span>` :
                            link.remote_system_description
                        ) :
                        '<span class="text-muted">No description</span>'
                    }
                </td>
                <td>
                    ${formatDateTime(link.last_seen)}
                    <br><small class="text-muted">${formatRelativeTime(link.last_seen)}</small>
                </td>
            </tr>
        `;
    });

    html += '</tbody></table></div>';
    content.innerHTML = html;
}

function displayHardwareTab(hardware) {
    const content = document.getElementById('hardwareContent');

    if (hardware.length === 0) {
        content.innerHTML = '<div class="text-center text-muted py-4"><p>No hardware matches found.</p></div>';
        return;
    }

    let html = `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <h6>Hardware Inventory Results</h6>
            <button class="btn btn-outline-primary btn-sm" onclick="viewAllResults('hardware')">
                <i class="bi bi-table me-1"></i>View All Hardware
            </button>
        </div>
        <div class="table-responsive">
            <table class="table table-dark table-hover">
                <thead>
                    <tr>
                        <th>Device</th>
                        <th>Component</th>
                        <th>Slot/Position</th>
                        <th>Part Number</th>
                        <th>Serial Number</th>
                        <th>Status</th>
                        <th>Last Seen</th>
                    </tr>
                </thead>
                <tbody>
    `;

    hardware.forEach(hw => {
        html += `
            <tr>
                <td>
                    <a href="/devices/detail/${hw.device_name}" class="text-decoration-none">
                        ${hw.device_name}
                    </a>
                    <br><small class="text-muted">${hw.site_code}</small>
                </td>
                <td>
                    <span class="badge ${getComponentTypeBadge(hw.component_type)}">
                        ${hw.component_type}
                    </span>
                    ${hw.description ? `<br><small class="text-muted">${hw.description.substring(0, 25)}${hw.description.length > 25 ? '...' : ''}</small>` : ''}
                </td>
                <td>${hw.slot_position || '-'}</td>
                <td>${hw.part_number ? `<code>${hw.part_number}</code>` : '-'}</td>
                <td>${hw.serial_number ? `<code>${hw.serial_number}</code>` : '-'}</td>
                <td>${getStatusBadge(hw.status)}</td>
                <td>
                    ${formatDateTime(hw.last_seen)}
                    <br><small class="text-muted">${formatRelativeTime(hw.last_seen)}</small>
                </td>
            </tr>
        `;
    });

    html += '</tbody></table></div>';
    content.innerHTML = html;
}

// Utility functions
function switchToTab(tabKey) {
    const tabMap = {
        'configurations': 'configs-tab',
        'network_data': 'network-tab',
        'interfaces': 'interfaces-tab',
        'topology': 'topology-tab',
        'hardware': 'hardware-tab'
    };

    const tabId = tabMap[tabKey];
    if (tabId) {
        const tab = document.getElementById(tabId);
        if (tab) {
            const tabInstance = new bootstrap.Tab(tab);
            tabInstance.show();
        }
    }
}

function viewAllResults(dataType) {
    // Open the table viewer for the specific data type
    window.open(`/search/view/${dataType}`, '_blank');
}

function quickSearch(term, category, description) {
    document.getElementById('searchTerm').value = term;
    document.getElementById('searchCategory').value = category;
    performSearch();

    // Show tooltip or alert about what we're searching for
    showAlert(`Searching for ${description}...`, 'info');
}

function getInterfaceTypeBadge(type) {
    const typeMap = {
        'Physical': 'bg-primary',
        'VLAN': 'bg-info',
        'Loopback': 'bg-success',
        'PortChannel': 'bg-warning',
        'Tunnel': 'bg-secondary'
    };
    return typeMap[type] || 'bg-secondary';
}

function getComponentTypeBadge(type) {
    const typeMap = {
        'transceiver': 'bg-info',
        'module': 'bg-primary',
        'power_supply': 'bg-warning',
        'fan': 'bg-success',
        'card': 'bg-secondary'
    };
    return typeMap[type] || 'bg-secondary';
}

function getStatusBadge(adminStatus, operStatus) {
    if (arguments.length === 1) {
        // Single status (hardware)
        const status = adminStatus;
        if (status === 'operational' || status === 'up' || status === 'enabled') {
            return '<span class="status-badge status-online"><i class="bi bi-check-circle me-1"></i>OK</span>';
        } else if (status === 'failed' || status === 'down' || status === 'disabled') {
            return '<span class="status-badge status-offline"><i class="bi bi-x-circle me-1"></i>Failed</span>';
        } else {
            return '<span class="status-badge status-warning"><i class="bi bi-question-circle me-1"></i>' + (status || 'Unknown') + '</span>';
        }
    } else {
        // Interface status (admin/oper)
        if (adminStatus === 'enabled' && operStatus === 'up') {
            return '<span class="status-badge status-online"><i class="bi bi-check-circle me-1"></i>Up/Up</span>';
        } else if (adminStatus === 'enabled' && operStatus === 'down') {
            return '<span class="status-badge status-offline"><i class="bi bi-x-circle me-1"></i>Up/Down</span>';
        } else if (adminStatus === 'disabled') {
            return '<span class="status-badge bg-secondary"><i class="bi bi-dash-circle me-1"></i>Disabled</span>';
        } else {
            return '<span class="status-badge status-warning"><i class="bi bi-question-circle me-1"></i>Unknown</span>';
        }
    }
}

function formatDateTime(dateString) {
    if (!dateString) return 'N/A';
    try {
        const date = new Date(dateString);
        return date.toLocaleString();
    } catch (e) {
        return dateString;
    }
}

function formatRelativeTime(dateString) {
    if (!dateString) return '';
    try {
        const date = new Date(dateString);
        const now = new Date();
        const diff = now - date;

        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (days > 0) return `${days} days ago`;
        if (hours > 0) return `${hours} hours ago`;
        if (minutes > 0) return `${minutes} minutes ago`;
        return 'Just now';
    } catch (e) {
        return '';
    }
}

function formatFileSize(bytes) {
    if (!bytes) return '0 B';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
}

function hideSearchResults() {
    document.getElementById('searchStats').style.display = 'none';
    document.getElementById('searchResults').style.display = 'none';
}

function downloadConfig(configId) {
    window.open(`/search/config/view/${configId}`, '_blank');
}

function exportResults() {
    if (!currentSearchResults) {
        showAlert('No search results to export', 'warning');
        return;
    }

    const modal = new bootstrap.Modal(document.getElementById('exportModal'));
    modal.show();
}

function performExport() {
    const format = document.querySelector('input[name="exportFormat"]:checked').value;
    const includeConfigs = document.getElementById('includeConfigs').checked;
    const includeNetwork = document.getElementById('includeNetwork').checked;
    const includeInterfaces = document.getElementById('includeInterfaces').checked;
    const includeHardware = document.getElementById('includeHardware').checked;

    // This would implement the actual export functionality
    showAlert(`Export in ${format} format would be implemented here`, 'info');

    const modal = bootstrap.Modal.getInstance(document.getElementById('exportModal'));
    modal.hide();
}

function loadInitialData() {
    // Load any initial data or state
}

function showAlert(message, type = 'info') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    const container = document.querySelector('.container-fluid');
    if (container) {
        container.insertBefore(alertDiv, container.firstChild);
    }

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}