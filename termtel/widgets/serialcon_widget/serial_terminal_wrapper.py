# Save this as serial_terminal_wrapper.py in your termtel/widgets/ directory

class SerialTerminalWrapper:
    """Wrapper class to standardize serial terminal interface for tab management"""

    def __init__(self, terminal_widget):
        self.terminal = terminal_widget

    def cleanup(self):
        """Handle cleanup when tab is closed"""
        if hasattr(self.terminal, 'cleanup'):
            self.terminal.cleanup()
        elif hasattr(self.terminal, 'backend') and hasattr(self.terminal.backend, 'disconnect'):
            # Try to disconnect the serial backend
            try:
                self.terminal.backend.disconnect()
            except Exception as e:
                print(f"Error disconnecting serial: {e}")