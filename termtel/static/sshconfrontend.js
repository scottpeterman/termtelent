// Add this at the beginning of the script for debugging backend methods
console.log("Backend methods available:");
setTimeout(() => {
    if (window.backend) {
        try {
            console.log("Backend object exists");
            for (let prop in window.backend) {
                if (typeof window.backend[prop] === 'function') {
                    console.log(`- ${prop} (function)`);
                } else {
                    console.log(`- ${prop} (${typeof window.backend[prop]})`);
                }
            }
        } catch (e) {
            console.error("Error inspecting backend:", e);
        }
    } else {
        console.log("Backend object not available");
    }
}, 1000); // Delay to ensure backend is loaded// Function to handle clipboard operations through the Qt backend
function qtClipboardOperation(operation, text) {
    console.log(`Attempting Qt clipboard operation: ${operation}`, text ? `with text length: ${text.length}` : "");

    try {
        if (window.backend) {
            if (operation === 'copy' && text) {
                console.log("Sending copy request to Qt backend");
                window.backend.clipboard_copy(text);
                return true;
            } else if (operation === 'paste') {
                console.log("Requesting paste from Qt backend");
                // Return a promise to match Clipboard API style
                return new Promise((resolve, reject) => {
                    try {
                        // Create a custom event listener for the paste result
                        window.handlePasteResult = function(pasteText) {
                            console.log(`Received paste result from Qt backend, length: ${pasteText ? pasteText.length : 0}`);
                            resolve(pasteText);
                            delete window.handlePasteResult; // Clean up
                        };

                        // Request paste operation from backend
                        window.backend.clipboard_paste();
                    } catch (error) {
                        console.error("Error in Qt paste operation:", error);
                        reject(error);
                        delete window.handlePasteResult; // Clean up
                    }
                });
            }
        } else {
            console.error("Backend not available for Qt clipboard operation");
            return false;
        }
    } catch (error) {
        console.error(`Error in qtClipboardOperation(${operation}):`, error);
        return false;
    }
}// Initialize terminal with specific options
var term = new Terminal({
    allowProposedApi: true,
    scrollback: 1000,
    fontSize: 14,
    fontFamily: 'monospace',
    theme: {
        background: '#141414',
        foreground: '#ffffff'
    },
    cursorBlink: true
});

// Open terminal in the DOM
term.open(document.getElementById('terminal'));

// Initialize and load the fit addon
const fitAddon = new FitAddon.FitAddon();
term.loadAddon(fitAddon);

// Initial fit with slight delay to ensure proper rendering
setTimeout(() => {
    fitAddon.fit();
}, 0);

// Enable fit on the terminal whenever the window is resized
window.addEventListener('resize', () => {
    fitAddon.fit();
    try {
        size_dim = 'cols:' + term.cols + '::rows:' + term.rows;
        console.log("front end window resize event: " + size_dim);
        backend.set_pty_size(size_dim);
    } catch (error) {
        console.error(error);
        console.log("Channel may not be up yet!");
    }
});

// When data is entered into the terminal, send it to the backend
term.onData(e => {
    backend.write_data(e);
});

// Function to handle incoming data from the backend
window.handle_output = function(data) {
    term.write(data);
};

// Initialize terminal themes
const terminal_themes = {
    "Cyberpunk": {
        foreground: '#0affff',
        background: '#121212',
        cursor: '#0a8993'
    },
    "Dark": {
        foreground: '#ffffff',
        background: '#1e1e1e',
        cursor: '#ffffff'
    },
    "Light": {
        foreground: '#000000',
        background: '#ffffff',
        cursor: '#000000'
    },
    "Green": {
        foreground: '#00ff00',
        background: '#000000',
        cursor: '#00ff00'
    },
    "Amber": {
        foreground: '#ffb000',
        background: '#000000',
        cursor: '#ffb000'
    },
    "Neon": {
        foreground: '#ff00ff',
        background: '#000000',
        cursor: '#ff00ff'
    }
};

// Function to change terminal theme
window.changeTheme = function(themeName) {
    const theme = terminal_themes[themeName];
    if (theme) {
        term.setOption('theme', theme);

        // Update scrollbar style
        let scrollbarStyle = document.getElementById('terminal-scrollbar-style');
        if (!scrollbarStyle) {
            scrollbarStyle = document.createElement('style');
            scrollbarStyle.id = 'terminal-scrollbar-style';
            document.head.appendChild(scrollbarStyle);
        }

        scrollbarStyle.innerHTML = `
            .xterm-viewport::-webkit-scrollbar {
                width: 12px;
            }
            .xterm-viewport::-webkit-scrollbar-track {
                background: ${theme.background};
            }
            .xterm-viewport::-webkit-scrollbar-thumb {
                background: ${theme.foreground};
                opacity: 0.5;
            }
            .xterm-viewport::-webkit-scrollbar-thumb:hover {
                background: ${theme.cursor};
            }
        `;

        // Update body background color
        document.body.style.backgroundColor = themeName === 'Light' ? '#ffffff' : '#000000';

        // Ensure terminal fits properly after theme change
        fitAddon.fit();
    }
};

// Function to copy terminal selection to clipboard
function copyTerminalSelection() {
    console.log("copyTerminalSelection called");
    const selection = term.getSelection();
    console.log("Terminal selection:", selection);

    if (selection) {
        // Check if backend has clipboard_copy method
        if (window.backend && typeof window.backend.clipboard_copy === 'function') {
            console.log("Using backend.clipboard_copy directly");
            try {
                window.backend.clipboard_copy(selection);
                console.log("Copy request sent directly to backend");
                return;
            } catch (backendError) {
                console.error("Backend clipboard_copy failed:", backendError);
                // Continue to fallbacks
            }
        } else {
            console.log("backend.clipboard_copy not available, using browser APIs");
        }

        try {
            console.log("Attempting to copy using Clipboard API");
            // Try to use clipboard API
            navigator.clipboard.writeText(selection)
                .then(() => {
                    console.log("Successfully copied text using Clipboard API");
                })
                .catch(err => {
                    console.error('Could not copy text using Clipboard API:', err);
                    console.log("Falling back to execCommand method");
                    // Fallback to execCommand method
                    copyUsingExecCommand(selection);
                });
        } catch (error) {
            console.error('Error copying text:', error);
            console.log("Falling back to execCommand method due to error");
            // Fallback to execCommand method
            copyUsingExecCommand(selection);
        }
    } else {
        console.log("No text selected to copy");
    }
}

// Function to copy text using execCommand (fallback method)
function copyUsingExecCommand(text) {
    console.log("copyUsingExecCommand called with text:", text.substring(0, 20) + (text.length > 20 ? "..." : ""));

    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.top = '0';
    textArea.style.left = '0';
    textArea.style.width = '2em';
    textArea.style.height = '2em';
    textArea.style.opacity = '0';
    textArea.style.zIndex = '-1';

    document.body.appendChild(textArea);
    console.log("Temporary textarea added to document");
    textArea.select();
    console.log("Text selected in textarea");

    try {
        const successful = document.execCommand('copy');
        console.log("execCommand copy result:", successful ? "success" : "failed");
        if (!successful) {
            console.error('execCommand copy failed');
        }
    } catch (err) {
        console.error('execCommand error:', err);
    }

    document.body.removeChild(textArea);
    console.log("Temporary textarea removed from document");
}

// Function to paste text to terminal
function pasteToTerminal() {
    console.log("pasteToTerminal called");

    // Focus the terminal first
    term.focus();
    console.log("Terminal focused");

    // Check if backend has clipboard_paste method
    if (window.backend && typeof window.backend.clipboard_paste === 'function') {
        console.log("Using backend.clipboard_paste directly");
        try {
            // Set up paste result handler before calling backend
            window.handlePasteResult = function(text) {
                console.log("Received paste result from backend handler, length:", text ? text.length : 0);
                if (text) {
                    try {
                        // Send directly to term instead of backend
                        term.paste(text);
                        console.log("Text pasted directly to terminal");
                    } catch (pasteError) {
                        console.error("Error pasting to terminal:", pasteError);
                        // Try write to backend as fallback
                        try {
                            backend.write_data(text);
                            console.log("Text sent to backend as fallback");
                        } catch (writeError) {
                            console.error("Backend write error:", writeError);
                        }
                    }
                } else {
                    console.log("Clipboard appears to be empty");
                }
                // Clean up
                delete window.handlePasteResult;
            };

            // Call backend paste method
            window.backend.clipboard_paste();
            console.log("Paste request sent to backend");
            return;
        } catch (backendError) {
            console.error("Backend clipboard_paste failed:", backendError);
            // Continue to fallbacks
            delete window.handlePasteResult; // Clean up if error
        }
    } else {
        console.log("backend.clipboard_paste not available, using browser APIs");
    }

    try {
        console.log("Attempting to use Clipboard API for paste");
        // Try to use clipboard API
        navigator.clipboard.readText()
            .then(text => {
                console.log("Successfully read from clipboard, text length:", text ? text.length : 0);
                if (text) {
                    try {
                        // Try direct paste to terminal first
                        term.paste(text);
                        console.log("Text pasted directly to terminal via Clipboard API");
                    } catch (pasteError) {
                        console.error("Error pasting to terminal:", pasteError);
                        // Fall back to backend write
                        try {
                            backend.write_data(text);
                            console.log("Text sent to backend after paste failed");
                        } catch (writeError) {
                            console.error("Backend write error:", writeError);
                        }
                    }
                } else {
                    console.log("Clipboard appears to be empty");
                }
            }).catch(err => {
                console.error('Could not paste text using Clipboard API:', err);
                console.log("Falling back to keyboard shortcut for paste");
                // Trigger paste via keyboard shortcut as fallback
                triggerPasteEvent();
            });
    } catch (error) {
        console.error('Error in paste operation:', error);
        console.log("Falling back to keyboard shortcut due to error");
        // Trigger paste via keyboard shortcut
        triggerPasteEvent();
    }
}

// Function for combined copy and paste
function copyAndPaste() {
    console.log("copyAndPaste called");

    const selection = term.getSelection();
    console.log("Terminal selection for copy & paste:", selection ? selection.substring(0, 20) + (selection.length > 20 ? "..." : "") : "none");

    if (selection) {
        // Copy to clipboard first (for user convenience)
        if (window.backend && typeof window.backend.clipboard_copy === 'function') {
            console.log("Copying to clipboard via backend");
            try {
                window.backend.clipboard_copy(selection);
            } catch (copyError) {
                console.error("Backend clipboard_copy failed:", copyError);
                // Try browser API as fallback
                try {
                    navigator.clipboard.writeText(selection).catch(err => {
                        console.error("Clipboard API copy failed:", err);
                    });
                } catch (e) {
                    console.error("Browser clipboard API failed:", e);
                }
            }
        } else {
            console.log("Using browser clipboard API for copy");
            try {
                navigator.clipboard.writeText(selection).catch(err => {
                    console.error("Clipboard API copy failed:", err);
                });
            } catch (e) {
                console.error("Browser clipboard API failed:", e);
            }
        }

        // Now paste directly to terminal
        console.log("Pasting directly to terminal");
        try {
            // Try direct paste to terminal first
            term.paste(selection);
            console.log("Selection pasted directly to terminal");
        } catch (pasteError) {
            console.error("Error pasting to terminal:", pasteError);
            // Fall back to backend write
            try {
                backend.write_data(selection);
                console.log("Selection sent to backend as fallback");
            } catch (writeError) {
                console.error("Backend write error:", writeError);
            }
        }
    } else {
        console.log("No text selected for copy & paste");
    }
}

// Function to trigger paste via keyboard shortcut
function triggerPasteEvent() {
    console.log("triggerPasteEvent called");

    // Focus the terminal
    term.focus();
    console.log("Terminal focused for keyboard shortcut paste");

    // Determine platform for correct key combination
    const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
    console.log("Platform detection - isMac:", isMac);

    // Create and dispatch a keyboard event (Ctrl+V or Command+V)
    try {
        console.log("Creating keyboard event for paste");
        const event = new KeyboardEvent('keydown', {
            key: 'v',
            code: 'KeyV',
            ctrlKey: !isMac,
            metaKey: isMac,
            bubbles: true
        });

        // Log the event details
        console.log("Keyboard event created:", {
            key: event.key,
            code: event.code,
            ctrlKey: event.ctrlKey,
            metaKey: event.metaKey,
            bubbles: event.bubbles
        });

        // Dispatch to the terminal element
        const terminalElement = document.getElementById('terminal');
        console.log("Dispatching paste keyboard event to terminal element");
        terminalElement.dispatchEvent(event);
        console.log("Paste keyboard event dispatched");
    } catch (error) {
        console.error("Error creating or dispatching keyboard event:", error);
    }
}

// Create and add custom context menu styles
function addContextMenuStyles() {
    const styleElement = document.createElement('style');
    styleElement.id = 'context-menu-style';
    styleElement.innerHTML = `
        #custom-context-menu {
            position: absolute;
            z-index: 1000;
            background-color: #1e1e1e;
            border: 1px solid #444;
            border-radius: 4px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.5);
            padding: 5px 0;
            min-width: 120px;
            display: none;
            user-select: none;
        }

        .context-menu-item {
            padding: 8px 12px;
            cursor: pointer;
            color: #fff;
            font-size: 14px;
            transition: background-color 0.2s;
        }

        .context-menu-item:hover {
            background-color: #444;
        }

        .context-menu-item + .context-menu-item {
            border-top: 1px solid #333;
        }
    `;
    document.head.appendChild(styleElement);
}

// Create the context menu
function createContextMenu() {
    // Add context menu styles first
    addContextMenuStyles();

    // Create the menu container
    const contextMenu = document.createElement('div');
    contextMenu.id = 'custom-context-menu';

    // Add Copy menu item
    const copyItem = document.createElement('div');
    copyItem.textContent = 'Copy';
    copyItem.className = 'context-menu-item';
    copyItem.addEventListener('click', (e) => {
        e.preventDefault();
        hideContextMenu();
        copyTerminalSelection();
    });
    contextMenu.appendChild(copyItem);

    // Add Paste menu item
    const pasteItem = document.createElement('div');
    pasteItem.textContent = 'Paste';
    pasteItem.className = 'context-menu-item';
    pasteItem.addEventListener('click', (e) => {
        e.preventDefault();
        hideContextMenu();
        pasteToTerminal();
    });
    contextMenu.appendChild(pasteItem);

    // Add Copy & Paste menu item
    const copyPasteItem = document.createElement('div');
    copyPasteItem.textContent = 'Copy & Paste';
    copyPasteItem.className = 'context-menu-item';
    copyPasteItem.addEventListener('click', (e) => {
        e.preventDefault();
        hideContextMenu();
        copyAndPaste();
    });
    contextMenu.appendChild(copyPasteItem);

    // Add the menu to document
    document.body.appendChild(contextMenu);

    return contextMenu;
}

// Function to show context menu
function showContextMenu(x, y) {
    const menu = document.getElementById('custom-context-menu');
    if (!menu) return;

    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    menu.style.display = 'block';

    // Hide menu when clicking outside
    setTimeout(() => {
        document.addEventListener('click', hideContextMenu, { once: true });
    }, 0);
}

// Function to hide context menu
function hideContextMenu() {
    const menu = document.getElementById('custom-context-menu');
    if (!menu) return;

    menu.style.display = 'none';
    // Refocus on terminal
    term.focus();
}

// Setup the context menu and handlers
function setupContextMenu() {
    console.log("Setting up context menu");

    // Create the context menu
    createContextMenu();
    console.log("Context menu created");

    // Add context menu event
    const terminalElement = document.getElementById('terminal');
    console.log("Adding contextmenu event listener to terminal element");

    terminalElement.addEventListener('contextmenu', (e) => {
        console.log("Context menu event triggered at position:", e.pageX, e.pageY);
        e.preventDefault();
        showContextMenu(e.pageX, e.pageY);
        console.log("Context menu displayed");
        return false;
    });

    // Log when terminal is clicked to ensure event binding is working
    terminalElement.addEventListener('click', () => {
        console.log("Terminal clicked - context menu should be set up");
    });

    // Hide context menu when pressing Escape
    console.log("Adding keydown event listener for Escape key");
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            console.log("Escape key pressed - hiding context menu");
            hideContextMenu();
        }
    });

    console.log("Context menu setup complete");
}

// Call setup function when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    setupContextMenu();
});

// Establish a connection with the Qt backend
new QWebChannel(qt.webChannelTransport, function(channel) {
    window.backend = channel.objects.backend;
});

// Window load event handler
window.onload = function() {
    term.focus();

    // Force a final fit after everything is loaded
    setTimeout(() => {
        fitAddon.fit();
    }, 100);

    // Setup context menu if it wasn't already
    if (!document.getElementById('custom-context-menu')) {
        setupContextMenu();
    }
};