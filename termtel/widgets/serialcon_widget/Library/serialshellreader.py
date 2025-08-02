from PyQt6.QtCore import pyqtSignal, QThread
import serial

class SerialReaderThread(QThread):
    data_ready = pyqtSignal(str)

    def __init__(self, serial_port):
        super().__init__()
        self.serial_port = serial_port
        self._is_running = True  # A flag to control the thread's loop

    def run(self):
        while self._is_running and self.serial_port.is_open:
            try:
                data = self.serial_port.readline().decode('utf-8')
                if data:  # only emit data if something is read
                    self.data_ready.emit(data)
            except serial.SerialException as e:
                print(f"Error while reading from serial port: {e}")
                self._is_running = False  # Stop the thread if there is a serial error
            except Exception as e:
                print(f"Unhandled exception: {e}")
                self._is_running = False  # Stop the thread on unhandled exceptions

    def stop(self):
        """Stop the thread."""
        self._is_running = False
