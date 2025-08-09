// Transit ETA polling functionality
document.addEventListener('DOMContentLoaded', function() {
    const transitScripts = document.querySelectorAll('script[data-api][data-target]');
    
    transitScripts.forEach(script => {
        const apiUrl = script.getAttribute('data-api');
        const targetSelector = script.getAttribute('data-target');
        const target = document.querySelector(targetSelector);
        
        if (!target || !apiUrl) return;
        
        let pollInterval;
        let retryCount = 0;
        const maxRetries = 3;
        const pollIntervalMs = 20000; // 20 seconds
        
        function updateTransitInfo(data) {
            if (!data || typeof data !== 'object') {
                showError('Invalid data received');
                return;
            }
            
            const { route, stop, eta_s, status } = data;
            
            let etaText = '—';
            if (typeof eta_s === 'number' && eta_s >= 0) {
                if (eta_s < 60) {
                    etaText = `${eta_s}s`;
                } else {
                    const minutes = Math.floor(eta_s / 60);
                    etaText = `${minutes}m`;
                }
            }
            
            target.innerHTML = `
                <div class="transit-info">
                    <div>
                        <div class="transit-route">${route || '—'}</div>
                        <div class="transit-status">${status || 'Unknown'}</div>
                    </div>
                    <div class="transit-eta">${etaText}</div>
                </div>
            `;
            
            retryCount = 0; // Reset retry count on success
        }
        
        function showError(message) {
            target.innerHTML = `
                <div class="transit-loading" style="color: #fca5a5;">
                    Transit unavailable${retryCount > 0 ? ` (${retryCount}/${maxRetries})` : ''}
                </div>
            `;
        }
        
        function showLoading() {
            target.innerHTML = '<div class="transit-loading">Loading transit data...</div>';
        }
        
        async function fetchTransitData() {
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s timeout
                
                const response = await fetch(apiUrl, {
                    signal: controller.signal,
                    headers: {
                        'Accept': 'application/json',
                    }
                });
                
                clearTimeout(timeoutId);
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                
                const data = await response.json();
                updateTransitInfo(data);
                
            } catch (error) {
                console.warn('Transit API error:', error.message);
                retryCount++;
                
                if (retryCount >= maxRetries) {
                    showError('Service unavailable');
                    if (pollInterval) {
                        clearInterval(pollInterval);
                        pollInterval = null;
                    }
                } else {
                    showError('Retrying...');
                }
            }
        }
        
        // Initial load
        showLoading();
        fetchTransitData();
        
        // Set up polling
        pollInterval = setInterval(fetchTransitData, pollIntervalMs);
        
        // Clean up on page unload
        window.addEventListener('beforeunload', () => {
            if (pollInterval) {
                clearInterval(pollInterval);
            }
        });
        
        // Pause polling when page is not visible
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                if (pollInterval) {
                    clearInterval(pollInterval);
                    pollInterval = null;
                }
            } else {
                if (!pollInterval && retryCount < maxRetries) {
                    fetchTransitData();
                    pollInterval = setInterval(fetchTransitData, pollIntervalMs);
                }
            }
        });
    });
});