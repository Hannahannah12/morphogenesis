(() => {
  'use strict';

  const phaseLabel = document.getElementById('phase-label');
  const crystalLabel = document.getElementById('crystal-label');
  const sequenceButton = document.getElementById('sequence-button');
  const reloadButton = document.getElementById('reload-button');
  const fullscreenButton = document.getElementById('fullscreen-button');
  let latestSession = null;
  const FORMATION_SECONDS = 28;
  const ANALYSIS_SECONDS = 60;
  const RESONANCE_SECONDS = 65;

  const exhibitionPhase = (session) => {
    if (session?.kind !== 'analysis_rehearsal') return 'system standby';
    const startedAt = Date.parse(session.createdAt || '');
    const elapsed = Number.isFinite(startedAt) ? Math.max(0, (Date.now() - startedAt) / 1000) : 0;
    if (elapsed < FORMATION_SECONDS) return 'formation';
    if (elapsed < FORMATION_SECONDS + ANALYSIS_SECONDS) return 'analysis';
    if (elapsed < FORMATION_SECONDS + ANALYSIS_SECONDS + RESONANCE_SECONDS) return 'resonance';
    return 'diffusion';
  };

  const reloadScreens = () => {
    document.querySelectorAll('iframe').forEach((frame) => {
      const url = new URL(frame.src, window.location.origin);
      url.searchParams.set('monitorRevision', String(Date.now()));
      frame.src = url.href;
    });
  };

  const updatePhase = async () => {
    try {
      const response = await fetch('/api/agent/session', { cache: 'no-store' });
      if (!response.ok) return;
      const session = await response.json();
      latestSession = session;
      const active = session?.kind === 'analysis_rehearsal';
      phaseLabel.textContent = active ? exhibitionPhase(session) : 'system standby';
      const crystalNumber = String(session?.crystal || 'ice_crystal_01').match(/(\d+)$/)?.[1] || '01';
      crystalLabel.textContent = `crystal ${crystalNumber.padStart(2, '0')} / 05`;
      sequenceButton.textContent = active ? 'Stop test' : 'Start test';
    } catch {
      phaseLabel.textContent = 'agent offline';
    }
  };

  sequenceButton.addEventListener('click', async () => {
    sequenceButton.disabled = true;
    const action = latestSession?.kind === 'analysis_rehearsal' ? 'stop' : 'start';
    try {
      const response = await fetch('/api/agent/analysis-rehearsal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      if (!response.ok) throw new Error('sequence control failed');
      latestSession = await response.json();
      await updatePhase();
      if (action === 'start') window.setTimeout(reloadScreens, 350);
    } catch {
      phaseLabel.textContent = 'control unavailable';
    } finally {
      sequenceButton.disabled = false;
    }
  });

  reloadButton.addEventListener('click', reloadScreens);

  fullscreenButton.addEventListener('click', async () => {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
  });

  document.addEventListener('fullscreenchange', () => {
    fullscreenButton.textContent = document.fullscreenElement ? 'Exit fullscreen' : 'Fullscreen';
  });

  updatePhase();
  window.setInterval(updatePhase, 1000);
})();
