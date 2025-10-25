document.addEventListener('DOMContentLoaded', () => {
    // --- Mock Terminal on Landing Page ---
    const terminalContent = document.getElementById('terminal-content');
    if (terminalContent) {
        // Base dummy log entries
        const baseLogs = [
            'Initializing 1L0Gx AI Core...',
            'Connecting to data streams...',
            'Stream established: aws.cloudtrail.us-east-1',
            'Stream established: gcp.audit.europe-west-2',
            'Stream established: endpoint.security.crowdstrike',
            'Analyzing incoming logs... 1.2M logs/sec',
        ];

        // Add more dummy data dynamically
        const randomLogs = [
            { text: '[INFO] User "alex" logged in from 192.168.1.55', color: '#00ff85' },
            { text: '[INFO] User "claire" logged in from 192.168.1.77', color: '#00ff85' },
            { text: '[WARN] High CPU usage on db-prod-01', color: '#ffd44d' },
            { text: '[WARN] Network latency detected between eu-west-1 and ap-southeast-2', color: '#ffd44d' },
            { text: '[CRITICAL] Multiple failed login attempts for "root" from 103.1.2.3', color: '#ff4d4d' },
            { text: '[CRITICAL] Malware signature match: Trojan.Zeus on host win-srv-02', color: '#ff4d4d' },
            { text: '[SECURITY] AI correlation engine identified potential brute-force attack.', color: '#ff99ff' },
            { text: 'Executing automated response: Block IP 103.1.2.3', color: '#00ffff' },
            { text: 'Executing automated response: Isolate host win-srv-02', color: '#00ffff' },
            { text: 'AI generating incident summary for INC-00871...', color: '#ffffff' },
            { text: 'Summary complete. Awaiting user action.', color: '#ffffff' },
            { text: '[INFO] Monitoring resumed on all active nodes...', color: '#00ff85' },
            { text: '[INFO] New API key issued for user "devops-bot"', color: '#00ff85' },
            { text: '[INFO] Log ingestion rate: 2.3M logs/sec', color: '#00ff85' },
            { text: '[SYSTEM] All clusters stable. AI in passive monitoring mode.', color: '#00ccff' },
        ];

        // Combine and shuffle for randomness
        const logLines = [...baseLogs, ...randomLogs.sort(() => Math.random() - 0.5)];

        let lineIndex = 0;
        let charIndex = 0;

        function typeLog() {
            if (lineIndex >= logLines.length) {
                // Optional: loop animation
                // lineIndex = 0;
                // terminalContent.innerHTML = '';
                // setTimeout(typeLog, 500);
                return;
            }

            const currentLine = logLines[lineIndex];
            const lineText = typeof currentLine === 'string' ? currentLine : currentLine.text;
            const lineColor = typeof currentLine === 'string' ? 'inherit' : currentLine.color;

            if (charIndex < lineText.length) {
                const span = document.createElement('span');
                if (charIndex === 0) {
                    const prefix = document.createTextNode('> ');
                    terminalContent.appendChild(prefix);
                }
                span.textContent = lineText.charAt(charIndex);
                if (lineColor !== 'inherit') {
                    span.style.color = lineColor;
                }
                terminalContent.appendChild(span);
                charIndex++;
                setTimeout(typeLog, 20);
            } else {
                terminalContent.appendChild(document.createTextNode('\n'));
                charIndex = 0;
                lineIndex++;
                const terminalBody = terminalContent.parentElement;
                terminalBody.scrollTop = terminalBody.scrollHeight;
                setTimeout(typeLog, Math.random() * 300 + 100);
            }
        }
        typeLog();
    }

    // --- Active Nav Link Highlighting for App Pages ---
    const navItems = document.querySelectorAll('.sidebar-nav .nav-item');
    if (navItems.length > 0) {
        const currentPage = window.location.pathname.split('/').pop();
        
        navItems.forEach(item => {
            const itemPage = item.getAttribute('href').split('/').pop();
            
            // Remove active class from all items first
            item.classList.remove('active');
            
            // Add active class to the current page's item
            if (itemPage === currentPage) {
                item.classList.add('active');
            }
        });
    }
});
