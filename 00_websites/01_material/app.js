(() => {
  'use strict';

  const sequences = [
    {
      name: 'Edge field',
      file: 'edge.mp4',
      outputIndex: 0
    },
    {
      name: 'Space–time rows 200 / 400 / 600 / 800',
      file: 'spacetime.mp4',
      outputIndex: 2
    },
    {
      name: 'Motion history / black blue',
      file: 'motion.mp4',
      outputIndex: 3
    }
  ];

  const stage = document.getElementById('material-stage');
  const video = document.getElementById('analysis-video');
  const edgeNumbers = document.getElementById('edge-numbers');
  const edgeContext = edgeNumbers.getContext('2d');
  const sampleCanvas = document.createElement('canvas');
  const sampleContext = sampleCanvas.getContext('2d', { willReadFrequently: true });
  const sequenceList = document.getElementById('sequence-list');
  const sourceLabel = document.getElementById('source-label');
  const sequenceCount = document.getElementById('sequence-count');
  const methodIndex = document.getElementById('method-index');
  const methodName = document.getElementById('method-name');
  const timeReadout = document.getElementById('time-readout');
  let current = 0;
  let crystal = 'ice_crystal_01';
  let sessionMode = false;
  let sessionOutputReady = false;
  let sessionRevision = 0;
  let sessionCreatedAt = '';
  let archiveCycleApplied = '';
  let lastEdgeDraw = 0;
  const pageParameters = new URLSearchParams(window.location.search);
  const standaloneMode = pageParameters.get('standalone');
  const previewMethod = pageParameters.get('method');

  const pad = (value) => String(value).padStart(2, '0');
  const clock = (seconds) => {
    const safe = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
    return `${pad(Math.floor(safe / 60))}:${pad(Math.floor(safe % 60))}`;
  };

  const sessionProgress = (session) => {
    const playback = session?.playback;
    const duration = Number(playback?.durationSeconds);
    if (!playback?.startedAtEpochMs || !Number.isFinite(duration) || duration <= 0) return 0;
    const elapsed = (Date.now() - Number(playback.startedAtEpochMs)) / 1000;
    const time = ((elapsed + Number(playback.offsetSeconds || 0)) % duration + duration) % duration;
    return time / duration;
  };

  const updateLedger = () => {
    [...sequenceList.children].forEach((item, index) => {
      item.classList.toggle('active', index === current);
      item.classList.toggle('complete', index < current);
    });
  };

  const resizeEdgeNumbers = () => {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    edgeNumbers.width = Math.round(window.innerWidth * ratio);
    edgeNumbers.height = Math.round(window.innerHeight * ratio);
    edgeNumbers.style.width = `${window.innerWidth}px`;
    edgeNumbers.style.height = `${window.innerHeight}px`;
    edgeContext.setTransform(ratio, 0, 0, ratio, 0, 0);
  };

  const drawEdgeNumbers = (timestamp = 0) => {
    window.requestAnimationFrame(drawEdgeNumbers);
    if (edgeNumbers.hidden || video.readyState < 2 || timestamp - lastEdgeDraw < 260) return;
    lastEdgeDraw = timestamp;

    const width = 240;
    const height = Math.max(100, Math.round(width * window.innerHeight / window.innerWidth));
    sampleCanvas.width = width;
    sampleCanvas.height = height;

    try {
      const videoWidth = video.videoWidth || width;
      const videoHeight = video.videoHeight || height;
      const coverScale = Math.max(width / videoWidth, height / videoHeight);
      const drawWidth = videoWidth * coverScale;
      const drawHeight = videoHeight * coverScale;
      sampleContext.drawImage(
        video,
        (width - drawWidth) / 2,
        (height - drawHeight) / 2,
        drawWidth,
        drawHeight
      );
      const pixels = sampleContext.getImageData(0, 0, width, height).data;
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
      selected.forEach((reading, index) => {
        const x = reading.x / width * window.innerWidth;
        const y = reading.y / height * window.innerHeight;
        edgeContext.fillStyle = 'rgba(0, 0, 0, 0.9)';
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

  const playSequence = (index) => {
    sessionMode = false;
    video.loop = false;
    current = (index + sequences.length) % sequences.length;
    const sequence = sequences[current];
    sequenceCount.textContent = `${pad(current + 1)} / ${pad(sequences.length)}`;
    methodIndex.textContent = `[${pad(current + 1)}]`;
    methodName.textContent = sequence.name;
    edgeNumbers.hidden = sequence.file !== 'edge.mp4';
    stage.classList.toggle('show-edge-numbers', !edgeNumbers.hidden);
    stage.classList.toggle('show-bright-motion', sequence.file === 'motion.mp4');
    if (edgeNumbers.hidden) {
      edgeContext.clearRect(0, 0, window.innerWidth, window.innerHeight);
    }
    updateLedger();
    video.src = sequence.url
      || `/05_shared_data/exhibition/${crystal}/01_material_analysis/${sequence.file}`;
    video.load();
    video.play().catch(() => {});
  };

  const setCrystal = (value) => {
    const match = String(value || '').match(/^ice_crystal_(\d+)$/i);
    if (!match) return false;
    crystal = `ice_crystal_${pad(match[1])}`;
    sequences.forEach((sequence) => delete sequence.url);
    sourceLabel.textContent = `Recorded analysis / ice crystal ${pad(match[1])}`;
    playSequence(0);
    return true;
  };

  sequences.forEach((sequence) => {
    const item = document.createElement('li');
    item.textContent = sequence.name;
    sequenceList.append(item);
  });

  video.addEventListener('timeupdate', () => {
    const duration = Number.isFinite(video.duration) ? video.duration : 0;
    timeReadout.textContent = `${clock(video.currentTime)} / ${clock(duration)}`;
  });

  video.addEventListener('ended', () => {
    if (!sessionMode) playSequence(current + 1);
  });
  video.addEventListener('error', () => {
    if (!sessionMode) window.setTimeout(() => playSequence(current + 1), 800);
  });

  window.getMorphogenesisPageDetails = () => ({
    source: 'recorded',
    crystal,
    analysis: sequences[current].name,
    sequence: current + 1,
    playing: !video.paused
  });

  window.handleMorphogenesisCommand = (command) => {
    if (command?.action !== 'setSource') return false;
    return setCrystal(command.value);
  };

  const applySession = async (session) => {
    if (session?.kind === 'archive_cycle') {
      const archiveKey = `${session.crystal}:${session.playback?.revision || 0}`;
      const archiveChanged = archiveCycleApplied !== archiveKey;
      if (archiveChanged) {
        archiveCycleApplied = archiveKey;
        sessionOutputReady = true;
        crystal = session.crystal;
        const archiveFiles = session?.jobs?.material?.outputUrls || [];
        sequences.forEach((sequence) => {
          sequence.url = archiveFiles[sequence.outputIndex]
            || `/05_shared_data/exhibition/${crystal}/01_material_analysis/${sequence.file}`;
        });
      }
      const desiredSequence = Math.min(
        sequences.length - 1,
        Math.floor(sessionProgress(session) * sequences.length)
      );
      if (archiveChanged || current !== desiredSequence) playSequence(desiredSequence);
      sourceLabel.textContent = 'Archive replay';
      await window.syncMorphogenesisVideo?.(
        video,
        session,
        sequences[current].url,
        { timeline: 'normalized' }
      );
      return;
    }
    archiveCycleApplied = '';
    const job = session?.jobs?.material;
    if (session?.kind === 'live_capture' && job?.state !== 'complete') {
      return;
    }
    if (session?.createdAt && sessionCreatedAt !== session.createdAt) {
      sessionCreatedAt = session.createdAt;
      video.pause();
      video.removeAttribute('src');
      video.load();
      sessionOutputReady = false;
      sessionRevision = 0;
      sequences.forEach((sequence) => delete sequence.url);
    }
    if (job?.state === 'complete' && !sessionOutputReady) {
      sessionOutputReady = true;
      crystal = session.crystal;
      sequences.forEach((sequence) => {
        const url = (job.outputUrls || [])[sequence.outputIndex];
        if (url) sequence.url = url;
      });
      playSequence(0);
      sourceLabel.textContent = session.kind === 'archive_cycle'
        ? `Archive replay / ${session.crystal.replaceAll('_', ' ')}`
        : `New live result / ${session.crystal.replaceAll('_', ' ')}`;
      return;
    }
    if (sessionOutputReady) return;
    const playback = session?.playback;
    if (!playback?.url) return;
    sessionMode = true;
    if (sessionRevision !== playback.revision) {
      sessionRevision = playback.revision;
      current = 0;
      methodIndex.textContent = '[LIVE]';
      methodName.textContent = playback.stage === 'raw' ? 'OBSERVING SURFACE' : 'FORMATION CLIP';
      sequenceCount.textContent = 'INPUT';
      sourceLabel.textContent = playback.stage === 'raw'
        ? `Simulated camera / ${session.crystal.replaceAll('_', ' ')}`
        : `Formation detected / pre-roll 2s`;
    }
    await window.syncMorphogenesisVideo?.(video, session, playback.url);
  };

  if (standaloneMode === 'ice_crystal_01' || standaloneMode === 'ice_crystal_02') {
    setCrystal(standaloneMode);
    const previewIndex = sequences.findIndex((sequence) => sequence.file.startsWith(previewMethod || ''));
    if (previewMethod && previewIndex >= 0) playSequence(previewIndex);
  } else {
    window.addEventListener('morphogenesis-session', (event) => applySession(event.detail));
    window.addEventListener('morphogenesis-session-tick', (event) => applySession(event.detail));
    playSequence(0);
  }

  resizeEdgeNumbers();
  window.addEventListener('resize', resizeEdgeNumbers);
  window.requestAnimationFrame(drawEdgeNumbers);
})();
