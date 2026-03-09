"""Kafka Translator Dashboard — Real-time metrics web interface."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.staticfiles import StaticFiles

# Embedded minimal dashboard HTML (no external dependencies)
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Kafka Translator Dashboard</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f172a; color: #e2e8f0;
      min-height: 100vh; padding: 2rem;
    }
    header {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid #334155;
    }
    h1 { font-size: 1.25rem; color: #38bdf8; }
    .status-badge {
      padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.875rem;
      background: #1e293b; border: 1px solid #475569;
    }
    .status-badge.running { background: #064e3b; border-color: #10b981; color: #34d399; }
    .status-badge.stopped { background: #7f1d1d; border-color: #ef4444; color: #f87171; }
    .grid {
      display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    }
    .card {
      background: #1e293b; border-radius: 0.75rem; padding: 1rem; border: 1px solid #334155;
    }
    .card h2 { font-size: 0.875rem; color: #94a3b8; margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 1px; }
    .value { font-size: 2rem; font-weight: 700; color: #e2e8f0; }
    .value.green { color: #34d399; }
    .value.red { color: #f87171; }
    .metrics-detail { margin-top: 0.5rem; font-size: 0.875rem; color: #94a3b8; }
    .grid-2 { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
    .detail-row { display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid #334155; }
    .detail-row:last-child { border-bottom: none; }
    .detail-label { color: #94a3b8; }
    .detail-value { font-family: monospace; color: #e2e8f0; }
    #live-updater { display: none; }
  </style>
</head>
<body>
  <header>
    <h1>Kafka Translator Dashboard</h1>
    <div id="status-badge" class="status-badge">Starting…</div>
  </header>

  <main class="grid">
    <!-- Primary Metrics -->
    <div class="card">
      <h2>Messages Transferred</h2>
      <div id="messages-transferred" class="value">0</div>
      <div class="metrics-detail" id="bytes-transferred">0 B transferred</div>
    </div>

    <div class="card">
      <h2>Errors</h2>
      <div id="errors" class="value">0</div>
    </div>

    <div class="card">
      <h2>Uptime</h2>
      <div id="uptime" class="value">0s</div>
    </div>

    <!-- Configuration & Details -->
    <div class="card">
      <h2>Source</h2>
      <div id="source-config"></div>
    </div>

    <div class="card">
      <h2>Destination</h2>
      <div id="dest-config"></div>
    </div>

    <div class="card">
      <h2>Details</h2>
      <div id="details"></div>
    </div>
  </main>

  <script>
    async function fetchStatus() {
      try {
        const res = await fetch('/status');
        if (!res.ok) throw new Error('Health check failed');
        const data = await res.json();

        // Update status badge
        const badge = document.getElementById('status-badge');
        if (data.running) {
          badge.textContent = '● Running';
          badge.className = 'status-badge running';
        } else {
          badge.textContent = '○ Stopped';
          badge.className = 'status-badge stopped';
        }

        // Update primary metrics
        document.getElementById('messages-transferred').textContent = data.messages_transferred || 0;
        const bytes = parseInt(data.bytes_transferred || 0);
        document.getElementById('bytes-transferred').textContent = 
          bytes > 1024 ? `${(bytes / 1024).toFixed(2)} KB transferred` : `${bytes} B transferred`;

        const errorsEl = document.getElementById('errors');
        errorsEl.textContent = data.errors || 0;
        errorsEl.className = 'value' + (errorsEl.textContent > 0 ? ' red' : '');

        // Update uptime
        const uptime = parseFloat(data.uptime_seconds || 0);
        document.getElementById('uptime').textContent =
          uptime > 3600 ? `${(uptime / 3600).toFixed(2)}h` :
          uptime > 60 ? `${(uptime / 60).toFixed(2)}m` : `${uptime.toFixed(1)}s`;

        // Update source config
        const sourceDiv = document.getElementById('source-config');
        sourceDiv.innerHTML = `
          <div class="detail-row"><span class="detail-label">Topic:</span><span class="detail-value">${data.source_topic || 'N/A'}</span></div>
          <div class="detail-row"><span class="detail-label">Bootstrap:</span><span class="detail-value">${data.source_bootstrap_servers || 'N/A'}</span></div>
        `;

        // Update dest config
        const destDiv = document.getElementById('dest-config');
        destDiv.innerHTML = `
          <div class="detail-row"><span class="detail-label">Topic:</span><span class="detail-value">${data.dest_topic || 'N/A'}</span></div>
          <div class="detail-row"><span class="detail-label">Bootstrap:</span><span class="detail-value">${data.dest_bootstrap_servers || 'N/A'}</span></div>
        `;

        // Update details
        const detailsDiv = document.getElementById('details');
        detailsDiv.innerHTML = `
          <div class="detail-row"><span class="detail-label">Version:</span><span class="detail-value">${data.version || 'N/A'}</span></div>
          <div class="detail-row"><span class="detail-label">Group ID:</span><span class="detail-value">${data.group_id || 'N/A'}</span></div>
          <div class="detail-row"><span class="detail-label">Last error:</span><span class="detail-value">${data.last_error || 'None'}</span></div>
        `;

      } catch (err) {
        console.error('Update failed:', err);
      }
    }

    // Poll every 1s
    fetchStatus();
    setInterval(fetchStatus, 1000);
  </script>
</body>
</html>
""".strip()


def create_dashboard_app() -> FastAPI:
    """Create dashboard sub-application."""
    app = FastAPI(title="Kafka Translator Dashboard")

    @app.get("/", response_class=HTMLResponse)
    async def root():
        """Return embedded dashboard HTML."""
        return DASHBOARD_HTML

    @app.get("/health", response_class=JSONResponse)
    async def health():
        """Health check for load balancers."""
        return {"status": "ok"}

    # Mount static files (unused but ready for future assets)
    app.mount("/static", StaticFiles(directory="."), name="static")

    return app


# Expose dashboard instance for integration
dashboard_app = create_dashboard_app()
