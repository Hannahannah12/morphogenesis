(() => {
  'use strict';

  const body = document.body;
  const scenes = [...document.querySelectorAll('.display-scene')];
  const status = document.getElementById('scene-status');
  const sharedCountdown = document.getElementById('shared-countdown');
  const sharedCountdownValue = document.getElementById('shared-countdown-value');
  const secondScreen = body.dataset.page === 'medium_display_2';
  const rotationSeconds = null;
  let activeIndex = -1;

  const prewarmResonance = () => {
    if (secondScreen) return;
    const frame = scenes[0]?.querySelector('iframe');
    if (frame?.dataset.src && frame.getAttribute('src') === 'about:blank') {
      frame.src = frame.dataset.src;
    }
  };

  const sleepScenes = () => {
    activeIndex = -1;
    body.dataset.activeScene = '';
    scenes.forEach((scene) => {
      scene.classList.remove('is-active');
      scene.setAttribute('aria-hidden', 'true');
      const frame = scene.querySelector('iframe');
      if (frame && frame.getAttribute('src') !== 'about:blank') frame.src = 'about:blank';
    });
  };

  const renderSharedCountdown = (session) => {
    const rehearsal = session?.kind === 'analysis_rehearsal';
    const countdown = rehearsal && session?.phase === 'analysis_countdown';
    const materialComplete = session?.jobs?.material?.state === 'complete';
    // The medium screens have one shared hand-off only: before Material is
    // complete they show WAITING_, after it completes they reveal their fixed
    // output. Future Agent stage names must not create a blank gap here.
    const waiting = rehearsal && !countdown && !materialComplete;
    const active = countdown || waiting;
    sharedCountdown.hidden = !active;
    if (!active) {
      sharedCountdown.classList.remove('is-countdown', 'is-waiting');
      return;
    }
    sharedCountdown.classList.toggle('is-countdown', countdown);
    sharedCountdown.classList.toggle('is-waiting', waiting);
    const label = sharedCountdown.querySelector('p');
    if (waiting) {
      label.textContent = '';
      sharedCountdownValue.textContent = 'WAITING';
      return;
    }
    label.textContent = 'ICE CRYSTALLISATION BEGINS IN';
    const presentation = session.presentation || {};
    const startedAt = Number(presentation.stageStartedAtEpochMs || Date.now());
    const duration = Math.max(0, Number(presentation.stageDurationSeconds || 0));
    const elapsed = Math.max(0, (Date.now() - startedAt) / 1000);
    const remaining = Math.max(0, Math.ceil(duration - elapsed));
    sharedCountdownValue.textContent = `00:${String(remaining).padStart(2, '0')}`;
  };

  const applyRehearsalScene = (session) => {
    if (session?.kind !== 'analysis_rehearsal') {
      sleepScenes();
      sharedCountdown.hidden = false;
      sharedCountdown.classList.remove('is-countdown');
      sharedCountdown.classList.add('is-waiting');
      sharedCountdown.querySelector('p').textContent = '';
      sharedCountdownValue.textContent = 'SYSTEM STANDBY';
      return;
    }
    // Load Medium 1's Resonance page behind the countdown/material overlay.
    // It stays invisible, but its manifest and first video frame are ready by
    // the time Material completes.
    prewarmResonance();
    renderSharedCountdown(session);
    const materialComplete = session?.jobs?.material?.state === 'complete';
    if (materialComplete) selectScene(secondScreen ? 1 : 0);
    else {
      activeIndex = -1;
      scenes.forEach((scene) => {
        scene.classList.remove('is-active');
        scene.setAttribute('aria-hidden', 'true');
        const frame = scene.querySelector('iframe');
        if (frame && frame.getAttribute('src') !== 'about:blank'
          && (secondScreen || scene !== scenes[0])) frame.src = 'about:blank';
      });
    }
  };

  const selectScene = (index) => {
    if (index === activeIndex || !scenes.length) return;
    activeIndex = index;
    scenes.forEach((scene, sceneIndex) => {
      const active = sceneIndex === activeIndex;
      scene.classList.toggle('is-active', active);
      scene.setAttribute('aria-hidden', active ? 'false' : 'true');
      const frame = scene.querySelector('iframe');
      if (active && frame?.dataset.src && frame.getAttribute('src') === 'about:blank') {
        frame.src = frame.dataset.src;
      } else if (!active && frame && frame.getAttribute('src') !== 'about:blank') {
        // Keep only the visible direction alive. This prevents two medium
        // screens from decoding Resonance and running Diffusion at the same
        // time, which previously stalled the Live screen.
        frame.src = 'about:blank';
      }
    });
    const label = scenes[activeIndex]?.getAttribute('aria-label') || 'Display';
    body.dataset.activeScene = scenes[activeIndex]?.dataset.scene || '';
    status.textContent = `${label} is now playing`;
  };

  const syncToClock = () => {
    if (!scenes.length) return;
    if (activeIndex < 0) selectScene(0);
  };

  const pageDetails = () => ({
    scene: scenes[activeIndex]?.dataset.scene || null,
    rotationSeconds,
    synchronizedToClock: false,
    phaseDriven: true,
    displayRole: secondScreen ? 'fixed-diffusion' : 'fixed-resonance',
    screensIntended: 2
  });

  const heartbeatPayload = (active = true) => ({
    page: body.dataset.page,
    active,
    visible: document.visibilityState === 'visible',
    title: document.title,
    url: window.location.href,
    details: pageDetails()
  });

  const heartbeat = () => {
    fetch('/api/agent/client', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(heartbeatPayload()),
      keepalive: true
    }).catch(() => {});
  };

  document.addEventListener('visibilitychange', heartbeat);
  window.addEventListener('pagehide', () => {
    navigator.sendBeacon?.('/api/agent/client', JSON.stringify(heartbeatPayload(false)));
  });

  sleepScenes();
  sharedCountdown.hidden = false;
  sharedCountdown.classList.add('is-waiting');
  sharedCountdown.querySelector('p').textContent = '';
  sharedCountdownValue.textContent = 'SYSTEM STANDBY';
  if (window.morphogenesisSession) applyRehearsalScene(window.morphogenesisSession);
  window.addEventListener('morphogenesis-session', (event) => applyRehearsalScene(event.detail));
  window.addEventListener('morphogenesis-session-tick', (event) => applyRehearsalScene(event.detail));
  heartbeat();
  window.setInterval(heartbeat, 3000);
})();
