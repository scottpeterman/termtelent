import logging
from typing import Optional, Callable


class CallbackHandler(logging.Handler):
    def __init__(self, callback: Callable):
        super().__init__()
        self.callback = callback

    def emit(self, record):
        if self.callback:
            self.callback(self.format(record))

class LoggerManager:
    _instance = None
    _loggers = {}  # Track all loggers
    _current_level = logging.INFO  # Track current level

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerManager, cls).__new__(cls)
        return cls._instance

    def get_logger(self, callback=None):
        """Get or create the singleton logger"""
        name = 'NetworkMapper'  # Single logger name for all components

        if name not in self._loggers:
            # Create new logger
            logger = logging.getLogger(name)
            logger.propagate = False
            logger.setLevel(self._current_level)  # Use tracked level
            # Set root logger level too
            logging.getLogger().setLevel(self._current_level)
            self._loggers[name] = logger

        logger = self._loggers[name]

        if callback:
            # Clear existing handlers
            logger.handlers.clear()
            # Add new handler with callback
            handler = CallbackHandler(callback)
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            handler.setLevel(self._current_level)  # Use tracked level
            logger.addHandler(handler)

        return logger

    def set_level(self, level: str):
        """Set level for all loggers and handlers"""
        # Validate level
        valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        level_upper = level.upper()

        if level_upper not in valid_levels:
            raise ValueError(f'Invalid log level: {level}')

        numeric_level = getattr(logging, level_upper)
        self._current_level = numeric_level  # Store current level

        # Set root logger level
        logging.getLogger().setLevel(numeric_level)

        # Set level for ALL loggers and their handlers
        for logger in self._loggers.values():
            logger.setLevel(numeric_level)
            for handler in logger.handlers:
                handler.setLevel(numeric_level)
# Global instance
logger_manager = LoggerManager()
# Global instance
