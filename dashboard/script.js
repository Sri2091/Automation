document.addEventListener('DOMContentLoaded', function() {
    const tabs = document.querySelectorAll('.page-tabs a');
    const pageViews = document.querySelectorAll('.page-view');

    tabs.forEach(tab => {
        tab.addEventListener('click', function(event) {
            event.preventDefault(); // Prevent default anchor behavior

            // Remove active class from all tabs
            tabs.forEach(t => t.classList.remove('active'));
            // Add active class to the clicked tab
            this.classList.add('active');

            const targetPageId = this.getAttribute('data-page') + '-content';

            // Hide all page views
            pageViews.forEach(view => {
                view.classList.remove('active');
                // If you want scrolling position to reset when switching tabs:
                // view.scrollTop = 0;
            });
            
            // Show the target page view
            const targetPage = document.getElementById(targetPageId);
            if (targetPage) {
                targetPage.classList.add('active');
            }
        });
    });
});