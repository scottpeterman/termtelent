def launch_theme_editor(window):
    """
    Launch the theme editor as a separate process.

    Args:
        window: The main application window instance
    """
    try:
        import os
        import sys
        import tempfile
        import json
        from PyQt6.QtCore import QProcess, QProcessEnvironment

        # Create a QProcess instance
        process = QProcess(window)

        # Set up environment
        env = QProcessEnvironment.systemEnvironment()
        process.setProcessEnvironment(env)

        # Set up the command and arguments
        python_path = sys.executable
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "widgets/theme_editor.py")
        print(f"launching {script_path}")
        # Create a temporary file to pass the current theme
        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, f"termtel_theme_{os.getpid()}.json")

        # Save current theme data to temp file
        current_theme_name = window.theme if hasattr(window, 'theme') else 'cyberpunk'
        current_theme = window.theme_manager.get_theme(current_theme_name)

        if current_theme:
            try:
                with open(temp_file, 'w') as f:
                    json.dump({
                        'theme_name': current_theme_name,
                        'theme_data': current_theme.to_dict() if hasattr(current_theme, 'to_dict') else current_theme
                    }, f)
            except Exception as e:
                import logging
                logger = logging.getLogger('termtel.theme_editor')
                logger.error(f"Error saving theme data to temp file: {e}")

        # Pass the themes directory path and temp file as arguments
        themes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "themes")
        if not os.path.isdir(themes_dir):
            themes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes")

        args = [script_path, "--themes-dir", themes_dir, "--temp-file", temp_file]

        # Connect signals for monitoring
        process.errorOccurred.connect(lambda error: _handle_theme_editor_error(window, error))
        process.finished.connect(lambda code, status: _handle_theme_editor_finish(window, code, status, temp_file))

        # Start the process
        process.start(python_path, args)

        # Store process reference
        window.theme_editor_process = process

        return process

    except Exception as e:
        import logging
        logger = logging.getLogger('termtel.theme_editor')
        logger.error(f"Error launching theme editor process: {e}")
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(
            window,
            "Theme Editor Error",
            f"Failed to start theme editor process: {str(e)}"
        )
        return None


def _handle_theme_editor_error(window, error):
    """Handle theme editor process errors"""
    from PyQt6.QtCore import QProcess

    error_messages = {
        QProcess.ProcessError.FailedToStart: "The theme editor failed to start",
        QProcess.ProcessError.Crashed: "The theme editor process crashed",
        QProcess.ProcessError.Timedout: "The theme editor process timed out",
        QProcess.ProcessError.WriteError: "Write error occurred",
        QProcess.ProcessError.ReadError: "Read error occurred",
        QProcess.ProcessError.UnknownError: "Unknown error occurred"
    }

    error_msg = error_messages.get(error, "An unknown error occurred")
    import logging
    logger = logging.getLogger('termtel.theme_editor')
    logger.error(f"Theme editor process error: {error_msg}")


def _handle_theme_editor_finish(window, exit_code, exit_status, temp_file):
    """Handle theme editor process completion"""
    import os
    import json
    import logging
    logger = logging.getLogger('termtel.theme_editor')

    # Check for successful completion
    if exit_code == 0:
        # Try to load the theme data from the temp file
        try:
            if os.path.exists(temp_file):
                with open(temp_file, 'r') as f:
                    theme_data = json.load(f)

                # Check if we need to update the theme
                if theme_data.get('apply_theme', False):
                    theme_name = theme_data.get('theme_name')
                    if theme_name:
                        # Reload themes from disk first
                        window.theme_manager._load_custom_themes()
                        # Apply the theme
                        window.switch_theme(theme_name)
                        logger.info(f"Applied theme '{theme_name}' from theme editor")
        except Exception as e:
            logger.error(f"Error loading theme data from temp file: {e}")

    # Clean up temp file
    try:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    except Exception as e:
        logger.error(f"Error removing temp file: {e}")

    # Clean up process reference
    if hasattr(window, 'theme_editor_process'):
        delattr(window, 'theme_editor_process')