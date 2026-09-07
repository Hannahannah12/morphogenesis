(() => {
  'use strict';

  const page = document.currentScript?.dataset.page || '';
  const jobNames = {
    material: 'material',
    structural: 'structural',
    diffusion: 'diffusion'
  };
  let currentSession = window.morphogenesisSession || null;

  const overlay = document.createElement('section');
  overlay.className = 'morphogenesis-session-state';
  overlay.hidden = true;
  overlay.setAttribute('role', 'status');
  overlay.setAttribute('aria-live', 'polite');
  overlay.innerHTML = `
    <div class="morphogenesis-session-copy">
      <p class="morphogenesis-session-kicker"></p>
      <h2></h2>
      <p class="morphogenesis-session-detail"></p>
    </div>
  `;
  document.body.append(overlay);

  const kicker = overlay.querySelector('.morphogenesis-session-kicker');
  const title = overlay.querySelector('h2');
  const detail = overlay.querySelector('.morphogenesis-session-detail');

  const diffusionConnected = () => (
    (
      document.getElementById('runtime-dot')?.classList.contains('ready')
      && document.getElementById('stream-button')?.textContent === 'Stop diffusion'
    )
    || document.body.dataset.diffusionFallback === 'true'
  );

  const outputReady = (session) => {
    if (page === 'live') return true;
    if (page === 'diffusion' && diffusionConnected()) return true;
    return session?.jobs?.[jobNames[page]]?.state === 'complete';
  };

  const reset = () => {
    overlay.hidden = true;
    overlay.className = 'morphogenesis-session-state';
    document.body.classList.remove('morphogenesis-entry', 'morphogenesis-processing');
  };

  const apply = (session) => {
    currentSession = session;
    if (!session?.id) {
      reset();
      return;
    }
    if (session.kind === 'analysis_rehearsal') {
      reset();
      return;
    }

    const phase = String(session.phase || 'starting');
    // Keep all three directions on the shared camera timeline until the
    // retained clip has actually finished writing. The pipeline stays in
    // formation_detected while that trim/write operation is in progress.
    const entry = ['starting', 'observing', 'formation_detected'].includes(phase);
    const waiting = !entry && !outputReady(session);
    if (!entry && !waiting) {
      reset();
      return;
    }

    overlay.hidden = false;
    overlay.className = `morphogenesis-session-state ${entry ? 'entry' : 'processing'}`;
    document.body.classList.toggle('morphogenesis-entry', entry);
    document.body.classList.toggle('morphogenesis-processing', waiting);

    if (entry) {
      const inputLabel = session.kind === 'recorded_rehearsal'
        ? 'Simulated input'
        : 'Live input';
      kicker.innerHTML = `<span class="morphogenesis-session-pulse"></span>${inputLabel}`;
      title.textContent = phase === 'formation_detected'
        ? 'Formation detected. Securing the capture.'
        : 'Awaiting formation';
      detail.textContent = phase === 'formation_detected'
        ? `${session.crystal?.replaceAll('_', ' ') || 'current input'} / shared live relay continues`
        : `${session.crystal?.replaceAll('_', ' ') || 'current input'} / shared entry`;
      return;
    }

    const job = session?.jobs?.[jobNames[page]];
    kicker.innerHTML = '<span class="morphogenesis-session-pulse"></span>Formation captured';
    title.innerHTML = 'A FORM HAS EMERGED.<br>ITS INTERPRETATIONS ARE STILL FORMING.';
    detail.textContent = job?.message || `System phase / ${phase.replaceAll('_', ' ')}`;
  };

  window.addEventListener('morphogenesis-session', (event) => apply(event.detail));
  window.addEventListener('morphogenesis-session-tick', (event) => apply(event.detail));
  window.setInterval(() => {
    if (currentSession && page === 'diffusion') apply(currentSession);
  }, 500);
  if (currentSession) apply(currentSession);
})();
