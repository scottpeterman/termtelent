import asyncio
import json

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import QUrl, pyqtSlot, QObject, pyqtSignal
import traceback
from pathlib import Path

# Import your message router
# from termtel.termtelng.backend.message_router import MessageRouter
# from termtel.termtelng.backend.sessions import TelemetrySession

# from termtelwidgets import
class TelemetryWidget(QWidget):
    """A widget that encapsulates the Terminal Telemetry web interface"""

    # Signal when cleanup is needed
    cleanup_requested = pyqtSignal()

    def __init__(self, parent=None, base_path=None):
        super().__init__(parent)
        self.base_path = self.resolve_base_path(base_path)
        self._cleanup_done = False
        self.parent = parent  # Store parent reference explicitly

        # Set up event loop
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop exists, create one
            from qasync import QEventLoop
            self.loop = QEventLoop(QApplication.instance())
            asyncio.set_event_loop(self.loop)

        self.setup_ui()


    def resolve_base_path(self, provided_path=None):
        """Resolve the base path for frontend files"""
        if provided_path:
            return Path(provided_path)

        # Default path logic - adjust based on your file structure
        try:
            current_dir = Path(__file__).parent.parent
            return current_dir / 'termtelng' / 'frontend'
        except:
            # Fallback
            return Path.cwd() / 'termtelng' / 'frontend'

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Create web view
        self.web_view = QWebEngineView(self)
        layout.addWidget(self.web_view)
        layout.setContentsMargins(0, 0, 0, 0)

        try:
            # Set up web channel
            self.channel = QWebChannel()

            # Create message router
            # self.message_router = MessageRouter(parent=self)

            # Register objects with channel
            # self.channel.registerObject("messageRouter", self.message_router)

            # Set up the web page
            self.web_view.page().setWebChannel(self.channel)
            self.web_view.page().setZoomFactor(1.0)

            # Connect to loadFinished signal to apply theme after page loads
            # self.web_view.loadFinished.connect(self.on_page_load_finished)

            # Load the frontend
            frontend_path = self.base_path / 'index.html'
            if not frontend_path.exists():
                error_msg = f"Frontend file not found at: {frontend_path}"
                print(error_msg)
                self.show_error_page(error_msg)
                return

            url = QUrl.fromLocalFile(str(frontend_path.absolute()))
            print(f"Loading telemetry frontend from: {url.toString()}")
            self.web_view.setUrl(url)

        except Exception as e:
            error_msg = f"Error setting up telemetry UI: {str(e)}"
            print(error_msg)
            traceback.print_exc()
            self.show_error_page(error_msg)

    def on_page_load_finished(self, success):
        """Handle the page load completed event"""
        if success:
            print("Telemetry frontend loaded successfully")

            # Apply parent's theme immediately after page load
            self.apply_parent_theme()
        else:
            print("Failed to load telemetry frontend")

    def apply_parent_theme(self):
        """Apply the parent application's current theme to this widget"""
        try:
            # Check if parent and theme attributes exist
            if hasattr(self, 'parent') and self.parent and hasattr(self.parent, 'theme'):
                theme_name = self.parent.theme
                print(f"Applying parent's theme to telemetry widget: {theme_name}")
                self.update_theme(theme_name)
            else:
                print("Parent or theme attribute not available")
        except Exception as e:
            print(f"Error applying parent theme: {e}")
            traceback.print_exc()

    def convert_theme_to_telemetry(self, theme_colors):
        """
        Convert a ThemeColors object to format for the telemetry widget

        Args:
            theme_colors: ThemeColors instance

        Returns:
            dict: Theme data in the format expected by telemetry_theme.js
        """
        # Map ThemeColors properties to telemetry theme CSS variables
        css_vars = {
            '--text-primary': theme_colors.text,
            '--text-secondary': theme_colors.grid,
            '--bg-primary': theme_colors.background,
            '--bg-secondary': theme_colors.darker_bg,
            '--border-color': theme_colors.border_light,
            '--accent-color': theme_colors.primary,
            '--scrollbar-track': theme_colors.scrollbar_bg,
            '--scrollbar-thumb': theme_colors.border,
            '--scrollbar-thumb-hover': theme_colors.text,
            '--success-color': theme_colors.success,
            '--error-color': theme_colors.error,
            '--chart-line': theme_colors.line,
            '--chart-grid': theme_colors.grid
        }

        # Create a corresponding terminal theme
        terminal_theme = {}
        if hasattr(theme_colors, 'terminal') and theme_colors.terminal and isinstance(theme_colors.terminal, dict):
            if 'theme' in theme_colors.terminal:
                terminal_theme = theme_colors.terminal['theme']
        else:
            # Map from app theme to terminal theme
            terminal_theme = {
                'foreground': theme_colors.text,
                'background': theme_colors.background,
                'cursor': theme_colors.text,
                'black': theme_colors.darker_bg,
                'red': theme_colors.error,
                'green': theme_colors.success,
                'yellow': theme_colors.line,
                'blue': theme_colors.primary,
                'magenta': theme_colors.secondary,
                'cyan': theme_colors.grid,
                'white': theme_colors.text,
                'brightBlack': theme_colors.darker_bg,
                'brightRed': theme_colors.error,
                'brightGreen': theme_colors.success,
                'brightYellow': theme_colors.line,
                'brightBlue': theme_colors.primary,
                'brightMagenta': theme_colors.secondary,
                'brightCyan': theme_colors.grid,
                'brightWhite': theme_colors.lighter_bg,
                'selectionBackground': theme_colors.selected_bg
            }

        # Determine appropriate corner style based on theme characteristics
        corner_style = self.get_corner_style_for_theme(theme_colors)

        # Return the complete theme data
        return {
            'css_vars': css_vars,
            'terminal': terminal_theme,
            'cornerStyle': corner_style
        }

    def get_corner_style_for_theme(self, theme_colors):
        """
        Determine appropriate corner style based on theme characteristics

        Args:
            theme_colors: ThemeColors instance

        Returns:
            str: Name of the corner style for the theme
        """
        # This mapping is a heuristic - customize based on your preferences
        # Look at color properties to determine the best match

        # Convert any colors to lowercase for comparison
        bg = theme_colors.background.lower() if hasattr(theme_colors.background, 'lower') else '#000000'
        text = theme_colors.text.lower() if hasattr(theme_colors.text, 'lower') else '#ffffff'

        # Cyber themes with dark blue/green backgrounds
        if bg.startswith('#0') or bg.startswith('#1') and ('0' in bg or '1' in bg or '2' in bg):
            return 'hexTech'

        # Neon cyan text themes
        elif text.startswith('#00ff') or text.startswith('#0ff'):
            return 'glowCircuit'

        # Neon blue text themes
        elif text.startswith('#00f') or text.startswith('#0000ff'):
            return 'quantumFlux'

        # Green text themes
        elif '#00' in text or text.startswith('#0f'):
            return 'pulseWave'

        # Amber/orange text themes
        elif text.startswith('#f') or text.startswith('#ff'):
            return 'neonGrid'

        # Dark themes
        elif bg.startswith('#1') or bg.startswith('#2'):
            return 'minimalist'

        # Light themes
        else:
            return 'rounded'

    def inject_theme(self, theme_name):
        """
        Inject a termtel theme into the telemetry widget's theme system

        Args:
            theme_name: Name of the termtel theme to apply
        """
        try:
            from termtel.themes3 import ThemeLibrary
            import json

            # Get theme manager instance
            theme_library = ThemeLibrary()

            # Get the theme colors
            theme_colors = theme_library.get_theme(theme_name)

            if not theme_colors:
                print(f"Theme '{theme_name}' not found")
                return

            # Create CSS vars object for theme_colors
            css_vars = {
                '--text-primary': theme_colors.border,
                '--text-secondary': theme_colors.text,
                '--accent-color': theme_colors.primary,
                '--bg-primary': theme_colors.background,
                '--bg-secondary': theme_colors.darker_bg,
                '--border-color': theme_colors.border,
                '--grid-color': theme_colors.grid,
                '--scrollbar-track': theme_colors.scrollbar_bg,
                '--scrollbar-thumb': theme_colors.border,
                '--scrollbar-thumb-hover': theme_colors.text
            }

            # Create terminal theme object
            term_theme = {}
            if hasattr(theme_colors, 'terminal') and theme_colors.terminal and isinstance(theme_colors.terminal,
                                                                                          dict) and 'theme' in theme_colors.terminal:
                # Use terminal colors directly from theme definition
                term_theme = theme_colors.terminal['theme']
            else:
                # Map from app theme to terminal theme
                term_theme = {
                    'foreground': theme_colors.text,
                    'background': theme_colors.background,
                    'cursor': theme_colors.text,
                    'cursorAccent': theme_colors.background,
                    'black': theme_colors.darker_bg,
                    'red': theme_colors.error,
                    'green': theme_colors.success,
                    'yellow': theme_colors.line,
                    'blue': theme_colors.primary,
                    'magenta': theme_colors.secondary,
                    'cyan': theme_colors.grid,
                    'white': theme_colors.text,
                    'brightBlack': theme_colors.darker_bg,
                    'brightRed': theme_colors.error,
                    'brightGreen': theme_colors.success,
                    'brightYellow': theme_colors.line,
                    'brightBlue': theme_colors.primary,
                    'brightMagenta': theme_colors.secondary,
                    'brightCyan': theme_colors.grid,
                    'brightWhite': theme_colors.lighter_bg
                }

            # Create simple theme style
            theme_style = f"""
                .interface-row {{ border-bottom: 1px solid {theme_colors.border_light}; }}
                .interface-name {{ color: {theme_colors.text}; }}
                .interface-status.up {{ color: {theme_colors.success}; }}
                .interface-status.down {{ color: {theme_colors.error}; }}
            """

            # First add the theme to the global theme objects
            register_js = f"""
            (function() {{
                // Make sure theme objects exist
                if (!window.THEME_COLORS) window.THEME_COLORS = {{}};
                if (!window.TERMINAL_THEMES) window.TERMINAL_THEMES = {{}};
                if (!window.THEME_STYLES) window.THEME_STYLES = {{}};

                // Register the theme
                window.THEME_COLORS['{theme_name}'] = {json.dumps(css_vars)};
                window.TERMINAL_THEMES['{theme_name}'] = {json.dumps(term_theme)};
                window.THEME_STYLES['{theme_name}'] = `{theme_style}`;

                console.log('Successfully registered theme: {theme_name}');
            }})();
            """

            # Run the registration script first
            self.web_view.page().runJavaScript(register_js)

            # Then call the apply theme function after a brief delay
            apply_js = f"""
            setTimeout(function() {{
                if (window.ThemeUtils) {{
                    window.ThemeUtils.applyTheme('{theme_name}');
                    console.log('Applied theme: {theme_name}');
                }} else {{
                    console.error('ThemeUtils not found!');
                }}
            }}, 100);
            """

            self.web_view.page().runJavaScript(apply_js)

        except Exception as e:
            print(f"Error injecting theme: {e}")
            import traceback
            traceback.print_exc()

    def update_theme(self, theme_name):
        """Update the theme of the telemetry widget"""
        try:
            # Inject theme directly
            self.inject_theme(theme_name)
        except Exception as e:
            print(f"Error updating telemetry theme: {e}")
            import traceback
            traceback.print_exc()
    def show_error_page(self, message):
        """Show an error page in the web view"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Error</title>
            <style>
                body {{ 
                    font-family: Arial, sans-serif;
                    background-color: #1a1a1a;
                    color: #ff4444;
                    margin: 0;
                    padding: 20px;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                }}
                .error-container {{
                    border: 1px solid #ff4444;
                    padding: 20px;
                    border-radius: 5px;
                    max-width: 600px;
                    text-align: center;
                }}
                h1 {{ color: #ff7777; }}
                pre {{ 
                    background-color: #333;
                    padding: 10px;
                    border-radius: 3px;
                    overflow: auto;
                    text-align: left;
                    color: #ddd;
                }}
            </style>
        </head>
        <body>
            <div class="error-container">
                <h1>Terminal Telemetry Error</h1>
                <p>Failed to initialize the telemetry interface:</p>
                <pre>{message}</pre>
            </div>
        </body>
        </html>
        """
        self.web_view.setHtml(html)

    def cleanup(self):
        """Perform cleanup operations"""
        if self._cleanup_done:
            return

        # try:
        #     print("Starting comprehensive telemetry cleanup...")
        #
        #     # Use the synchronous cleanup method instead of the async one
        #     if hasattr(self.message_router, 'cleanup_sync'):
        #         self.message_router.cleanup_sync()
        #     else:
        #         print("Warning: MessageRouter does not have cleanup_sync method")
        #
        #     self._cleanup_done = True
        #     print("Telemetry cleanup completed")
        #
        # except Exception as e:
        #     print(f"Error during telemetry cleanup: {e}")
        #     traceback.print_exc()
        #
        # # Emit cleanup signal to notify parent
        # self.cleanup_requested.emit()

    def cleanup_sync(self):
        """Synchronous cleanup for widget usage"""
        print("Running MessageRouter cleanup_sync")
        # for session_id, session in list(self.sessions.items()):
        #     try:
                # # Special handling for TelemetrySession
                # if isinstance(session, TelemetrySession):
                #     print(f"Cleaning up telemetry session: {session_id}")
                #     # Stop the collector if it exists
                #     if hasattr(session, 'collector') and session.collector:
                #         if hasattr(session.collector, 'isRunning') and session.collector.isRunning():
                #             print(f"Stopping collector thread")
                #             session.collector._is_running = False
                #             session.collector.quit()
                #             session.collector.wait(1000)  # Wait with timeout
                #
                #     # Mark session as inactive
                #     session._active = False
                #
                #     # Create and run a temporary event loop to synchronously disconnect
                #     try:
                #         temp_loop = asyncio.new_event_loop()
                #         asyncio.set_event_loop(temp_loop)
                #         temp_loop.run_until_complete(session.disconnect())
                #         temp_loop.close()
                #     except Exception as e:
                #         print(f"Error in sync disconnect: {e}")

            #     # For other session types
            #     elif hasattr(session, 'stop_sync'):
            #         session.stop_sync()
            #     # Fallback to async if needed
            #     elif hasattr(session, 'stop'):
            #         try:
            #             temp_loop = asyncio.new_event_loop()
            #             asyncio.set_event_loop(temp_loop)
            #             temp_loop.run_until_complete(session.stop())
            #             temp_loop.close()
            #         except Exception as e:
            #             print(f"Error in fallback async stop: {e}")
            #
            # except Exception as e:
            #     print(f"Error stopping session {session_id}: {e}")
            #     traceback.print_exc()

    def closeEvent(self, event):
        """Handle widget close event"""
        self.cleanup()
        # self.cleanup_requested.emit()
        event.accept()


def update_theme(self, theme_name):
    """Update the theme of the telemetry widget"""
    try:
        # Try to inject theme directly from termtel
        self.inject_theme(theme_name)
    except Exception as e:
        print(f"Error updating telemetry theme: {e}")
        import traceback
        traceback.print_exc()

        # Fallback to simple theme application
        script = f"if (window.ThemeUtils) {{ window.ThemeUtils.applyTheme('{theme_name}'); }}"
        self.web_view.page().runJavaScript(script)