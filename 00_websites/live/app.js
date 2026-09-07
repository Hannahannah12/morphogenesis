(() => {
  'use strict';

  const root = document.getElementById('observation');
  const cameraVideo = document.getElementById('camera-video');
  const archiveVideo = document.getElementById('archive-video');
  const archiveCutFlash = document.getElementById('archive-cut-flash');
  const archiveCutVideos = {
    source: archiveVideo,
    edge: document.getElementById('archive-edge-video'),
    threshold: document.getElementById('archive-threshold-video'),
    motion: document.getElementById('archive-motion-video')
  };
  const mediaStage = document.querySelector('.media-stage');
  const livePane = document.querySelector('.live-pane');
  const mainSplitter = document.getElementById('main-splitter');
  const thermalSplitter = document.getElementById('thermal-splitter');
  const cameraButton = document.getElementById('camera-button');
  const cameraSelect = document.getElementById('camera-select');
  const archiveButton = document.getElementById('archive-button');
  const agentStateSelect = document.getElementById('agent-state-select');
  const fullscreenButton = document.getElementById('fullscreen-button');
  const sourceLabel = document.getElementById('source-label');
  const agentLabel = document.getElementById('agent-label');
  const temperatureLabel = document.getElementById('temperature');
  const ambientTemperatureLabel = document.getElementById('ambient-temperature');
  const thermalCanvas = document.getElementById('thermal-canvas');
  const thermalContext = thermalCanvas.getContext('2d', { alpha: false });
  const thermalSource = document.createElement('canvas');
  thermalSource.width = 32;
  thermalSource.height = 24;
  const thermalSourceContext = thermalSource.getContext('2d', { alpha: false });
  const sensorState = document.getElementById('sensor-state');
  const dateLabel = document.getElementById('date-label');
  const clockLabel = document.getElementById('clock-label');
  const notice = document.getElementById('notice');
  const analysisOverlay = document.getElementById('analysis-overlay');
  const analysisKicker = document.getElementById('analysis-kicker');
  const analysisTitle = document.getElementById('analysis-title');
  const analysisValue = document.getElementById('analysis-value');
  const analysisProcess = document.getElementById('analysis-process');
  const analysisStartButton = document.getElementById('analysis-start-button');

  let cameraStream = null;
  let noticeTimer = null;
  let currentCameraLabel = 'USB Camera';
  let sessionMode = false;
  let sessionCreatedAt = '';
  let archiveCycleApplied = '';
  let cameraLastError = '';
  let experimentRecorder = null;
  let experimentChunks = [];
  let experimentCrystal = '';
  let detectionTimer = null;
  let detectionBaseline = null;
  let detectionBaselineEnergy = 0;
  let detectionSamples = 0;
  let detectionHits = 0;
  let formationStopTimer = null;
  let thermalSequence = -1;
  let thermalDisplay = new Float64Array(768);
  let thermalDisplayMin = NaN;
  let thermalDisplayMax = NaN;
  let archiveCutCrystal = 'ice_crystal_01';
  const stabilizedArchiveRoots = {
    ice_crystal_01: '/09_experiments/05_stabilization/ice_crystal_01_fixed_lock',
    ice_crystal_02: '/09_experiments/05_stabilization/ice_crystal_02_plate_lock_v3',
    ice_crystal_03: '/09_experiments/05_stabilization/ice_crystal_03_global_lock',
    ice_crystal_04: '/09_experiments/05_stabilization/ice_crystal_04_fixed_lock',
    ice_crystal_05: '/09_experiments/05_stabilization/ice_crystal_05_global_lock',
    ice_crystal_06: '/09_experiments/05_stabilization/ice_crystal_06_global_lock_v2'
  };

  const stabilizedSourceFor = (crystal, fallback = '') => {
    const root = stabilizedArchiveRoots[crystal];
    return root ? `${root}/source/crystallization_stabilized.mp4` : fallback;
  };
  let archiveCutEnabled = true;
  let archiveCutLayer = 'source';
  let analysisOutputLayer = '';
  let analysisStageKey = '';
  let analysisSession = null;
  let analysisOverlayHideTimer = 0;
  let analysisPlaybackReleased = false;
  const archiveCutReady = new Set();
  thermalDisplay.fill(NaN);

  const archiveCuts = [
    { from: 0, to: 5, layer: 'source' },
    { from: 5, to: 7, layer: 'motion' },
    { from: 7, to: 9, layer: 'edge' },
    { from: 9, to: 11, layer: 'threshold' },
    { from: 11, to: Infinity, layer: 'source' }
  ];

  const archiveLayerAt = (time) => {
    if (analysisOutputLayer && archiveCutReady.has(analysisOutputLayer)) {
      return analysisOutputLayer;
    }
    if (analysisSession?.phase === 'material_analysis') return 'source';
    const requested = archiveCuts.find((cut) => time >= cut.from && time < cut.to)?.layer || 'source';
    return requested === 'source' || archiveCutReady.has(requested) ? requested : 'source';
  };

  const fireArchiveCut = () => {
    archiveCutFlash.classList.remove('fire');
    void archiveCutFlash.offsetWidth;
    archiveCutFlash.classList.add('fire');
  };

  const showArchiveLayer = (name, flash = true) => {
    const activeVideo = archiveCutVideos[name];
    if (name === archiveCutLayer && activeVideo?.classList.contains('active')) {
      if (activeVideo.paused) activeVideo.play().catch(() => {});
      return;
    }
    Object.entries(archiveCutVideos).forEach(([key, video]) => {
      video.classList.toggle('active', key === name);
      if (key !== 'source' && key !== name) video.pause();
    });
    if (activeVideo) {
      activeVideo.muted = true;
      if (name !== 'source' && activeVideo.readyState >= 1) {
        const duration = Number(activeVideo.duration);
        const sourceTime = Number(archiveVideo.currentTime || 0);
        if (Number.isFinite(duration) && duration > 0) {
          activeVideo.currentTime = sourceTime % duration;
        }
      }
      activeVideo.play().catch(() => {});
    }
    if (flash && archiveCutEnabled) fireArchiveCut();
    archiveCutLayer = name;
  };

  const setArchiveCutEnabled = (enabled) => {
    const nextEnabled = Boolean(enabled);
    if (nextEnabled === archiveCutEnabled) return;
    archiveCutEnabled = nextEnabled;
    if (!archiveCutEnabled) {
      Object.values(archiveCutVideos).slice(1).forEach((video) => video.pause());
      showArchiveLayer('source', false);
      return;
    }
    archiveVideo.muted = true;
    archiveVideo.play().catch(() => {});
    Object.values(archiveCutVideos).slice(1).forEach((video) => video.pause());
    showArchiveLayer(archiveLayerAt(archiveVideo.currentTime || 0), false);
  };

  const setArchiveCutSources = (crystal, outputUrls = []) => {
    const normalized = /^ice_crystal_\d{2}$/.test(crystal || '') ? crystal : 'ice_crystal_01';
    const stabilizedRoot = stabilizedArchiveRoots[normalized];
    const base = stabilizedRoot
      ? `${stabilizedRoot}/01_material_analysis`
      : `/05_shared_data/exhibition/${normalized}/01_material_analysis`;
    const sources = {
      edge: `${base}/edge_numbers.mp4`,
      threshold: stabilizedRoot ? `${base}/threshold.mp4` : outputUrls[1] || `${base}/threshold.mp4`,
      motion: stabilizedRoot ? `${base}/motion.mp4` : outputUrls[3] || `${base}/motion.mp4`
    };
    archiveCutCrystal = normalized;
    Object.entries(sources).forEach(([name, url]) => {
      const video = archiveCutVideos[name];
      const absolute = new URL(url, window.location.origin).href;
      if (video.dataset.analysisSource === absolute) return;
      archiveCutReady.delete(name);
      video.pause();
      video.src = absolute;
      video.dataset.analysisSource = absolute;
      video.load();
      if (archiveCutEnabled && archiveCutLayer === name) video.play().catch(() => {});
    });
  };

  ['edge', 'threshold', 'motion'].forEach((name) => {
    const video = archiveCutVideos[name];
    video.addEventListener('canplay', () => archiveCutReady.add(name));
    video.addEventListener('error', () => {
      archiveCutReady.delete(name);
      if (archiveCutLayer === name) showArchiveLayer('source', false);
    });
  });

  const updateArchiveCut = () => {
    if (archiveCutEnabled) {
      const time = archiveVideo.currentTime || 0;
      const targetLayer = archiveLayerAt(time);
      showArchiveLayer(targetLayer);
      if (targetLayer !== 'source' && archiveCutReady.has(targetLayer)) {
        const follower = archiveCutVideos[targetLayer];
        const duration = Number(follower.duration);
        const expected = Number.isFinite(duration) && duration > 0 ? time % duration : time;
        let difference = expected - (follower.currentTime || 0);
        if (Number.isFinite(duration) && duration > 0 && Math.abs(difference) > duration / 2) {
          difference += difference > 0 ? -duration : duration;
        }
        if (follower.paused) follower.play().catch(() => {});
        if (Math.abs(difference) > 0.09) {
          follower.currentTime = expected;
          follower.playbackRate = 1;
        } else {
          follower.playbackRate = Math.max(0.97, Math.min(1.03, 1 + difference * 0.18));
        }
      }
    }
    window.requestAnimationFrame(updateArchiveCut);
  };

  const CAMERA_STORAGE_KEY = 'morphogenesis-camera-id';
  const ARCHIVE_SPLIT_STORAGE_KEY = 'morphogenesis-live-archive-split';
  const THERMAL_SPLIT_STORAGE_KEY = 'morphogenesis-live-thermal-split';

  const clampSplit = (value) => Math.max(.2, Math.min(.8, value));
  const readSplit = (key, fallback) => {
    try {
      const value = Number(localStorage.getItem(key));
      return Number.isFinite(value) && value >= .2 && value <= .8 ? value : fallback;
    } catch (_) {
      return fallback;
    }
  };
  let archiveSplit = readSplit(ARCHIVE_SPLIT_STORAGE_KEY, .5);
  let thermalSplit = readSplit(THERMAL_SPLIT_STORAGE_KEY, 2 / 3);
  let activeResize = null;

  const persistSplit = (key, value) => {
    try {
      localStorage.setItem(key, value.toFixed(4));
    } catch (_) {
      // Resizing still works when browser storage is unavailable.
    }
  };

  const applyPanelSizes = () => {
    const stageRect = mediaStage.getBoundingClientRect();
    const liveRect = livePane.getBoundingClientRect();
    if (stageRect.width > 0) {
      const availableWidth = Math.max(1, stageRect.width - mainSplitter.offsetWidth);
      document.documentElement.style.setProperty('--archive-size', `${availableWidth * archiveSplit}px`);
      mainSplitter.setAttribute('aria-valuenow', String(Math.round(archiveSplit * 100)));
    }
    if (liveRect.height > 0) {
      const availableHeight = Math.max(1, liveRect.height - thermalSplitter.offsetHeight);
      document.documentElement.style.setProperty('--camera-size', `${availableHeight * thermalSplit}px`);
      thermalSplitter.setAttribute('aria-valuenow', String(Math.round(thermalSplit * 100)));
    }
  };

  const updateResize = (event) => {
    if (!activeResize) return;
    if (activeResize === 'archive') {
      const rect = mediaStage.getBoundingClientRect();
      const available = Math.max(1, rect.width - mainSplitter.offsetWidth);
      archiveSplit = clampSplit((event.clientX - rect.left) / available);
    } else {
      const rect = livePane.getBoundingClientRect();
      const available = Math.max(1, rect.height - thermalSplitter.offsetHeight);
      thermalSplit = clampSplit((event.clientY - rect.top) / available);
    }
    applyPanelSizes();
  };

  const finishResize = () => {
    if (!activeResize) return;
    persistSplit(ARCHIVE_SPLIT_STORAGE_KEY, archiveSplit);
    persistSplit(THERMAL_SPLIT_STORAGE_KEY, thermalSplit);
    activeResize = null;
    document.body.classList.remove('is-resizing');
    document.body.style.cursor = '';
  };

  const startResize = (kind, event) => {
    if (event.button !== undefined && event.button !== 0) return;
    event.preventDefault();
    activeResize = kind;
    document.body.classList.add('is-resizing');
    document.body.style.cursor = kind === 'archive' ? 'col-resize' : 'row-resize';
    updateResize(event);
  };

  const nudgeSplit = (kind, amount) => {
    if (kind === 'archive') archiveSplit = clampSplit(archiveSplit + amount);
    else thermalSplit = clampSplit(thermalSplit + amount);
    applyPanelSizes();
    persistSplit(
      kind === 'archive' ? ARCHIVE_SPLIT_STORAGE_KEY : THERMAL_SPLIT_STORAGE_KEY,
      kind === 'archive' ? archiveSplit : thermalSplit
    );
  };

  mainSplitter.addEventListener('pointerdown', (event) => startResize('archive', event));
  thermalSplitter.addEventListener('pointerdown', (event) => startResize('thermal', event));
  window.addEventListener('pointermove', updateResize);
  window.addEventListener('pointerup', finishResize);
  window.addEventListener('pointercancel', finishResize);
  mainSplitter.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    nudgeSplit('archive', event.key === 'ArrowLeft' ? -.02 : .02);
  });
  thermalSplitter.addEventListener('keydown', (event) => {
    if (!['ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    nudgeSplit('thermal', event.key === 'ArrowUp' ? -.02 : .02);
  });
  mainSplitter.addEventListener('dblclick', () => {
    archiveSplit = .5;
    nudgeSplit('archive', 0);
  });
  thermalSplitter.addEventListener('dblclick', () => {
    thermalSplit = 2 / 3;
    nudgeSplit('thermal', 0);
  });

  const postCaptureStatus = (action, message = '') => fetch('/api/agent/live-capture-status', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, crystal: experimentCrystal, message })
  });

  const textureMetrics = (pixels, width, height) => {
    const gray = new Float32Array(width * height);
    let energy = 0;
    for (let i = 0, p = 0; i < pixels.length; i += 4, p++) {
      gray[p] = pixels[i] * .299 + pixels[i + 1] * .587 + pixels[i + 2] * .114;
      if (p % width) energy += Math.abs(gray[p] - gray[p - 1]);
      if (p >= width) energy += Math.abs(gray[p] - gray[p - width]);
    }
    return { gray, energy: energy / (width * height * 2) };
  };

  const stopExperimentRecording = () => {
    window.clearInterval(detectionTimer);
    detectionTimer = null;
    window.clearTimeout(formationStopTimer);
    formationStopTimer = null;
    if (experimentRecorder?.state === 'recording') experimentRecorder.stop();
  };

  const startFormationDetection = () => {
    const width = 160;
    const height = 90;
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    detectionTimer = window.setInterval(() => {
      if (!context || !cameraStream || experimentRecorder?.state !== 'recording') return;
      context.drawImage(cameraVideo, 0, 0, width, height);
      const metrics = textureMetrics(
        context.getImageData(0, 0, width, height).data,
        width,
        height
      );
      if (detectionSamples < 15) {
        if (!detectionBaseline) detectionBaseline = new Float32Array(metrics.gray.length);
        for (let i = 0; i < metrics.gray.length; i++) {
          detectionBaseline[i] += metrics.gray[i] / 15;
        }
        detectionBaselineEnergy += metrics.energy / 15;
        detectionSamples += 1;
        return;
      }
      let difference = 0;
      for (let i = 0; i < metrics.gray.length; i++) {
        difference += Math.abs(metrics.gray[i] - detectionBaseline[i]);
      }
      difference /= metrics.gray.length;
      const textureGrowth = metrics.energy > detectionBaselineEnergy * 1.22 + 0.8;
      detectionHits = difference > 8 || textureGrowth ? detectionHits + 1 : Math.max(0, detectionHits - 1);
      if (detectionHits >= 3 && !formationStopTimer) {
        postCaptureStatus('formation_detected').catch(() => {});
        showNotice('Formation detected — recording the final 2 seconds.', 2800);
        formationStopTimer = window.setTimeout(stopExperimentRecording, 2000);
      }
    }, 200);
  };

  const startExperimentRecording = async (crystal) => {
    if (experimentRecorder?.state === 'recording' || experimentCrystal === crystal) return;
    if (!cameraStream || !cameraVideo.videoWidth) {
      await postCaptureStatus('error', 'Physical camera stream is not ready').catch(() => {});
      showNotice('Recording failed — physical camera is not ready.', 5000);
      return;
    }
    if (!window.MediaRecorder) {
      await postCaptureStatus('error', 'MediaRecorder is unavailable').catch(() => {});
      showNotice('Recording is unavailable in this browser.', 5000);
      return;
    }
    experimentCrystal = crystal;
    experimentChunks = [];
    detectionBaseline = null;
    detectionBaselineEnergy = 0;
    detectionSamples = 0;
    detectionHits = 0;
    const mimeType = [
      'video/webm;codecs=vp9',
      'video/webm;codecs=vp8',
      'video/webm'
    ].find((type) => MediaRecorder.isTypeSupported(type)) || '';
    experimentRecorder = new MediaRecorder(cameraStream, {
      ...(mimeType ? { mimeType } : {}),
      videoBitsPerSecond: 8_000_000
    });
    experimentRecorder.addEventListener('dataavailable', (event) => {
      if (event.data?.size) experimentChunks.push(event.data);
    });
    experimentRecorder.addEventListener('stop', async () => {
      window.clearInterval(detectionTimer);
      detectionTimer = null;
      const blob = new Blob(experimentChunks, { type: experimentRecorder.mimeType || 'video/webm' });
      showNotice('Recording complete — uploading raw experiment.', 5000);
      try {
        const response = await fetch('/api/agent/live-recording', {
          method: 'POST',
          headers: {
            'Content-Type': blob.type || 'video/webm',
            'X-Morphogenesis-Crystal': experimentCrystal
          },
          body: blob
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Upload failed');
        showNotice('Recording saved — turn off Peltier manually — processing three directions.', 8000);
      } catch (error) {
        postCaptureStatus('error', error.message || 'Recording upload failed').catch(() => {});
        showNotice(`Recording save failed — ${error.message || 'unknown error'}`, 7000);
      } finally {
        experimentChunks = [];
        experimentRecorder = null;
      }
    });
    experimentRecorder.start(1000);
    await postCaptureStatus('recording');
    startFormationDetection();
    showNotice('Cooling + recording started.', 3200);
  };

  const showNotice = (message, duration = 3600) => {
    notice.textContent = message;
    notice.classList.add('visible');
    window.clearTimeout(noticeTimer);
    noticeTimer = window.setTimeout(() => notice.classList.remove('visible'), duration);
  };

  const setSource = (mode) => {
    const live = Boolean(cameraStream);
    cameraButton.classList.toggle('active', live);
    archiveButton.classList.add('active');
    sourceLabel.textContent = live
      ? `Archive + Live / ${currentCameraLabel}`
      : 'Archive + Live / camera waiting';
    archiveVideo.play().catch(() => {});
    cameraStream?.getVideoTracks().forEach((track) => { track.enabled = true; });
    if (live) cameraVideo.play().catch(() => {});
  };

  const cameraPreferenceScore = (device) => {
    const label = device.label.toLowerCase();
    if (/integrated|built-in|internal|facetime|front/.test(label)) return -20;
    if (/usb|uvc|external|logitech|brio|elgato|capture|avermedia|webcam/.test(label)) return 20;
    return 0;
  };

  const isPhysicalCamera = (device) => {
    const label = device.label.toLowerCase();
    return !/obs|virtual camera|meta quest/.test(label);
  };

  const listCameras = async (selectedId = '') => {
    const devices = (await navigator.mediaDevices.enumerateDevices())
      .filter((device) => device.kind === 'videoinput')
      .filter(isPhysicalCamera);
    cameraSelect.replaceChildren();
    const automatic = document.createElement('option');
    automatic.value = '';
    automatic.textContent = 'USB camera (auto)';
    cameraSelect.appendChild(automatic);
    devices.forEach((device, index) => {
      const option = document.createElement('option');
      option.value = device.deviceId;
      option.textContent = device.label || `Camera ${index + 1}`;
      cameraSelect.appendChild(option);
    });
    if (!devices.length) {
      automatic.textContent = 'No camera — open in Chrome';
      cameraSelect.title = 'No camera is exposed by this browser. Open the localhost page in Chrome or Edge.';
    } else {
      cameraSelect.title = 'Choose the external USB camera';
    }
    cameraSelect.value = devices.some((device) => device.deviceId === selectedId) ? selectedId : '';
    return devices;
  };

  const stopCamera = () => {
    cameraStream?.getTracks().forEach((track) => track.stop());
    cameraStream = null;
    cameraVideo.srcObject = null;
  };

  const startCamera = async (requestedDeviceId = cameraSelect.value) => {
    if (cameraStream && (!requestedDeviceId || cameraStream.getVideoTracks()[0]?.getSettings().deviceId === requestedDeviceId)) {
      setSource('live');
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      cameraLastError = 'Camera access unavailable in this browser';
      root.dataset.cameraError = cameraLastError;
      showNotice('Camera access is unavailable. Open this page through localhost or HTTPS.');
      return;
    }

    cameraButton.disabled = true;
    cameraSelect.disabled = true;
    cameraButton.textContent = 'Starting…';
    try {
      let nextStream = await navigator.mediaDevices.getUserMedia({
        video: {
          ...(requestedDeviceId ? { deviceId: { exact: requestedDeviceId } } : {}),
          width: { ideal: 1920 },
          height: { ideal: 1080 },
          facingMode: { ideal: 'environment' }
        },
        audio: false
      });

      const devices = await listCameras(requestedDeviceId);
      const savedId = localStorage.getItem(CAMERA_STORAGE_KEY) || '';
      const preferred = devices
        .filter((device) => device.deviceId !== nextStream.getVideoTracks()[0]?.getSettings().deviceId)
        .sort((a, b) => cameraPreferenceScore(b) - cameraPreferenceScore(a))[0];
      const targetId = requestedDeviceId
        || (devices.some((device) => device.deviceId === savedId) ? savedId : '')
        || (preferred && cameraPreferenceScore(preferred) > 0 ? preferred.deviceId : '')
        || devices[0]?.deviceId
        || '';

      if (targetId && nextStream.getVideoTracks()[0]?.getSettings().deviceId !== targetId) {
        nextStream.getTracks().forEach((track) => track.stop());
        nextStream = await navigator.mediaDevices.getUserMedia({
          video: {
            deviceId: { exact: targetId },
            width: { ideal: 1920 },
            height: { ideal: 1080 }
          },
          audio: false
        });
      }

      stopCamera();
      cameraStream = nextStream;
      const activeId = cameraStream.getVideoTracks()[0]?.getSettings().deviceId || targetId;
      const activeDevice = devices.find((device) => device.deviceId === activeId);
      currentCameraLabel = activeDevice?.label || 'USB Camera';
      if (activeId) {
        localStorage.setItem(CAMERA_STORAGE_KEY, activeId);
        cameraSelect.value = activeId;
      }
      cameraVideo.srcObject = cameraStream;
      await cameraVideo.play();
      cameraLastError = '';
      root.dataset.cameraError = '';
      setSource('live');
    } catch (error) {
      cameraLastError = error.name === 'NotAllowedError'
        ? 'Camera permission was not granted'
        : `Camera connection failed: ${error.name || 'unknown error'}`;
      root.dataset.cameraError = cameraLastError;
      setSource('archive');
      showNotice(error.name === 'NotAllowedError'
        ? 'Camera permission was not granted — archive playback continues.'
        : 'Camera could not be opened — archive playback continues.');
    } finally {
      cameraButton.disabled = false;
      cameraSelect.disabled = false;
      cameraButton.textContent = 'Camera';
    }
  };

  const applySystemState = (state) => {
    if (state === 'archive') {
      setSource('archive');
      return;
    }
    if (state === 'live' && cameraStream) {
      setSource('live');
    } else if (state === 'live') {
      sourceLabel.textContent = 'Archive + Live requested / camera not started';
      showNotice('Crystallization is active — start the camera once to grant access.');
    }
  };

  const displayMinimumTemperature = (value) => {
    if (!Number.isFinite(value) || value < -100 || value > 150) return;
    temperatureLabel.textContent = value.toFixed(1);
    sensorState.textContent = 'Arduino sensor / live';
    document.title = `${value.toFixed(1)}°C — Morphogenesis`;
  };

  const displayAmbientTemperature = (value) => {
    if (!Number.isFinite(value) || value < -100 || value > 150) return;
    ambientTemperatureLabel.textContent = value.toFixed(1);
  };

  const thermalColor = (position) => {
    const value = Math.max(0, Math.min(1, position));
    const stops = [
      [0.00, [4, 0, 18]], [0.16, [32, 12, 74]],
      [0.34, [108, 22, 112]], [0.54, [196, 45, 83]],
      [0.72, [242, 110, 42]], [0.88, [252, 200, 72]],
      [1.00, [255, 255, 235]]
    ];
    for (let index = 1; index < stops.length; index++) {
      if (value <= stops[index][0]) {
        const [leftPosition, leftColor] = stops[index - 1];
        const [rightPosition, rightColor] = stops[index];
        const mix = (value - leftPosition) / (rightPosition - leftPosition);
        return leftColor.map((channel, channelIndex) =>
          Math.round(channel + (rightColor[channelIndex] - channel) * mix));
      }
    }
    return stops[stops.length - 1][1];
  };

  const clearThermal = () => {
    thermalContext.fillStyle = '#040012';
    thermalContext.fillRect(0, 0, thermalCanvas.width, thermalCanvas.height);
  };

  const renderThermal = (frame) => {
    if (!frame?.connected || !Array.isArray(frame.temperatures) || frame.temperatures.length !== 768) {
      clearThermal();
      return;
    }
    if (frame.sequence === thermalSequence) return;
    thermalSequence = frame.sequence;
    frame.temperatures.forEach((temperature, pixel) => {
      const value = Number(temperature);
      const previous = thermalDisplay[pixel];
      thermalDisplay[pixel] = Number.isFinite(value)
        ? (Number.isFinite(previous) ? previous + (value - previous) * .34 : value)
        : NaN;
    });
    const sorted = Array.from(thermalDisplay).filter(Number.isFinite).sort((a, b) => a - b);
    if (!sorted.length) return;
    const targetMin = sorted[Math.floor((sorted.length - 1) * .02)];
    const targetMax = sorted[Math.ceil((sorted.length - 1) * .98)];
    thermalDisplayMin = Number.isFinite(thermalDisplayMin)
      ? thermalDisplayMin + (targetMin - thermalDisplayMin) * .18 : targetMin;
    thermalDisplayMax = Number.isFinite(thermalDisplayMax)
      ? thermalDisplayMax + (targetMax - thermalDisplayMax) * .18 : targetMax;
    const span = Math.max(.5, thermalDisplayMax - thermalDisplayMin);
    const image = thermalSourceContext.createImageData(32, 24);
    thermalDisplay.forEach((temperature, pixel) => {
      const color = Number.isFinite(temperature)
        ? thermalColor((temperature - thermalDisplayMin) / span)
        : [0, 0, 0];
      const offset = pixel * 4;
      image.data[offset] = color[0];
      image.data[offset + 1] = color[1];
      image.data[offset + 2] = color[2];
      image.data[offset + 3] = 255;
    });
    thermalSourceContext.putImageData(image, 0, 0);
    thermalContext.imageSmoothingEnabled = true;
    thermalContext.imageSmoothingQuality = 'high';
    thermalContext.drawImage(thermalSource, 0, 0, thermalCanvas.width, thermalCanvas.height);
  };

  const pollThermal = async () => {
    try {
      const response = await fetch('/api/agent/thermal-frame', { cache: 'no-store' });
      if (!response.ok) return;
      renderThermal(await response.json());
    } catch (_) {
      // Shared status polling owns the public disconnected state.
    }
  };

  const applyAgentStatus = async (status) => {
    const state = String(status.state || 'IDLE').toUpperCase();
    agentLabel.textContent = `Agent / ${state.toLowerCase()}`;
    agentStateSelect.value = state;
    const cooling = status.manualCooling || {};
    const recording = cooling.recording || {};
    if (cooling.active && cooling.experimentId) {
      if (!cameraStream || !cameraVideo.videoWidth) await startCamera();
      await startExperimentRecording(cooling.experimentId).catch((error) => {
        postCaptureStatus('error', error.message || 'Recording failed').catch(() => {});
      });
    } else if (
      ['recording', 'waiting_recorder', 'formation_detected', 'stop_requested']
        .includes(recording.state)
      && experimentRecorder?.state === 'recording'
    ) {
      stopExperimentRecording();
    }
    if (status.sensor?.connected) {
      displayMinimumTemperature(Number(status.minimumTemperature));
      displayAmbientTemperature(Number(status.ambientTemperature));
    } else {
      temperatureLabel.textContent = '--.-';
      ambientTemperatureLabel.textContent = '--.-';
      sensorState.textContent = 'Sensor managed by Control Room / disconnected';
      clearThermal();
    }

    if (!sessionMode && !analysisSession) {
      if (state === 'GROWING' || state === 'OBSERVING') applySystemState('live');
      if (state === 'IDLE' || state === 'ARCHIVING') applySystemState('archive');
    }
  };

  const pollAgent = async () => {
    try {
      const response = await fetch('/api/agent/status', { cache: 'no-store' });
      if (!response.ok) throw new Error(`Agent returned ${response.status}`);
      await applyAgentStatus(await response.json());
      agentStateSelect.disabled = false;
    } catch (_) {
      agentLabel.textContent = 'Agent / offline';
      agentStateSelect.disabled = true;
    }
  };

  const setAgentState = async (state) => {
    agentStateSelect.disabled = true;
    try {
      const response = await fetch('/api/agent/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Agent command failed');
      applyAgentStatus(result);
      showNotice(`Agent state changed to ${state}.`, 1800);
    } catch (_) {
      showNotice('Morphogenesis Agent is not running.');
    } finally {
      agentStateSelect.disabled = false;
    }
  };

  const updateClock = () => {
    const now = new Date();
    dateLabel.textContent = new Intl.DateTimeFormat('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric'
    }).format(now);
    clockLabel.dateTime = now.toISOString();
    clockLabel.textContent = new Intl.DateTimeFormat('en-GB', {
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
    }).format(now);
  };

  const analysisElapsed = (presentation) => Math.max(
    0,
    (Date.now() - Number(presentation?.stageStartedAtEpochMs || Date.now())) / 1000
  );

  const setAnalysisBodyPhase = (phase) => {
    document.body.classList.remove(
      'analysis-countdown',
      'analysis-playback',
      'analysis-material',
      'analysis-complete'
    );
    const phaseClass = {
      analysis_countdown: 'analysis-countdown',
      crystallisation_playback: 'analysis-playback',
      material_analysis: 'analysis-material',
      analysis_complete: 'analysis-complete'
    }[phase];
    if (phaseClass) document.body.classList.add(phaseClass);
  };

  const bindAnalysisSource = async (session, playbackStartedAtOverride = null) => {
    const source = stabilizedSourceFor(session.crystal, session.playback?.url);
    if (!source) return;
    const absolute = new URL(source, window.location.origin).href;
    const phase = String(session.phase || '');
    const playbackStartedAt = Number(
      playbackStartedAtOverride || session.playback?.startedAtEpochMs || Date.now()
    );
    archiveVideo.loop = phase !== 'crystallisation_playback';
    const synchronizedSession = {
      ...session,
      playback: {
        ...session.playback,
        startedAtEpochMs: playbackStartedAt,
        offsetSeconds: 0
      }
    };
    if (typeof window.syncMorphogenesisVideo === 'function') {
      await window.syncMorphogenesisVideo(
        archiveVideo,
        synchronizedSession,
        absolute,
        { timeline: 'seconds' }
      );
      return;
    }
    archiveVideo.play().catch(() => {});
  };

  const analysisLogEntries = [
    ['edge', 'Canny edge · contour extraction'],
    ['motion', 'Optical flow · temporal motion'],
    ['threshold', 'Adaptive threshold · region mask']
  ];

  const setAnalysisOverlayVisible = (visible) => {
    if (visible) {
      window.clearTimeout(analysisOverlayHideTimer);
      analysisOverlay.dataset.targetVisible = 'true';
      if (analysisOverlay.classList.contains('visible')) return;
      analysisOverlay.hidden = false;
      window.requestAnimationFrame(() => {
        if (analysisOverlay.dataset.targetVisible === 'true') {
          analysisOverlay.classList.add('visible');
        }
      });
      return;
    }
    if (analysisOverlay.dataset.targetVisible === 'false') return;
    analysisOverlay.dataset.targetVisible = 'false';
    window.clearTimeout(analysisOverlayHideTimer);
    analysisOverlay.classList.remove('visible');
    analysisOverlayHideTimer = window.setTimeout(() => {
      if (analysisOverlay.dataset.targetVisible === 'false') analysisOverlay.hidden = true;
    }, 740);
  };

  const renderAnalysisFrame = () => {
    if (!analysisSession) return;
    const phase = String(analysisSession.phase || 'analysis_countdown');
    const presentation = analysisSession.presentation || {};
    const elapsed = analysisElapsed(presentation);
    const duration = Math.max(.1, Number(presentation.stageDurationSeconds || 1));
    const progress = Math.max(0, Math.min(1, elapsed / duration));
    document.body.classList.toggle('analysis-no-camera', !cameraStream);
    document.documentElement.style.setProperty(
      '--analysis-mask-opacity',
      String(.08 + progress * .78)
    );

    if (phase === 'analysis_countdown') {
      setAnalysisOverlayVisible(true);
      analysisKicker.textContent = cameraStream
        ? 'LIVE SURFACE / THERMAL OBSERVATION'
        : 'CAMERA WAITING / SIMULATED WHITE INPUT';
      analysisTitle.textContent = 'ICE CRYSTALLISATION BEGINS IN';
      analysisValue.textContent = `00:${String(Math.max(0, Math.ceil(duration - elapsed))).padStart(2, '0')}`;
      analysisProcess.replaceChildren();
      return;
    }

    if (phase === 'crystallisation_playback') {
      setAnalysisOverlayVisible(false);
      return;
    }

    if (phase === 'material_analysis') {
      setAnalysisOverlayVisible(true);
      analysisKicker.textContent = 'step 01 / material analysis';
      analysisTitle.textContent = 'Analysing ice crystal structure';
      const outputIndex = Math.max(0, Number(presentation.analysisOutputIndex || 0));
      const outputState = String(presentation.analysisOutputState || 'processing');
      analysisValue.textContent = 'pipeline / running';
      analysisProcess.replaceChildren();
      analysisLogEntries.slice(0, outputIndex + 1).forEach(([key, method], index) => {
        const line = document.createElement('span');
        const finished = index < outputIndex || outputState === 'success';
        line.className = finished ? 'success' : 'running';
        line.textContent = `${String(index + 1).padStart(2, '0')}  ${method}  ${finished ? '[success]' : '[running]'}`;
        analysisProcess.append(line);
      });
      return;
    }

    if (phase === 'analysis_complete' && elapsed < 4) {
      setAnalysisOverlayVisible(true);
      analysisKicker.textContent = 'step 01 / material analysis';
      analysisTitle.textContent = 'Analysis complete';
      analysisValue.textContent = 'outputs synchronised';
      analysisProcess.replaceChildren();
      analysisLogEntries.forEach(([, method], index) => {
        const line = document.createElement('span');
        line.className = 'success';
        line.textContent = `${String(index + 1).padStart(2, '0')}  ${method}  [success]`;
        analysisProcess.append(line);
      });
      return;
    }
    setAnalysisOverlayVisible(false);
  };

  const applyAnalysisSession = async (session) => {
    analysisSession = session;
    analysisStartButton.textContent = 'Stop';
    analysisStartButton.setAttribute('aria-label', 'Stop rehearsal and enter standby');
    document.body.classList.remove('cold-idle');
    document.body.classList.add('analysis-running');
    setAnalysisBodyPhase(session.phase);
    setArchiveCutSources(session.crystal, session.jobs?.material?.outputUrls || []);
    sourceLabel.textContent = session.phase === 'analysis_countdown'
      ? 'Live observation / analysis rehearsal ready'
      : session.phase === 'crystallisation_playback'
        ? 'Ice crystallisation / direct observation'
        : session.phase === 'material_analysis'
          ? 'Material analysis / synchronized outputs'
          : 'Material analysis / complete';

    if (session.phase === 'analysis_countdown') {
      analysisOutputLayer = '';
      setArchiveCutEnabled(false);
    } else if (session.phase === 'crystallisation_playback') {
      analysisOutputLayer = '';
      setArchiveCutEnabled(false);
      showArchiveLayer('source', false);
      await bindAnalysisSource(session);
    } else if (session.phase === 'material_analysis') {
      analysisOutputLayer = '';
      setArchiveCutEnabled(false);
      await bindAnalysisSource(session);
      showArchiveLayer('source', false);
    } else {
      analysisOutputLayer = '';
      if (!analysisPlaybackReleased) {
        analysisPlaybackReleased = true;
        analysisStageKey = '';
      }
      // Material completion is the single hand-off shared with both Medium
      // screens. Live starts its continuous loop immediately—no four-second
      // pause and no later phase can stop it again.
      const materialCompletedAt = Number(
        session.phase === 'analysis_complete'
          ? session.presentation?.stageStartedAtEpochMs
          : session.presentation?.sharedPlaybackStartedAtEpochMs
      ) || Date.now();
      await bindAnalysisSource(session, materialCompletedAt);
      archiveVideo.loop = true;
      setArchiveCutEnabled(true);
    }
    renderAnalysisFrame();
  };

  const clearAnalysisSession = () => {
    if (!analysisSession) return;
    analysisSession = null;
    analysisOutputLayer = '';
    analysisStageKey = '';
    analysisPlaybackReleased = false;
    setAnalysisOverlayVisible(false);
    document.body.classList.remove(
      'analysis-running', 'analysis-no-camera', 'analysis-countdown',
      'analysis-playback', 'analysis-material', 'analysis-complete'
    );
    document.documentElement.style.removeProperty('--analysis-mask-opacity');
  };

  const toggleAnalysisRehearsal = async () => {
    const action = analysisSession?.kind === 'analysis_rehearsal' ? 'stop' : 'start';
    analysisStartButton.disabled = true;
    try {
      const response = await fetch('/api/agent/analysis-rehearsal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `Analysis rehearsal could not ${action}`);
      await applySession(result);
      showNotice(action === 'stop'
        ? 'Rehearsal stopped. System standby.'
        : 'Rehearsal started from the first crystal.');
    } catch (error) {
      showNotice(error.message || 'Morphogenesis Agent is not running.');
    } finally {
      analysisStartButton.disabled = false;
    }
  };

  cameraButton.addEventListener('click', () => startCamera());
  analysisStartButton.addEventListener('click', toggleAnalysisRehearsal);
  try {
    const controlChannel = new BroadcastChannel('morphogenesis-control');
    controlChannel.addEventListener('message', (event) => {
      if (event.data?.type === 'start-camera') startCamera(event.data.deviceId || '');
    });
  } catch (_) {
    // Query-based camera requests remain available.
  }
  cameraSelect.addEventListener('change', () => {
    if (cameraSelect.value) startCamera(cameraSelect.value);
  });
  archiveButton.addEventListener('click', () => {
    sessionMode = false;
    setSource('archive');
  });
  agentStateSelect.addEventListener('change', () => setAgentState(agentStateSelect.value));
  fullscreenButton.addEventListener('click', async () => {
    try {
      if (!document.fullscreenElement) await root.requestFullscreen();
      else await document.exitFullscreen();
    } catch (_) {
      showNotice('Fullscreen mode is unavailable.');
    }
  });

  document.addEventListener('fullscreenchange', () => {
    fullscreenButton.textContent = document.fullscreenElement ? 'Exit fullscreen' : 'Fullscreen';
  });

  window.addEventListener('beforeunload', () => {
    stopCamera();
  });

  const applySession = async (session) => {
    if (session?.kind === 'analysis_rehearsal') {
      await applyAnalysisSession(session);
      return;
    }
    clearAnalysisSession();
    const materialOutputs = session?.jobs?.material?.outputUrls || [];
    if (session?.crystal && session.crystal !== archiveCutCrystal) {
      setArchiveCutSources(session.crystal, materialOutputs);
    }
    const materialReady = session?.kind === 'archive_cycle'
      || session?.jobs?.material?.state === 'complete'
      || session?.phase === 'outputs_ready';
    setArchiveCutEnabled(materialReady);
    if (session?.kind === 'archive_cycle') {
      archiveCycleApplied = '';
      sessionMode = true;
      analysisStartButton.textContent = 'Start';
      analysisStartButton.setAttribute('aria-label', 'Start rehearsal from the first crystal');
      document.body.classList.add('cold-idle');
      setArchiveCutEnabled(false);
      showArchiveLayer('source', false);
      Object.values(archiveCutVideos).forEach((item) => item.pause());
      archiveVideo.pause();
      sourceLabel.textContent = 'System idle / waiting for rehearsal';
      analysisKicker.textContent = '';
      analysisTitle.textContent = '';
      analysisValue.textContent = 'SYSTEM STANDBY';
      analysisProcess.replaceChildren();
      setAnalysisOverlayVisible(true);
      return;
    }
    document.body.classList.remove('cold-idle');
    archiveCycleApplied = '';
    if (session?.kind === 'live_capture' && ['capturing', 'recording'].includes(session?.phase)) {
      sessionMode = false;
      await startCamera();
      setSource('live');
      sourceLabel.textContent = 'Live camera / observation active';
      return;
    }
    const playback = session?.playback;
    if (!session?.id || !playback?.url) return;
    if (session.createdAt && sessionCreatedAt !== session.createdAt) {
      sessionCreatedAt = session.createdAt;
      sessionMode = true;
      setSource('archive');
      archiveVideo.loop = true;
    }
    sessionMode = true;
    sourceLabel.textContent = playback.stage === 'raw'
      ? 'Current crystallisation / observation'
      : 'Current crystallisation / retained result';
    await window.syncMorphogenesisVideo?.(
      archiveVideo,
      session,
      stabilizedSourceFor(session.crystal, playback.url)
    );
  };

  setArchiveCutSources('ice_crystal_01');
  setArchiveCutEnabled(true);
  window.requestAnimationFrame(updateArchiveCut);
  window.addEventListener('morphogenesis-session', (event) => applySession(event.detail));
  window.addEventListener('morphogenesis-session-tick', (event) => applySession(event.detail));
  if (window.morphogenesisSession) applySession(window.morphogenesisSession);

  updateClock();
  applyPanelSizes();
  window.addEventListener('resize', applyPanelSizes);
  window.setInterval(updateClock, 1000);
  window.setInterval(renderAnalysisFrame, 100);
  pollAgent();
  window.setInterval(pollAgent, 1000);
  clearThermal();
  pollThermal();
  window.setInterval(pollThermal, 500);
  archiveVideo.play().catch(() => {});
  if (navigator.mediaDevices?.enumerateDevices) listCameras(localStorage.getItem(CAMERA_STORAGE_KEY) || '');
  const pageParameters = new URLSearchParams(window.location.search);
  if (pageParameters.get('startCamera') === '1') {
    startCamera(pageParameters.get('camera') || '');
  }
  navigator.mediaDevices?.addEventListener('devicechange', () => {
    listCameras(localStorage.getItem(CAMERA_STORAGE_KEY) || '');
  });
})();
