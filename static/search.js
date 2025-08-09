// Client-side search functionality for tables
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('search');
    const searchContainer = document.querySelector('[data-search]');
    
    if (!searchInput || !searchContainer) return;
    
    // Find the table to search in
    const table = searchContainer.querySelector('table');
    if (!table) return;
    
    const tbody = table.querySelector('tbody');
    const rows = tbody ? Array.from(tbody.querySelectorAll('tr')) : Array.from(table.querySelectorAll('tr')).slice(1);
    
    function performSearch(query) {
        const searchTerm = query.toLowerCase().trim();
        
        rows.forEach(row => {
            const text = row.textContent.toLowerCase();
            const matches = searchTerm === '' || text.includes(searchTerm);
            row.style.display = matches ? '' : 'none';
        });
        
        // Update results count
        const visibleRows = rows.filter(row => row.style.display !== 'none');
        updateResultsCount(visibleRows.length, rows.length);
    }
    
    function updateResultsCount(visible, total) {
        let countElement = document.getElementById('search-count');
        if (!countElement) {
            countElement = document.createElement('div');
            countElement.id = 'search-count';
            countElement.className = 'search-count';
            countElement.style.cssText = 'margin-top: 0.5rem; font-size: 0.875rem; color: #888;';
            searchInput.parentElement.appendChild(countElement);
        }
        
        if (visible === total) {
            countElement.textContent = `${total} items`;
        } else {
            countElement.textContent = `${visible} of ${total} items`;
        }
    }
    
    // Initialize count
    updateResultsCount(rows.length, rows.length);
    
    // Add search functionality
    searchInput.addEventListener('input', function(e) {
        performSearch(e.target.value);
    });
    
    // Add keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Focus search on '/' key
        if (e.key === '/' && e.target !== searchInput) {
            e.preventDefault();
            searchInput.focus();
        }
        
        // Clear search on Escape
        if (e.key === 'Escape' && e.target === searchInput) {
            searchInput.value = '';
            performSearch('');
            searchInput.blur();
        }
    });
    
    // Add placeholder hint
    const originalPlaceholder = searchInput.placeholder;
    searchInput.placeholder = `${originalPlaceholder} (Press / to focus)`;
});