(() => {
  'use strict';

  const role = document.body.dataset.role || 'main';
  const isMain = role === 'main';
  const isMedium = role.startsWith('medium-');
  const isSmall = role.startsWith('small-');
  const mediaStage = document.getElementById('media-stage');
  const resonanceStage = document.getElementById('resonance-stage');
  const legacyResonanceStage = document.getElementById('legacy-resonance-stage');
  const legacyResonanceFrame = document.getElementById('legacy-resonance-frame');
  const realtimeDiffusionStage = document.getElementById('realtime-diffusion-stage');
  const realtimeDiffusionFrame = document.getElementById('realtime-diffusion-frame');
  const textStage = document.getElementById('text-stage');
  const videoA = document.getElementById('video-a');
  const videoB = document.getElementById('video-b');
  const blobVideo = document.getElementById('blob-video');
  const analysisCaption = document.getElementById('analysis-caption');
  const analysisLabel = document.getElementById('analysis-label');
  const analysisState = document.getElementById('analysis-state');
  const resonancePair = document.getElementById('resonance-pair');
  const patchImage = document.getElementById('patch-image');
  const resultImage = document.getElementById('result-image');
  const patchCaption = document.getElementById('patch-caption');
  const resultCaption = document.getElementById('result-caption');
  const textKicker = document.getElementById('text-kicker');
  const textTitle = document.getElementById('text-title');
  const textDetail = document.getElementById('text-detail');
  const diffusionStatus = document.getElementById('diffusion-status');
  const diffusionCountdown = document.getElementById('diffusion-countdown');
  const diffusionThought = document.getElementById('diffusion-thought');
  const diffusionPromptResult = document.getElementById('diffusion-prompt-result');
  const diffusionPromptOutput = document.getElementById('diffusion-prompt-output');
  const mainTemperature = document.getElementById('main-temperature');
  const mainTemperatureValue = document.getElementById('main-temperature-value');
  const mainTemperatureState = document.getElementById('main-temperature-state');
  const stages = [
    mediaStage, resonanceStage, legacyResonanceStage,
    realtimeDiffusionStage, textStage
  ].filter(Boolean);
  const manifestCache = new Map();
  const RESONANCE_CUT_SECONDS = 14;
  const PATCH_HOLD_SECONDS = 10;
  const FORMATION_SECONDS = 28;
  const ANALYSIS_ITEM_SECONDS = 20;
  const ANALYSIS_OUTPUTS = [
    '01_material_analysis/edge.mp4',
    '01_material_analysis/motion.mp4',
    '01_material_analysis/spacetime_row_200.mp4'
  ];
  const ANALYSIS_SECONDS = ANALYSIS_ITEM_SECONDS * ANALYSIS_OUTPUTS.length;
  const RESONANCE_SECONDS = 65;
  let currentPhase = '';
  let currentCrystal = '';
  let currentSession = null;
  let currentPatchKey = '';
  let currentDiffusionTraceKey = '';

  const renderMainTemperature = (health) => {
    if (!isMain || !mainTemperature) return;
    const sensing = health?.sensing || {};
    const rawValue = sensing.minimumTemperature;
    const value = Number(rawValue);
    const connected = Boolean(sensing.connected)
      && rawValue !== null
      && rawValue !== undefined
      && Number.isFinite(value);
    mainTemperature.classList.toggle('connected', connected);
    mainTemperature.classList.toggle('disconnected', !connected);
    mainTemperatureValue.textContent = connected ? value.toFixed(1) : '--.-';
    mainTemperatureState.textContent = connected
      ? 'Arduino / live'
      : sensing.portOpen
        ? 'Arduino / waiting'
        : 'Arduino disconnected';
  };

  const updateMainTemperature = async () => {
    if (!isMain || !mainTemperature) return;
    try {
      const response = await fetch('/api/agent/health', { cache: 'no-store' });
      if (!response.ok) throw new Error(`health ${response.status}`);
      renderMainTemperature(await response.json());
    } catch (_) {
      renderMainTemperature(null);
    }
  };

  if (isMain && mainTemperature) {
    updateMainTemperature();
    window.setInterval(updateMainTemperature, 2500);
  }

  const crystalElapsed = (session) => {
    const startedAt = Date.parse(session?.createdAt || '');
    return Number.isFinite(startedAt)
      ? Math.max(0, (Date.now() - startedAt) / 1000)
      : 0;
  };

  const phaseFromSession = (session) => {
    if (session?.kind !== 'analysis_rehearsal') return 'standby';
    const elapsed = crystalElapsed(session);
    if (elapsed < FORMATION_SECONDS) return 'formation';
    if (elapsed < FORMATION_SECONDS + ANALYSIS_SECONDS) return 'analysis';
    if (elapsed < FORMATION_SECONDS + ANALYSIS_SECONDS + RESONANCE_SECONDS) return 'resonance';
    return 'diffusion';
  };

  const rootFor = (crystal) => `/05_shared_data/exhibition/${crystal}`;
  const urlsFor = (crystal) => {
    const root = rootFor(crystal);
    return {
      attention: `${root}/02_structural_resonance/attention_map.mp4`,
      blob: `${root}/02_structural_resonance/blob_track.mp4`,
      manifest: `${root}/02_structural_resonance/manifest.json`,
      diffusion: `${root}/03_diffusion_imagination/diffusion_capture.mp4`
    };
  };

  const showStages = (...visibleStages) => {
    stages.forEach((candidate) => (
      candidate.classList.toggle('active', visibleStages.includes(candidate))
    ));
  };

  const showStage = (stage) => showStages(stage);

  const stopVideo = (video, release = false) => {
    video.pause();
    video.playbackRate = 1;
    if (release && video.getAttribute('src')) {
      video.removeAttribute('src');
      delete video.dataset.morphogenesisSourceUrl;
      video.load();
    }
  };

  const stopUnused = (...keep) => {
    [videoA, videoB, blobVideo].forEach((video) => {
      if (!keep.includes(video)) stopVideo(video, true);
    });
  };

  const unloadLegacyResonance = () => {
    if (!legacyResonanceFrame || !legacyResonanceFrame.dataset.loaded) return;
    legacyResonanceFrame.src = 'about:blank';
    delete legacyResonanceFrame.dataset.loaded;
  };

  const unloadRealtimeDiffusion = () => {
    if (!realtimeDiffusionFrame || !realtimeDiffusionFrame.dataset.loaded) return;
    realtimeDiffusionFrame.src = 'about:blank';
    delete realtimeDiffusionFrame.dataset.loaded;
  };

  const renderRealtimeDiffusion = () => {
    stopUnused();
    showStage(realtimeDiffusionStage);
    if (realtimeDiffusionFrame.dataset.loaded) return;
    const isMonitor = new URLSearchParams(window.location.search).get('monitor') === '1';
    const url = new URL(realtimeDiffusionFrame.dataset.src, window.location.origin);
    if (isMain) {
      url.searchParams.set('exhibitionEmbed', 'main');
      // Every main-display instance competes for one browser-local lease.
      // The winner runs StreamDiffusion; other main/monitor tabs mirror it.
      url.searchParams.set('mirror', 'auto');
    }
    url.searchParams.set('displayRole', role);
    realtimeDiffusionFrame.src = url.href;
    realtimeDiffusionFrame.dataset.loaded = 'true';
  };

  const syncVideo = async (video, session, url, timeline = 'normalized') => {
    if (!url) return;
    video.loop = true;
    await window.syncMorphogenesisVideo?.(video, session, url, { timeline });
  };

  const phaseElapsed = (session) => {
    const elapsed = crystalElapsed(session);
    const phase = phaseFromSession(session);
    if (phase === 'analysis') return elapsed - FORMATION_SECONDS;
    if (phase === 'resonance') return elapsed - FORMATION_SECONDS - ANALYSIS_SECONDS;
    if (phase === 'diffusion') {
      return elapsed - FORMATION_SECONDS - ANALYSIS_SECONDS - RESONANCE_SECONDS;
    }
    return elapsed;
  };

  const formationSession = (session) => {
    if (session.phase !== 'analysis_countdown') return session;
    return {
      ...session,
      playback: {
        ...session.playback,
        startedAtEpochMs: session.presentation?.stageStartedAtEpochMs || Date.now(),
        offsetSeconds: 0
      }
    };
  };

  const renderStandby = () => {
    stopUnused();
    showStage(textStage);
    textKicker.textContent = 'morphogenesis / exhibition mode';
    textTitle.textContent = 'SYSTEM STANDBY';
    textDetail.textContent = 'waiting for Formation → Analysis → Resonance → Diffusion';
  };

  const renderFormation = async (session) => {
    stopUnused(videoA);
    showStage(mediaStage);
    mediaStage.classList.remove('show-secondary');
    analysisCaption.hidden = true;
    // All four Exhibition screens share the same normalized clock. This also
    // avoids one screen independently wrapping to frame zero when it opens near
    // the end of a source clip.
    await syncVideo(videoA, formationSession(session), session.playback?.url, 'normalized');
  };

  const renderAnalysisVisual = async (session) => {
    stopUnused(videoA);
    showStage(mediaStage);
    mediaStage.classList.remove('show-secondary');
    const outputIndex = Math.min(
      ANALYSIS_OUTPUTS.length - 1,
      Math.floor(phaseElapsed(session) / ANALYSIS_ITEM_SECONDS)
    );
    const url = `${rootFor(session.crystal)}/${ANALYSIS_OUTPUTS[outputIndex]}`;
    analysisCaption.hidden = true;
    await syncVideo(videoA, session, url, 'normalized');
  };

  const renderAnalysis = (session) => renderAnalysisVisual(session);

  const loadManifest = async (crystal) => {
    if (manifestCache.has(crystal)) return manifestCache.get(crystal);
    const manifestUrl = urlsFor(crystal).manifest;
    const response = await fetch(manifestUrl, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Manifest HTTP ${response.status}`);
    const data = await response.json();
    const base = new URL('.', new URL(manifestUrl, window.location.origin)).href;
    const resolveUrl = (value) => value ? new URL(value, base).href : '';
    const normalized = {
      patches: (data.patches || []).map(resolveUrl),
      sets: (data.resonanceSets || []).map((set) => ({
        patchIndex: Number(set.patchIndex || 0),
        patch: resolveUrl(set.patch || data.patches?.[Number(set.patchIndex || 0)]),
        branch: set.branch || 'structure',
        results: (set.results || []).map((result) => ({
          url: resolveUrl(typeof result === 'string' ? result : result.url),
          category: typeof result === 'string' ? '' : result.category || '',
          provider: typeof result === 'string' ? '' : result.provider || ''
        })).filter((result) => result.url)
      }))
    };
    manifestCache.set(crystal, normalized);
    return normalized;
  };

  const renderResonanceMain = async (session) => {
    const urls = urlsFor(session.crystal);
    stopUnused(videoA, videoB);
    showStage(mediaStage);
    analysisCaption.hidden = true;
    await Promise.all([
      syncVideo(videoA, session, urls.attention),
      syncVideo(videoB, session, urls.blob)
    ]);
  };

  const renderResonanceSmall = async (session) => {
    const urls = urlsFor(session.crystal);
    stopUnused(videoA);
    showStage(mediaStage);
    mediaStage.classList.remove('show-secondary');
    analysisCaption.hidden = true;
    await syncVideo(videoA, session, urls.attention);
  };

  const updatePatchPair = async (session) => {
    if (!isMedium || legacyResonanceFrame || phaseFromSession(session) !== 'resonance') return;
    const manifest = await loadManifest(session.crystal);
    if (!manifest.sets.length) return;
    const sequenceIndex = Math.floor(phaseElapsed(session) / PATCH_HOLD_SECONDS);
    const set = manifest.sets[sequenceIndex % manifest.sets.length];
    const results = set.results || [];
    const result = results.length ? results[sequenceIndex % results.length] : null;
    const patchUrl = set.patch || manifest.patches[set.patchIndex];
    const key = `${session.crystal}:${sequenceIndex}:${patchUrl}:${result?.url || ''}`;
    if (currentPatchKey === key) return;
    currentPatchKey = key;
    resonancePair.classList.add('changing');
    window.setTimeout(() => {
      patchImage.src = patchUrl || '';
      resultImage.src = result?.url || patchUrl || '';
      patchCaption.textContent = `detected patch / ${String(set.patchIndex + 1).padStart(2, '0')}`;
      resultCaption.textContent = [result?.category, result?.provider, set.branch]
        .filter(Boolean).join(' / ') || 'structural resonance';
      resonancePair.classList.remove('changing');
    }, 420);
  };

  const renderResonanceMedium = async (session) => {
    stopUnused();
    showStage(legacyResonanceStage);
    if (!legacyResonanceFrame.dataset.loaded) {
      const url = new URL(legacyResonanceFrame.dataset.src, window.location.origin);
      url.searchParams.set('crystal', session.crystal || 'ice_crystal_01');
      url.searchParams.set('monitorRevision', String(session.id || Date.now()));
      legacyResonanceFrame.src = url.href;
      legacyResonanceFrame.dataset.loaded = 'true';
    }
  };

  const renderResonance = (session) => {
    if (isMain) return renderResonanceMain(session);
    if (isSmall) return renderResonanceSmall(session);
    return renderResonanceMedium(session);
  };

  const renderDiffusionVisual = async (session) => {
    stopUnused(videoA);
    showStage(mediaStage);
    mediaStage.classList.remove('show-secondary');
    analysisCaption.hidden = true;
    // Playback-only in Exhibition Mode: the main and both medium screens reuse the
    // same saved generation. No StreamDiffusion socket or OpenAI request is
    // created by this page.
    // Diffusion and the small-screen source share one real-seconds clock at
    // 1x speed. This avoids stretching the low-frame-rate recorded result.
    await syncVideo(videoA, session, urlsFor(session.crystal).diffusion, 'seconds');
  };

  const renderDiffusionSource = async (session) => {
    stopUnused(videoA);
    showStage(mediaStage);
    mediaStage.classList.remove('show-secondary');
    analysisCaption.hidden = true;
    await syncVideo(videoA, session, session.playback?.url, 'seconds');
  };

  const diffusionTrace = [
    {
      status: 'OpenAI / examining formation structure',
      thought: 'Magnifying the emerged structure…',
      prompt: ''
    },
    {
      status: 'OpenAI / reading crystallisation',
      thought: 'I am observing water crystallising into an organised ice structure.\n\nReading branching direction, growth front and local density before extending the image.',
      prompt: ''
    },
    {
      status: 'OpenAI / unfolding association',
      thought: 'The structure is stable enough to support a wider association.\n\nSearching for the same rhythm rather than the same material: translucent membranes, dendritic channels and pale mineral depth.',
      prompt: 'Preserve the branching topology, growth front and local density; unfold it as translucent ice membranes, fine dendritic filaments and pale silver-blue depth.'
    },
    {
      status: 'OpenAI / imagination complete',
      thought: 'A shared visual association has entered the display system. The generated result is reused by the main and medium displays while the small displays return to the crystallisation source.',
      prompt: 'One generated visual / shared main and medium playback / source retained on small displays.'
    }
  ];

  const updateDiffusionTrace = (session) => {
    if (!isMain || !diffusionStatus) return;
    const elapsed = phaseElapsed(session);
    const index = Math.min(diffusionTrace.length - 1, Math.floor(elapsed / 12));
    const trace = diffusionTrace[index];
    const key = `${session.crystal}:${index}`;
    diffusionStatus.textContent = trace.status;
    diffusionCountdown.textContent = index < diffusionTrace.length - 1
      ? `next / ${Math.max(0, 12 - Math.floor(elapsed % 12))}s`
      : 'result / shared';
    if (key === currentDiffusionTraceKey) return;
    currentDiffusionTraceKey = key;
    diffusionThought.textContent = trace.thought;
    diffusionThought.classList.remove('typing');
    window.requestAnimationFrame(() => diffusionThought.classList.add('typing'));
    diffusionPromptResult.hidden = !trace.prompt;
    diffusionPromptOutput.textContent = trace.prompt;
  };

  const renderDiffusionMain = async (session) => {
    stopUnused(videoA);
    showStages(mediaStage, textStage);
    mediaStage.classList.remove('show-secondary');
    analysisCaption.hidden = true;
    await syncVideo(videoA, session, urlsFor(session.crystal).diffusion, 'seconds');
    updateDiffusionTrace(session);
  };

  const renderDiffusion = (session) => (
    isSmall ? renderDiffusionSource(session) : renderRealtimeDiffusion(session)
  );

  const render = async (session) => {
    currentSession = session;
    const phase = phaseFromSession(session);
    const phaseChanged = phase !== currentPhase || session?.crystal !== currentCrystal;
    currentPhase = phase;
    currentCrystal = session?.crystal || '';
    document.body.dataset.phase = phase;
    document.body.dataset.crystal = currentCrystal;
    if (phase !== 'resonance') unloadLegacyResonance();
    if (phase !== 'diffusion') unloadRealtimeDiffusion();
    if (phaseChanged) {
      currentPatchKey = '';
      currentDiffusionTraceKey = '';
    }
    try {
      if (phase === 'formation') await renderFormation(session);
      else if (phase === 'analysis') await renderAnalysis(session);
      else if (phase === 'resonance') await renderResonance(session);
      else if (phase === 'diffusion') await renderDiffusion(session);
      else renderStandby();
    } catch (error) {
      showStage(textStage);
      textKicker.textContent = `exhibition / ${phase}`;
      textTitle.textContent = 'MEDIA RECONNECTING';
      textDetail.textContent = error.message || 'waiting for shared media';
    }
  };

  const updateClockedVisuals = () => {
    if (!currentSession) return;
    if (currentPhase === 'resonance' && isMain) {
      const index = Math.floor(phaseElapsed(currentSession) / RESONANCE_CUT_SECONDS) % 2;
      mediaStage.classList.toggle('show-secondary', index === 1);
    }
  };

  const heartbeat = () => {
    fetch('/api/agent/client', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        page: `exhibition_${role.replace('-', '_')}`,
        active: true,
        visible: document.visibilityState === 'visible',
        title: document.title,
        url: window.location.href,
        details: {
          mode: 'exhibition',
          role,
          phase: currentPhase,
          crystal: currentCrystal,
          diffusionMode: 'shared-recorded-result'
        }
      }),
      keepalive: true
    }).catch(() => {});
  };

  window.addEventListener('morphogenesis-session', (event) => render(event.detail));
  window.addEventListener('morphogenesis-session-tick', (event) => render(event.detail));
  window.addEventListener('pagehide', () => {
    [videoA, videoB, blobVideo].forEach((video) => stopVideo(video, true));
  });
  document.addEventListener('visibilitychange', heartbeat);
  window.setInterval(updateClockedVisuals, 500);
  window.setInterval(heartbeat, 3000);
  renderStandby();
  heartbeat();
  if (window.morphogenesisSession) render(window.morphogenesisSession);
})();
