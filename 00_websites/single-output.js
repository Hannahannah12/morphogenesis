(() => {
  'use strict';

  const body = document.body;
  const video = document.getElementById('single-output-video');
  const page = body.dataset.page || '';
  const section = body.dataset.section || '';
  const file = body.dataset.file || '';
  const jobName = body.dataset.job || '';
  const outputIndex = Number.parseInt(body.dataset.outputIndex || '', 10);
  const defaultCrystal = body.dataset.defaultCrystal || 'ice_crystal_01';
  const outputName = body.dataset.outputName || file;
  const timeline = body.dataset.timeline === 'seconds' ? 'seconds' : 'normalized';
  const outputCatalog = {
    attention: {
      key: 'attention', label: 'Attention Map', look: 'attention',
      section: '02_structural_resonance', file: 'attention_map.mp4',
      job: 'structural', outputIndex: 1
    },
    edge: {
      key: 'edge', label: 'Edge', look: 'edge',
      section: '01_material_analysis', file: 'edge_numbers.mp4',
      job: 'material', outputIndex: null
    },
    motion: {
      key: 'motion', label: 'Motion', look: 'motion',
      section: '01_material_analysis', file: 'motion.mp4',
      job: 'material', outputIndex: 3
    },
    threshold: {
      key: 'threshold', label: 'Threshold', look: 'threshold',
      section: '01_material_analysis', file: 'threshold.mp4',
      job: 'material', outputIndex: 1
    },
    blob: {
      key: 'blob', label: 'Blob Track', look: 'blob',
      section: '02_structural_resonance', file: 'blob_track.mp4',
      job: 'structural', outputIndex: null
    },
    spacetime: {
      key: 'spacetime', label: 'Spacetime', look: 'attention',
      section: '01_material_analysis', file: 'spacetime.mp4',
      job: 'material', outputIndex: 2
    },
    spacetimeRow200: {
      key: 'spacetimeRow200', label: 'Spacetime / Row 200', look: 'spacetime',
      section: '01_material_analysis', file: 'spacetime_row_200.mp4',
      job: 'material', outputIndex: null
    }
  };
  const stabilizedMaterialRoots = {
    ice_crystal_01: '/09_experiments/05_stabilization/ice_crystal_01_fixed_lock',
    ice_crystal_02: '/09_experiments/05_stabilization/ice_crystal_02_plate_lock_v3',
    ice_crystal_03: '/09_experiments/05_stabilization/ice_crystal_03_global_lock',
    ice_crystal_04: '/09_experiments/05_stabilization/ice_crystal_04_fixed_lock',
    ice_crystal_05: '/09_experiments/05_stabilization/ice_crystal_05_global_lock',
    ice_crystal_06: '/09_experiments/05_stabilization/ice_crystal_06_global_lock_v2'
  };
  const playlist = String(body.dataset.playlist || '')
    .split(',')
    .map((key) => outputCatalog[key.trim()])
    .filter(Boolean);
  const rotationSeconds = Math.max(3, Number(body.dataset.rotationSeconds) || 10);
  const fixedOutput = {
    key: body.dataset.look || file,
    label: outputName,
    look: body.dataset.look || '',
    section,
    file,
    job: jobName,
    outputIndex
  };

  let crystal = defaultCrystal;
  let sourceUrl = '';
  let sourceError = '';
  let lastMediaEvent = 'initialising';
  let lastMediaEventAt = Date.now();
  let mediaRetryCount = 0;
  let playlistIndex = 0;
  let activeOutput = playlist[playlistIndex] || fixedOutput;
  let activeSession = null;
  let analysisPlaybackActive = false;
  const ANALYSIS_COMPLETE_HOLD_SECONDS = 4;
  const ANALYSIS_SHARED_PLAYBACK_SECONDS = 24;

  const statusOverlay = document.createElement('section');
  statusOverlay.className = 'single-output-status';
  statusOverlay.innerHTML = '<p></p><strong></strong>';
  document.body.append(statusOverlay);
  const statusKicker = statusOverlay.querySelector('p');
  const statusTitle = statusOverlay.querySelector('strong');

  const setWaitingState = (waiting, kicker = '', title = '') => {
    document.body.classList.toggle('single-output-waiting', waiting);
    statusOverlay.classList.toggle('visible', waiting || Boolean(title));
    statusKicker.textContent = kicker;
    statusTitle.textContent = title;
    if (waiting) video.pause();
  };

  const analysisCountdownRemaining = (session) => {
    const presentation = session?.presentation || {};
    const startedAt = Number(presentation.stageStartedAtEpochMs || Date.now());
    const duration = Math.max(0, Number(presentation.stageDurationSeconds || 0));
    const elapsed = Math.max(0, (Date.now() - startedAt) / 1000);
    return Math.max(0, Math.ceil(duration - elapsed));
  };

  video.defaultMuted = true;
  video.muted = true;
  video.autoplay = true;
  video.playsInline = true;

  const edgeNumbers = document.getElementById('single-edge-numbers');
  const edgeContext = edgeNumbers?.getContext('2d');
  const edgeSampleCanvas = edgeNumbers ? document.createElement('canvas') : null;
  const edgeSampleContext = edgeSampleCanvas?.getContext('2d', { willReadFrequently: true });
  let lastEdgeDraw = 0;

  const normalizeCrystal = (value) => {
    const match = String(value || '').match(/^ice_crystal_(\d+)$/i);
    if (!match) return null;
    return `ice_crystal_${String(Number(match[1])).padStart(2, '0')}`;
  };

  const stabilizedMaterialUrl = (value, selected = activeOutput) => {
    const root = stabilizedMaterialRoots[value];
    if (!root || !['edge', 'motion'].includes(selected.key)) return '';
    return `${root}/01_material_analysis/${selected.file}`;
  };

  const defaultUrl = (value, selected = activeOutput) => (
    stabilizedMaterialUrl(value, selected)
    || `/05_shared_data/exhibition/${value}/${selected.section}/${selected.file}`
  );

  const sessionUrl = (session, value, selected = activeOutput) => {
    const stabilized = stabilizedMaterialUrl(value, selected);
    if (stabilized) return stabilized;
    if (selected.job === 'structural' && selected.key === 'attention') {
      const attention = session?.jobs?.structural?.videoUrls?.attentionMap
        || session?.jobs?.structural?.outputUrls?.[selected.outputIndex];
      if (attention) return attention;
    }
    if (selected.job === 'structural' && selected.key === 'blob') {
      const blob = session?.jobs?.structural?.videoUrls?.blobTrack;
      if (blob) return blob;
    }
    if (selected.job === 'material' && Number.isInteger(selected.outputIndex)) {
      const output = session?.jobs?.material?.outputUrls?.[selected.outputIndex];
      if (output) return output;
    }
    return defaultUrl(value, selected);
  };

  const analysisPreloadPool = new Map();
  const warmAnalysisOutputs = (session, value) => {
    ['edge', 'motion', 'threshold', 'attention', 'blob'].forEach((key) => {
      const selected = outputCatalog[key];
      const url = sessionUrl(session, value, selected);
      const absolute = new URL(url, window.location.origin).href;
      if (analysisPreloadPool.has(absolute)) return;
      const preloadVideo = document.createElement('video');
      preloadVideo.preload = 'auto';
      preloadVideo.muted = true;
      preloadVideo.playsInline = true;
      preloadVideo.src = absolute;
      preloadVideo.load();
      analysisPreloadPool.set(absolute, preloadVideo);
    });
  };

  const bindStandalone = async (url) => {
    const absolute = new URL(url, window.location.origin).href;
    if (video.dataset.morphogenesisSourceUrl !== absolute) {
      video.pause();
      video.src = absolute;
      video.dataset.morphogenesisSourceUrl = absolute;
      video.load();
      mediaRetryCount = 0;
    }
    video.loop = true;
    await video.play().catch((error) => {
      sourceError = `Playback waiting: ${error.name || 'browser policy'}`;
    });
  };

  const resizeEdgeNumbers = () => {
    if (!edgeNumbers || !edgeContext) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    edgeNumbers.width = Math.round(window.innerWidth * ratio);
    edgeNumbers.height = Math.round(window.innerHeight * ratio);
    edgeNumbers.style.width = `${window.innerWidth}px`;
    edgeNumbers.style.height = `${window.innerHeight}px`;
    edgeContext.setTransform(ratio, 0, 0, ratio, 0, 0);
  };

  const drawEdgeNumbers = (timestamp = 0) => {
    if (!edgeNumbers || !edgeContext || !edgeSampleCanvas || !edgeSampleContext) return;
    window.requestAnimationFrame(drawEdgeNumbers);
    if (video.readyState < 2 || timestamp - lastEdgeDraw < 260) return;
    lastEdgeDraw = timestamp;

    const width = 240;
    const height = Math.max(100, Math.round(width * window.innerHeight / window.innerWidth));
    edgeSampleCanvas.width = width;
    edgeSampleCanvas.height = height;

    try {
      const videoWidth = video.videoWidth || width;
      const videoHeight = video.videoHeight || height;
      const coverScale = Math.max(width / videoWidth, height / videoHeight);
      const drawWidth = videoWidth * coverScale;
      const drawHeight = videoHeight * coverScale;
      edgeSampleContext.drawImage(
        video,
        (width - drawWidth) / 2,
        (height - drawHeight) / 2,
        drawWidth,
        drawHeight
      );
      const pixels = edgeSampleContext.getImageData(0, 0, width, height).data;
      const luminance = (x, y) => {
        const index = (
          Math.max(0, Math.min(height - 1, y)) * width
          + Math.max(0, Math.min(width - 1, x))
        ) * 4;
        return pixels[index] * 0.2126
          + pixels[index + 1] * 0.7152
          + pixels[index + 2] * 0.0722;
      };
      const readings = [];

      for (let y = 3; y < height - 3; y += 2) {
        for (let x = 3; x < width - 3; x += 2) {
          const center = luminance(x, y);
          if (center > 205) continue;
          const contrast = Math.max(
            Math.abs(center - luminance(x - 2, y)),
            Math.abs(center - luminance(x + 2, y)),
            Math.abs(center - luminance(x, y - 2)),
            Math.abs(center - luminance(x, y + 2))
          );
          if (contrast < 20) continue;
          readings.push({
            x,
            y,
            strength: Math.min(99.9, (contrast * 0.72 + (255 - center) * 0.28) / 2.55)
          });
        }
      }

      readings.sort((a, b) => b.strength - a.strength);
      const selected = [];
      for (const reading of readings) {
        const overlaps = selected.some((other) => (
          Math.hypot(other.x - reading.x, other.y - reading.y) < 11
        ));
        if (!overlaps) selected.push(reading);
        if (selected.length >= 60) break;
      }

      edgeContext.clearRect(0, 0, window.innerWidth, window.innerHeight);
      edgeContext.font = '600 6px "IBM Plex Mono", "SFMono-Regular", Consolas, monospace';
      edgeContext.textBaseline = 'middle';
      edgeContext.fillStyle = 'rgba(0, 0, 0, 0.9)';
      selected.forEach((reading, index) => {
        const x = reading.x / width * window.innerWidth;
        const y = reading.y / height * window.innerHeight;
        edgeContext.fillText(
          `${String(index + 1).padStart(2, '0')}  ${reading.strength.toFixed(1)}`,
          x + 4,
          y - 4
        );
      });
    } catch (_) {
      edgeContext.clearRect(0, 0, window.innerWidth, window.innerHeight);
    }
  };

  const applySession = async (session) => {
    const nextCrystal = normalizeCrystal(session?.crystal);
    if (!nextCrystal) return;

    activeSession = session;
    if (session.kind === 'analysis_rehearsal') {
      const phase = String(session.phase || 'analysis_countdown');
      const phaseElapsed = Math.max(
        0,
        (Date.now() - Number(session.presentation?.stageStartedAtEpochMs || Date.now())) / 1000
      );
      const terminalWaiting = [
        'analysis_countdown', 'crystallisation_playback', 'material_analysis'
      ].includes(phase) || (phase === 'analysis_complete' && phaseElapsed < ANALYSIS_COMPLETE_HOLD_SECONDS);
      body.classList.toggle('single-output-countdown', terminalWaiting);
      if (phase === 'analysis_countdown') {
        analysisPlaybackActive = false;
        warmAnalysisOutputs(session, nextCrystal);
        const remaining = analysisCountdownRemaining(session);
        setWaitingState(
          true,
          'ICE CRYSTALLISATION BEGINS IN',
          `00:${String(remaining).padStart(2, '0')}`
        );
        return;
      }
      if (phase === 'crystallisation_playback') {
        analysisPlaybackActive = false;
        setWaitingState(true, '', 'WAITING');
        return;
      }
      if (phase === 'material_analysis') {
        analysisPlaybackActive = false;
        setWaitingState(true, '', 'WAITING');
        return;
      }
      if (phase === 'analysis_complete') {
        const sharedTime = phaseElapsed - ANALYSIS_COMPLETE_HOLD_SECONDS;
        if (sharedTime < 0) {
          analysisPlaybackActive = false;
          setWaitingState(true, '', 'WAITING');
          return;
        }
        const sharedPlayback = sharedTime < ANALYSIS_SHARED_PLAYBACK_SECONDS;
        if (sharedPlayback) {
          analysisPlaybackActive = true;
          const playbackStartedAt = Number(
            session.presentation?.sharedPlaybackStartedAtEpochMs || Date.now()
          );
          const sharedSourceDuration = Math.max(1, Number(session.playback?.durationSeconds || 20));
          const sharedSourceTime = Math.max(0, (Date.now() - playbackStartedAt) / 1000)
            % sharedSourceDuration;
          const sharedCuts = [
            [0, 5, 'source'], [5, 7, 'motion'], [7, 9, 'edge'],
            [9, 11, 'threshold'], [11, Infinity, 'source']
          ];
          const sharedKey = sharedCuts.find(([from, to]) => sharedSourceTime >= from && sharedSourceTime < to)?.[2] || 'source';
          const sharedOutput = sharedKey === 'source'
            ? { key: 'source', label: 'Source', look: '', section: 'source', file: 'crystallization.mp4', job: '', outputIndex: null }
            : outputCatalog[sharedKey];
          activeOutput = sharedOutput;
          crystal = nextCrystal;
          sourceUrl = sharedKey === 'source'
            ? session.playback?.url
            : sessionUrl(session, crystal, activeOutput);
          body.dataset.look = activeOutput.look;
          body.dataset.activeOutput = activeOutput.key;
          setWaitingState(false);
          if (typeof window.syncMorphogenesisVideo === 'function') {
            const sharedSession = {
              ...session,
              playback: {
                ...session.playback,
                startedAtEpochMs: playbackStartedAt,
                offsetSeconds: 0
              }
            };
            await window.syncMorphogenesisVideo(video, sharedSession, sourceUrl, { timeline: 'seconds' });
          } else {
            await bindStandalone(sourceUrl);
          }
          return;
        }
        if (analysisPlaybackActive) {
          analysisPlaybackActive = false;
          playlistIndex = 0;
          activeOutput = playlist[0] || fixedOutput;
        }
        setWaitingState(false);
      }
      if (['resonance_terminal', 'resonance_animation', 'diffusion_terminal', 'diffusion_active'].includes(phase)) {
        if (analysisPlaybackActive || !playlist.includes(activeOutput)) {
          analysisPlaybackActive = false;
          playlistIndex = 0;
          activeOutput = playlist[0] || fixedOutput;
          sourceUrl = sessionUrl(session, nextCrystal, activeOutput);
          body.dataset.look = activeOutput.look;
          body.dataset.activeOutput = activeOutput.key;
          if (typeof window.syncMorphogenesisVideo === 'function') {
            await window.syncMorphogenesisVideo(video, session, sourceUrl, { timeline: 'normalized' });
          } else {
            await bindStandalone(sourceUrl);
          }
        }
        setWaitingState(false);
      }
    } else {
      analysisPlaybackActive = false;
      body.classList.add('single-output-countdown');
      video.pause();
      setWaitingState(true, '', 'SYSTEM STANDBY');
      return;
    }
    const relevantJob = session?.jobs?.[activeOutput.job];
    if (
      !['archive_cycle', 'analysis_rehearsal'].includes(session.kind)
      && relevantJob?.state !== 'complete'
    ) {
      return;
    }

    crystal = nextCrystal;
    sourceUrl = sessionUrl(session, crystal, activeOutput);
    sourceError = '';
    body.dataset.look = activeOutput.look;
    body.dataset.activeOutput = activeOutput.key;
    if (typeof window.syncMorphogenesisVideo === 'function' && session?.playback) {
      await window.syncMorphogenesisVideo(
        video,
        session,
        sourceUrl,
        { timeline }
      );
    } else {
      await bindStandalone(sourceUrl);
    }
  };

  const rotatePlaylist = () => {
    if (playlist.length < 2) return;
    if (activeSession?.kind !== 'analysis_rehearsal') return;
    if (activeSession?.kind === 'analysis_rehearsal' && [
      'analysis_countdown', 'crystallisation_playback', 'material_analysis'
    ].includes(activeSession.phase)) return;
    playlistIndex = (playlistIndex + 1) % playlist.length;
    activeOutput = playlist[playlistIndex];
    sourceError = '';
    body.dataset.look = activeOutput.look;
    body.dataset.activeOutput = activeOutput.key;
    if (activeSession) {
      applySession(activeSession).catch(() => {});
      return;
    }
    sourceUrl = defaultUrl(crystal, activeOutput);
    bindStandalone(sourceUrl).catch(() => {});
  };

  const noteMediaEvent = (event) => {
    lastMediaEvent = event.type;
    lastMediaEventAt = Date.now();
  };

  [
    'loadstart', 'loadedmetadata', 'loadeddata', 'canplay', 'playing',
    'waiting', 'stalled', 'suspend', 'abort', 'emptied', 'error'
  ].forEach((eventName) => video.addEventListener(eventName, noteMediaEvent));

  video.addEventListener('canplay', () => {
    video.play().catch((error) => {
      sourceError = `Playback waiting: ${error.name || 'browser policy'}`;
    });
  });
  video.addEventListener('playing', () => {
    sourceError = '';
    mediaRetryCount = 0;
  });
  video.addEventListener('error', () => {
    const mediaError = video.error;
    sourceError = mediaError
      ? `Media ${mediaError.code}: ${mediaError.message || sourceUrl || file}`
      : `Unable to play ${sourceUrl || file}`;
  });

  const resumePlayback = () => {
    video.muted = true;
    video.play().catch(() => {});
  };
  window.addEventListener('pointerdown', resumePlayback, { passive: true });
  window.addEventListener('touchstart', resumePlayback, { passive: true });
  window.addEventListener('keydown', resumePlayback);

  window.setInterval(() => {
    if (
      !video.dataset.morphogenesisSourceUrl
      || video.readyState >= HTMLMediaElement.HAVE_METADATA
      || Date.now() - lastMediaEventAt < 6500
      || mediaRetryCount >= 3
    ) return;
    mediaRetryCount += 1;
    lastMediaEvent = `retry-${mediaRetryCount}`;
    lastMediaEventAt = Date.now();
    video.load();
    resumePlayback();
  }, 2500);

  window.addEventListener('morphogenesis-session', (event) => {
    applySession(event.detail).catch(() => {});
  });
  window.addEventListener('morphogenesis-session-tick', (event) => {
    applySession(event.detail).catch(() => {});
  });

  window.getMorphogenesisPageDetails = () => ({
    source: sourceUrl || defaultUrl(crystal, activeOutput),
    crystal,
    output: activeOutput.label,
    displayRole: body.dataset.displayRole || null,
    playlist: playlist.map((item) => item.key),
    playlistIndex,
    playing: !video.paused && !video.ended,
    currentTime: Number.isFinite(video.currentTime) ? Number(video.currentTime.toFixed(2)) : 0,
    duration: Number.isFinite(video.duration) ? Number(video.duration.toFixed(2)) : null,
    readyState: video.readyState,
    networkState: video.networkState,
    currentSrc: video.currentSrc,
    lastMediaEvent,
    mediaRetryCount,
    error: sourceError
  });

  const heartbeatPayload = (active = true) => ({
    page,
    active,
    visible: document.visibilityState === 'visible',
    title: document.title,
    url: window.location.href,
    details: window.getMorphogenesisPageDetails()
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

  body.dataset.look = activeOutput.look;
  body.dataset.activeOutput = activeOutput.key;
  sourceUrl = defaultUrl(crystal, activeOutput);
  video.pause();
  body.classList.add('single-output-countdown');
  setWaitingState(true, '', 'SYSTEM STANDBY');
  if (window.morphogenesisSession) {
    applySession(window.morphogenesisSession).catch(() => {});
  }
  heartbeat();
  window.setInterval(heartbeat, 3000);
  if (playlist.length > 1) {
    window.setInterval(rotatePlaylist, rotationSeconds * 1000);
  }

  if (edgeNumbers) {
    resizeEdgeNumbers();
    window.addEventListener('resize', resizeEdgeNumbers);
    window.requestAnimationFrame(drawEdgeNumbers);
  }
})();
