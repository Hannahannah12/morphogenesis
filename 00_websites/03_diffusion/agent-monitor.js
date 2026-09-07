(() => {
  'use strict';

  const details = () => {
    const runtimeDetails = window.getMorphogenesisPageDetails?.();
    if (runtimeDetails) return runtimeDetails;
    const runtime = document.getElementById('runtime-label')?.textContent || '';
    const runtimeReady = document.getElementById('runtime-dot')?.classList.contains('ready') || false;
    const fpsText = document.getElementById('fps-label')?.textContent || '';
    const fps = Number.parseFloat(fpsText);
    return {
      workerConnected: runtimeReady,
      workerStatus: runtime.replace('GPU service / ', '') || 'unknown',
      source: document.getElementById('source-label')?.textContent || '',
      cameraActive: Boolean(document.getElementById('camera-video')?.srcObject),
      streaming: document.getElementById('stream-button')?.textContent === 'Stop',
      hasGeneratedFrame: document.getElementById('generated-frame')?.dataset.generated === 'true',
      fps: Number.isFinite(fps) ? fps : null,
      creativeAI: document.getElementById('ai-status')?.classList.contains('ready') || false,
      imaginationEnabled: document.getElementById('ai-toggle')?.getAttribute('aria-pressed') === 'true',
      sessionId: window.morphogenesisSession?.id || '',
      sessionRevision: window.morphogenesisSession?.playback?.revision || 0
    };
  };

  const payload = (active = true) => ({
    page: 'diffusion',
    active,
    visible: document.visibilityState === 'visible',
    title: document.title,
    url: window.location.href,
    details: details()
  });

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
  window.setInterval(heartbeat, 3000);
})();
