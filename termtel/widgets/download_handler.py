import os
import uuid
import logging
from pathlib import Path
from PyQt6.QtCore import QUrl, QStandardPaths
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEngineDownloadRequest

logger = logging.getLogger(__name__)


class DownloadHandler:
    """Handles file downloads from QWebEngineView"""

    def __init__(self, parent_widget):
        self.parent_widget = parent_widget

    def handle_download(self, download_request: QWebEngineDownloadRequest):
        """Handle a download request with a save dialog"""
        try:
            # Get suggested filename
            suggested_filename = download_request.suggestedFileName()
            if not suggested_filename:
                suggested_filename = "download"

            # Get default downloads directory
            downloads_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
            default_path = os.path.join(downloads_dir, suggested_filename)

            # Show save dialog
            file_path, _ = QFileDialog.getSaveFileName(
                self.parent_widget,
                "Save File",
                default_path,
                "All Files (*.*)"
            )

            if file_path:
                # Set the download path
                download_request.setDownloadFileName(file_path)

                # Accept the download
                download_request.accept()

                # Connect to finished signal to show completion message
                download_request.isFinishedChanged.connect(
                    lambda: self._download_finished(download_request, file_path)
                )

                logger.info(f"Download started: {file_path}")
            else:
                # User cancelled
                download_request.cancel()
                logger.info("Download cancelled by user")

        except Exception as e:
            logger.error(f"Error handling download: {e}")
            download_request.cancel()
            QMessageBox.warning(
                self.parent_widget,
                "Download Error",
                f"Failed to start download: {e}"
            )

    def _download_finished(self, download_request: QWebEngineDownloadRequest, file_path: str):
        """Called when download is finished"""
        try:
            if download_request.state() == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
                logger.info(f"Download completed: {file_path}")

                # Show completion message
                reply = QMessageBox.question(
                    self.parent_widget,
                    "Download Complete",
                    f"File downloaded successfully:\n{file_path}\n\nWould you like to open the containing folder?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )

                if reply == QMessageBox.StandardButton.Yes:
                    # Open the containing folder
                    self._open_containing_folder(file_path)

            elif download_request.state() == QWebEngineDownloadRequest.DownloadState.DownloadInterrupted:
                logger.error(f"Download interrupted: {file_path}")
                QMessageBox.warning(
                    self.parent_widget,
                    "Download Failed",
                    f"Download was interrupted:\n{file_path}"
                )
            elif download_request.state() == QWebEngineDownloadRequest.DownloadState.DownloadCancelled:
                logger.info(f"Download cancelled: {file_path}")

        except Exception as e:
            logger.error(f"Error in download finished handler: {e}")

    def _open_containing_folder(self, file_path: str):
        """Open the folder containing the downloaded file"""
        try:
            import subprocess
            import platform

            folder_path = os.path.dirname(file_path)

            system = platform.system()
            if system == "Windows":
                # Windows - open with explorer and select the file
                subprocess.run(["explorer", "/select,", file_path], check=False)
            elif system == "Darwin":  # macOS
                subprocess.run(["open", "-R", file_path], check=False)
            else:  # Linux and others
                subprocess.run(["xdg-open", folder_path], check=False)

        except Exception as e:
            logger.error(f"Failed to open containing folder: {e}")

