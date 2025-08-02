// Simple, safe download handler - only intercepts obvious download scenarios
(function() {
    console.log("Safe download handler loaded");

    // Only handle very specific file extensions that should never be displayed
    const FORCE_DOWNLOAD_EXTENSIONS = ['.xml', '.drawio', '.json', '.csv', '.xlsx'];

    // Simple function to check if URL should be downloaded
    function isDownloadFile(url) {
        if (!url) return false;
        const urlLower = url.toLowerCase();
        return FORCE_DOWNLOAD_EXTENSIONS.some(ext => urlLower.endsWith(ext)) ||
               urlLower.includes('/download/') ||
               urlLower.includes('/export/');
    }

    // Only override window.open for download files
    const originalOpen = window.open;
    window.open = function(url, target, features) {
        if (isDownloadFile(url)) {
            console.log("Download detected in window.open:", url);
            window.location.href = url;
            return null;
        }
        return originalOpen.call(this, url, target, features);
    };

    // Handle download attribute links
    document.addEventListener('click', function(e) {
        const link = e.target.closest('a[download]');
        if (link && link.href) {
            console.log("Download link clicked:", link.href);
            e.preventDefault();
            window.location.href = link.href;
        }
    });

    console.log("Safe download handler ready");
})();