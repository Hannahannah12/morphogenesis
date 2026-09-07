(() => {
  'use strict';

  const script = document.currentScript;
  const page = script?.dataset.page;
  if (!page) return;

  const details = () => {
    if (typeof window.getMorphogenesisPageDetails === 'function') {
      return window.getMorphogenesisPageDetails();
    }
    if (page === 'live') {
      const camera = document.getElementById('camera-video');
      const sensor = document.getElementById('sensor-state')?.textContent || '';
      return {
        source: document.getElementById('source-label')?.textContent || '',
        sensor,
        arduinoConnected: sensor === 'Arduino sensor / live',
        cameraActive: Boolean(
          camera?.srcObject
          || (
            document.getElementById('observation')?.classList.contains('is-live')
            && camera?.videoWidth
          )
        ),
        cameraError: document.getElementById('observation')?.dataset.cameraError || '',
        objectTemperature: document.getElementById('temperature')?.textContent || '',
        ambientTemperature: document.getElementById('ambient-temperature')?.textContent || ''
      };
    }
    if (page === 'diffusion') {
      const runtime = document.getElementById('runtime-label')?.textContent || '';
      const fpsText = document.getElementById('fps-label')?.textContent || '';
      const fps = Number.parseFloat(fpsText);
      return {
        workerConnected: runtime === 'GPU service / ready',
        workerStatus: runtime.replace('GPU service / ', '') || 'unknown',
        source: document.getElementById('source-label')?.textContent || '',
        cameraActive: Boolean(document.getElementById('camera-video')?.srcObject),
        streaming: document.getElementById('stream-button')?.textContent === 'Stop diffusion',
        fps: Number.isFinite(fps) ? fps : null
      };
    }
    return {};
  };

  const payload = (active = true) => ({
    page,
    active,
    visible: document.visibilityState === 'visible',
    title: document.title,
    url: window.location.href,
    details: details()
  });

  const coolingOverlay = document.createElement('div');
  coolingOverlay.id = 'morphogenesis-cooling-overlay';
  coolingOverlay.setAttribute('role', 'status');
  coolingOverlay.style.cssText = [
    'position:fixed', 'z-index:99999', 'right:12px', 'bottom:12px',
    'display:none', 'padding:6px 9px',
    'border:1px solid rgba(143,220,255,.42)', 'background:rgba(5,8,8,.88)',
    'color:#dff6ff', 'font:8px/1.2 Helvetica,Arial,sans-serif',
    'letter-spacing:.1em', 'text-transform:uppercase',
    'max-width:220px',
    'backdrop-filter:blur(10px)', 'pointer-events:none'
  ].join(';');
  document.body.appendChild(coolingOverlay);

  const renderCooling = async () => {
    try {
      const response = await fetch('/api/agent/status', { cache: 'no-store' });
      if (!response.ok) return;
      const status = await response.json();
      const cooling = status.manualCooling || {};
      const recording = cooling.recording || {};
      const visible = cooling.active || !['idle', 'complete', 'showcase'].includes(recording.state);
      if (!visible) {
        coolingOverlay.style.display = 'none';
        return;
      }
      const started = Date.parse(cooling.startedAt || recording.startedAt || '');
      const elapsed = Number.isFinite(started) ? Math.max(0, Math.floor((Date.now() - started) / 1000)) : 0;
      const minutes = String(Math.floor(elapsed / 60)).padStart(2, '0');
      const seconds = String(elapsed % 60).padStart(2, '0');
      const label = recording.state === 'formation_detected'
        ? 'Formation detected · final 2 seconds'
        : recording.state === 'processing'
          ? 'Turn off Peltier · processing new crystal'
          : 'Cooling + recording';
      coolingOverlay.textContent = `${label} · ${minutes}:${seconds}`;
      coolingOverlay.style.display = 'block';
    } catch (_) {
      coolingOverlay.style.display = 'none';
    }
  };

  const heartbeat = () => {
    fetch('/api/agent/client', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload()),
      keepalive: true
    }).catch(() => {});
  };

  document.addEventListener('visibilitychange', heartbeat);
  window.addEventListener('pagehide', () => {
    navigator.sendBeacon?.('/api/agent/client', JSON.stringify(payload(false)));
  });
  heartbeat();
  renderCooling();
  window.setInterval(heartbeat, 3000);
  window.setInterval(renderCooling, 1000);
})();
