/**
 * terminal_theme.js - Theme manager for xterm.js terminal
 *
 * This script manages themes for the xterm.js terminal, ensuring proper
 * selection colors and scrollbar styling.
 */

class TerminalThemeManager {
    constructor() {
        this.styleElement = null;
        this.currentTheme = null;
        this.selectionBg = '#504945';  // Default selection background
        this.selectionFg = '#EBDBB2';  // Default selection foreground
        this.initialize();
    }

    initialize() {
        console.log('TerminalThemeManager: Initializing...');

        // Create style element for theme CSS
        this.styleElement = document.createElement('style');
        this.styleElement.id = 'terminal-theme-style';
        document.head.appendChild(this.styleElement);

        // Apply default selection styles
        this.applySelectionStyles(this.selectionBg, this.selectionFg);

        // Listen for theme change events
        window.addEventListener('themeChanged', (e) => {
            if (e.detail && e.detail.theme) {
                this.applyTheme(e.detail.theme);
            }
        });
    }

    applyTheme(theme) {
        console.log('TerminalThemeManager: Applying theme:', theme);
        this.currentTheme = theme;

        if (!window.term) {
            console.warn('TerminalThemeManager: Terminal not initialized');
            return;
        }

        try {
            // Get selection colors from theme
            this.selectionBg = theme.selection || theme.selectionBackground || '#504945';
            this.selectionFg = theme.selectionForeground || '#EBDBB2';

            // Apply selection colors
            this.applySelectionStyles(this.selectionBg, this.selectionFg);

            // Apply theme to terminal
            if (window.term.options) {
                // xterm.js 5.x approach
                window.term.options.theme = theme;
            } else if (window.term.setOption) {
                // Legacy approach
                window.term.setOption('theme', theme);
            }

            // Apply scrollbar styles
            this.updateScrollbarStyles(theme);

            // Force refresh
            if (window.term.refresh) {
                window.term.refresh(0, window.term.rows - 1);
            }

            // Apply fit if available
            if (window.fitAddon && window.fitAddon.fit) {
                setTimeout(() => window.fitAddon.fit(), 100);
            }

            console.log('TerminalThemeManager: Theme applied successfully');
        } catch (error) {
            console.error('TerminalThemeManager: Error applying theme:', error);
        }
    }

    applySelectionStyles(bg, fg) {
        if (!bg || !fg) {
            console.warn('TerminalThemeManager: Invalid selection colors');
            return;
        }

        console.log('TerminalThemeManager: Applying selection styles:', { bg, fg });

        try {
            // Create styles for selection
            const selectionStyles = `
                /* Direct terminal selection styling */
                .xterm-selection-layer .xterm-selection {
                    background-color: ${bg} !important;
                    opacity: 0.6;
                }
                .xterm-selection-layer .xterm-selection.xterm-focus {
                    opacity: 0.8;
                }

                /* Selection CSS variables */
                :root {
                    --selection-background: ${bg};
                    --selection-text: ${fg};
                }

                /* Text selection styling */
                ::selection {
                    background-color: ${bg};
                    color: ${fg};
                }
            `;

            // Apply to style element
            if (!this.styleElement) {
                this.styleElement = document.createElement('style');
                this.styleElement.id = 'terminal-selection-style';
                document.head.appendChild(this.styleElement);
            }

            this.styleElement.textContent = selectionStyles;

            // Also apply to terminal directly if available
            if (window.term) {
                if (window.term.options) {
                    // Modern xterm.js approach
                    window.term.options.theme = {
                        ...(window.term.options.theme || {}),
                        selection: bg,
                        selectionBackground: bg,
                        selectionForeground: fg
                    };
                } else if (window.term.setOption) {
                    // Legacy approach
                    const currentTheme = window.term.getOption ?
                        window.term.getOption('theme') || {} : {};

                    window.term.setOption('theme', {
                        ...currentTheme,
                        selection: bg,
                        selectionBackground: bg,
                        selectionForeground: fg
                    });
                }
            }

            console.log('TerminalThemeManager: Selection styles applied');
        } catch (error) {
            console.error('TerminalThemeManager: Error applying selection styles:', error);
        }
    }

    updateScrollbarStyles(theme) {
        console.log('TerminalThemeManager: Updating scrollbar styles');

        try {
            // Default scrollbar colors
            const scrollbarBg = theme.background || '#000000';
            const scrollbarThumb = theme.border || '#333333';
            const scrollbarThumbHover = theme.brightBlack || '#555555';

            // Create scrollbar styles
            const scrollbarStyles = `
                /* Terminal scrollbar styling */
                .xterm-viewport::-webkit-scrollbar {
                    width: 10px;
                    height: 10px;
                }

                .xterm-viewport::-webkit-scrollbar-track {
                    background: ${scrollbarBg};
                    border-radius: 0;
                }

                .xterm-viewport::-webkit-scrollbar-thumb {
                    background: ${scrollbarThumb};
                    border-radius: 5px;
                }

                .xterm-viewport::-webkit-scrollbar-thumb:hover {
                    background: ${scrollbarThumbHover};
                }
            `;

            // Create or update style element
            const scrollbarStyleElement = document.getElementById('terminal-scrollbar-style') ||
                                        document.createElement('style');
            scrollbarStyleElement.id = 'terminal-scrollbar-style';
            scrollbarStyleElement.textContent = scrollbarStyles;

            if (!scrollbarStyleElement.parentNode) {
                document.head.appendChild(scrollbarStyleElement);
            }

            console.log('TerminalThemeManager: Scrollbar styles updated');
        } catch (error) {
            console.error('TerminalThemeManager: Error updating scrollbar styles:', error);
        }
    }
}

// Create theme manager instance when document is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing Terminal Theme Manager');
    window.themeManager = new TerminalThemeManager();
});