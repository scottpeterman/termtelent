// Global variables
let term;
let fitAddon;
let backend;
let terminalTheme = {
    background: '#000000',
    foreground: '#f0f0f0',
    cursor: '#00ff00',
    cursorAccent: '#000000',
    selection: '#504945',
    selectionForeground: '#f0f0f0',
    black: '#000000',
    red: '#cc0000',
    green: '#4e9a06',
    yellow: '#c4a000',
    blue: '#3465a4',
    magenta: '#75507b',
    cyan: '#06989a',
    white: '#d3d7cf',
    brightBlack: '#555753',
    brightRed: '#ef2929',
    brightGreen: '#8ae234',
    brightYellow: '#fce94f',
    brightBlue: '#729fcf',
    brightMagenta: '#ad7fa8',
    brightCyan: '#34e2e2',
    brightWhite: '#eeeeec'
};

// Initialize the terminal
function initTerminal() {
    // Create terminal instance
    term = new Terminal({
        cursorBlink: true,
        fontFamily: 'Courier New',
        fontSize: 14,
        theme: terminalTheme,
        scrollback: 10000,
        allowTransparency: true
    });

    // Create and load addons
    fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);

    // Open the terminal in the container
    term.open(document.getElementById('terminal'));
    fitAddon.fit();

    // Connect terminal input to backend
    term.onData(data => {
        if (backend) {
            backend.write_data(data);
        }
    });

    // Handle window resize
    window.addEventListener('resize', () => {
        fitAddon.fit();
    });

    // Set up WebChannel for backend communication
    initWebChannel();
}

// Handle output from backend
function handle_output(data) {
    if (term) {
        console.log("Received data:", data);
        term.write(data);
    }
}

// Initialize WebChannel to communicate with Python backend
function initWebChannel() {
    new QWebChannel(qt.webChannelTransport, function(channel) {
        backend = channel.objects.backend;
        console.log("WebChannel initialized, backend connected");

        // Get form elements
        const portSelect = document.getElementById('port-select');
        const baudSelect = document.getElementById('baud-select');
        const databitsSelect = document.getElementById('databits-select');
        const stopbitsSelect = document.getElementById('stopbits-select');
        const paritySelect = document.getElementById('parity-select');
        const connectBtn = document.getElementById('connect-btn');

        // Add refresh ports button
        addRefreshButton(portSelect);

        // Function to update UI based on connection state
        window.updateUIConnected = function(isConnected) {
            console.log("Updating UI connection state:", isConnected);
            if (isConnected) {
                connectBtn.textContent = 'Disconnect';
                // Update status element if it exists
                updateConnectionStatus(true);
                connectBtn.onclick = function() {
                    backend.disconnect();
                };
            } else {
                connectBtn.textContent = 'Connect';
                // Update status element if it exists
                updateConnectionStatus(false);
                connectBtn.onclick = function() {
                    // Get current values from form
                    const port = portSelect.value;
                    const baud = parseInt(baudSelect.value, 10);
                    const databits = parseInt(databitsSelect.value, 10);
                    const stopbits = parseFloat(stopbitsSelect.value);
                    const parity = paritySelect.value;

                    console.log("Connecting with params:", {
                        port: port,
                        baud: baud,
                        databits: databits,
                        stopbits: stopbits,
                        parity: parity
                    });

                    // Make sure we have a port
                    if (!port) {
                        console.error("No port selected");
                        term.write("\r\nError: No port selected\r\n");
                        return;
                    }

                    // Call the connect method with correct parameters
                    backend.connect_with_params(port, baud, databits, stopbits, parity);
                };
            }
        };

        // Make updateConnectButton call updateUIConnected for compatibility
        window.updateConnectButton = function(isConnected) {
            window.updateUIConnected(isConnected);
        };

        // Set initial values in form if available
        setTimeout(() => {
            if (backend.baudrate) baudSelect.value = backend.baudrate.toString();
            if (backend.databits) databitsSelect.value = backend.databits.toString();
            if (backend.stopbits) {
                const stopVal = backend.stopbits === 1.5 ? "1.5" : backend.stopbits.toString();
                stopbitsSelect.value = stopVal;
            }
            if (backend.parity) paritySelect.value = backend.parity;

            // Initial button state
            window.updateUIConnected(false);
        }, 200);
    });
}

// Function to update connection status indicator
function updateConnectionStatus(isConnected) {
    const statusDiv = document.getElementById('connection-status');
    if (statusDiv) {
        statusDiv.textContent = isConnected ? 'Connected' : 'Disconnected';
        statusDiv.className = isConnected ? 'status-connected' : 'status-disconnected';
    }
}

// Add a refresh button for the port list
function addRefreshButton(portSelect) {
    // Check if button already exists
    if (document.getElementById('refresh-ports-btn')) {
        return;
    }

    const controlGroup = document.querySelector('.control-group');
    const refreshBtn = document.createElement('button');
    refreshBtn.id = 'refresh-ports-btn';
    refreshBtn.textContent = 'Refresh Ports';
    refreshBtn.onclick = function() {
        if (backend && backend.refresh_ports) {
            backend.refresh_ports();
        } else {
            console.log("Requesting port refresh from backend");
            // Just notify the terminal
            term.write("\r\nRequesting port refresh...\r\n");
        }
    };

    // Insert after the port select
    portSelect.parentNode.insertBefore(refreshBtn, portSelect.nextSibling);
}

// Apply theme to terminal
function applyTheme(theme) {
    try {
        console.log('Applying theme to terminal:', theme);

        // Apply theme to terminal
        if (term) {
            term.options.theme = theme;
            // Force terminal to update
            term.refresh(0, term.rows - 1);
        }

        // Update CSS variables
        Object.keys(theme).forEach(key => {
            document.documentElement.style.setProperty(`--terminal-${key}`, theme[key]);
        });

        // Update selection colors specifically
        if (theme.selection && theme.selectionForeground) {
            document.documentElement.style.setProperty('--selection-background', theme.selection);
            document.documentElement.style.setProperty('--selection-text', theme.selectionForeground);
        }

        // Force fit to ensure proper sizing
        if (fitAddon) {
            setTimeout(() => fitAddon.fit(), 100);
        }

        console.log('Theme applied successfully');
    } catch (e) {
        console.error('Error applying theme:', e);
    }
}

// Listen for theme change events
window.addEventListener('themeChanged', function(e) {
    if (e.detail && e.detail.theme) {
        applyTheme(e.detail.theme);
    }
});

// Apply selection styles via CSS
function applySelectionStyles(bg, fg) {
    try {
        const style = document.createElement('style');
        style.textContent = `
            .xterm-selection-layer .xterm-selection {
                background-color: ${bg} !important;
                opacity: 0.6;
            }
            .xterm-selection-layer .xterm-selection.xterm-focus {
                opacity: 0.8;
            }
        `;
        document.head.appendChild(style);

        // Update terminal theme
        if (term) {
            const currentTheme = term.options.theme || {};
            term.options.theme = {
                ...currentTheme,
                selection: bg,
                selectionBackground: bg,
                selectionForeground: fg
            };
            term.refresh(0, term.rows - 1);
        }
    } catch (e) {
        console.error('Error applying selection styles:', e);
    }
}

// Initialize the terminal on page load
document.addEventListener('DOMContentLoaded', function() {
    initTerminal();

    // Set default selection colors
    applySelectionStyles('#504945', '#EBDBB2');
});

// Make functions available to window
window.handle_output = handle_output;
window.applyTheme = applyTheme;
window.applySelectionStyles = applySelectionStyles;
window.updateConnectButton = function(isConnected) {
    window.updateUIConnected(isConnected);
};