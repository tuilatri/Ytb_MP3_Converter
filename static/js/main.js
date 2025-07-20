document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('converter-form');
    const urlInput = document.getElementById('youtube-url');
    const statusMessage = document.getElementById('status-message');
    const downloadLink = document.getElementById('download-link');
    const themeToggle = document.querySelector('.header__theme-toggle');

    // Theme toggle
    themeToggle.addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        if (currentTheme === 'dark') {
            document.documentElement.setAttribute('data-theme', 'light');
            themeToggle.innerHTML = '<i class="fas fa-moon"></i>';
        } else {
            document.documentElement.setAttribute('data-theme', 'dark');
            themeToggle.innerHTML = '<i class="fas fa-sun"></i>';
        }
    });

    // Form submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const url = urlInput.value.trim();

        if (!url) {
            statusMessage.textContent = 'Please enter a valid YouTube URL';
            return;
        }

        statusMessage.textContent = 'Converting...';
        downloadLink.style.display = 'none';

        try {
            const response = await fetch('/convert', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url }),
            });

            const data = await response.json();

            if (response.ok) {
                statusMessage.textContent = 'Conversion successful!';
                downloadLink.href = data.download_url;
                downloadLink.style.display = 'inline-flex';
            } else {
                statusMessage.textContent = data.error || 'An error occurred during conversion';
            }
        } catch (error) {
            statusMessage.textContent = 'Failed to connect to the server';
            console.error('Error:', error);
        }
    });
});