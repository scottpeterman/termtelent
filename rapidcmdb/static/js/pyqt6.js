function waitForQtWebChannel() {
    return new Promise((resolve, reject) => {
        let attempts = 0;
        const maxAttempts = 30; // Increased for slower loading
        const interval = 200;   // Check more frequently

        const checkAvailability = () => {
            attempts++;
            console.log(`Checking QWebChannel availability: attempt ${attempts}`);

            // Check all required components
            const qwebChannelAvailable = typeof QWebChannel !== 'undefined';
            const qtAvailable = typeof qt !== 'undefined';
            const transportAvailable = qtAvailable && qt.webChannelTransport;

            console.log({
                QWebChannel: qwebChannelAvailable,
                qt: qtAvailable,
                transport: transportAvailable
            });

            if (qwebChannelAvailable && qtAvailable && transportAvailable) {
                try {
                    new QWebChannel(qt.webChannelTransport, function(channel) {
                        // Debug: log all objects in the channel
                        console.log('QWebChannel objects:', Object.keys(channel.objects));

                        // Set up backend if it exists
                        if (channel.objects.backend) {
                            window.backend = channel.objects.backend;
                        }

                        // Set up theme bridge if it exists
                        if (channel.objects.themeBridge) {
                            window.themeBridge = channel.objects.themeBridge;
                            console.log('themeBridge registered on window');
                        }

                        console.log('QWebChannel initialized successfully');
                        resolve(channel);
                    });
                    return;
                } catch (error) {
                    console.error('Error creating QWebChannel:', error);
                }
            }

            if (attempts >= maxAttempts) {
                reject(new Error(`Failed to initialize QWebChannel after ${maxAttempts} attempts`));
                return;
            }

            setTimeout(checkAvailability, interval);
        };

        // Start checking
        checkAvailability();
    });
}

function setupThemeListener() {
    console.log('Setting up theme listener...');

    // Check for theme bridge - it should be directly on window, not under backend
    if (window.themeBridge) {
        console.log('Found themeBridge, setting up listener...');

        // Connect to theme change signals from Qt
        window.themeBridge.theme_changed.connect(function(themeName) {
            console.log('Theme change received from Qt:', themeName);
            applyThemeChange(themeName);
        });

        // Get current theme on startup
        window.themeBridge.get_current_theme(function(currentTheme) {
            console.log('Current theme from Qt:', currentTheme);
            if (currentTheme) {
                applyThemeChange(currentTheme);
            }
        });
    } else {
        console.log('themeBridge not found on window object');
        console.log('Available objects:', Object.keys(window).filter(k => k.toLowerCase().includes('theme') || k.toLowerCase().includes('bridge')));
    }
}

function applyThemeChange(themeName) {
    console.log('Applying theme change:', themeName);

    // Safeguard: check if we're already on the correct theme
    const urlParams = new URLSearchParams(window.location.search);
    const currentUrlTheme = urlParams.get('theme');

    if (currentUrlTheme === themeName) {
        console.log(`Already on theme ${themeName}, skipping reload`);
        return;
    }

    // Safeguard: prevent rapid reloads
    if (window.lastThemeChange && Date.now() - window.lastThemeChange < 2000) {
        console.log('Preventing rapid theme change - less than 2 seconds since last change');
        return;
    }

    window.lastThemeChange = Date.now();

    // Get current URL and update theme parameter
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set('theme', themeName);

    console.log(`Reloading page with theme: ${themeName}`);

    // Reload the page with new theme
    window.location.href = currentUrl.toString();
}

// Usage
waitForQtWebChannel()
    .then(() => {
        console.log('QWebChannel ready, backend available at window.backend');
        console.log('Available window objects:', Object.keys(window).filter(k => !k.startsWith('_')));

        // Set up theme bridge if available
        setupThemeListener();
    })
    .catch(error => {
        console.error('QWebChannel initialization failed:', error);
    });

// Expose theme functions globally
window.qtThemeHandler = {
    applyTheme: applyThemeChange,
    setupListener: setupThemeListener
};

// --webEngineArgs --remote-debugging-port=<portnumber>