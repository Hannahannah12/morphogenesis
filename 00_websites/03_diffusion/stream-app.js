(() => {
  'use strict';

  const pageParameters = new URLSearchParams(window.location.search);
  const spectatorMode = pageParameters.get('spectator') === '1';
  const exhibitionEmbed = pageParameters.get('exhibitionEmbed') || '';
  if (exhibitionEmbed) document.body.dataset.exhibitionEmbed = exhibitionEmbed;
  const requestedMirrorRole = pageParameters.get('mirror') || (spectatorMode ? 'receiver' : 'primary');
  const primaryLeaseKey = 'morphogenesis.diffusion.primaryLease.v1';
  const primaryLeaseToken = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const primaryLeaseMs = 6500;
  const readPrimaryLease = () => {
    try { return JSON.parse(window.localStorage.getItem(primaryLeaseKey) || 'null'); }
    catch { return null; }
  };
  const claimPrimaryLease = () => {
    const now = Date.now();
    const current = readPrimaryLease();
    if (current?.token && current.token !== primaryLeaseToken && Number(current.expiresAt) > now) {
      return false;
    }
    window.localStorage.setItem(primaryLeaseKey, JSON.stringify({
      token: primaryLeaseToken,
      expiresAt: now + primaryLeaseMs
    }));
    return readPrimaryLease()?.token === primaryLeaseToken;
  };
  const mirrorRole = requestedMirrorRole === 'auto'
    ? (claimPrimaryLease() ? 'primary' : 'receiver')
    : requestedMirrorRole;
  document.body.dataset.resolvedMirrorRole = mirrorRole;
  const mirrorChannel = 'BroadcastChannel' in window
    ? new BroadcastChannel('morphogenesis-medium-diffusion-v1')
    : null;
  const workerHost = window.location.hostname || '127.0.0.1';
  const WORKER_HTTP = `http://${workerHost}:8091`;
  const WORKER_WS = `ws://${workerHost}:8091/ws`;
  const $ = (id) => document.getElementById(id);
  const archiveVideo = $('archive-video');
  const cameraVideo = $('camera-video');
  const cameraSelect = $('camera-select');
  const cameraButton = $('camera-button');
  const archiveButton = $('archive-button');
  const streamButton = $('stream-button');
  const promptInput = $('prompt-input');
  const canvas = $('capture-canvas');
  const context = canvas.getContext('2d', { alpha: false });
  const aiCanvas = $('ai-canvas');
  const aiContext = aiCanvas.getContext('2d', { alpha: false });
  const output = $('generated-frame');
  const backupVideo = $('diffusion-backup');
  const runtimeDot = $('runtime-dot');
  const runtimeLabel = $('runtime-label');
  const fpsLabel = $('fps-label');
  const sourceLabel = $('source-label');
  const diffusionRehearsalSource = $('diffusion-rehearsal-source');
  const diffusionTerminal = $('diffusion-terminal');
  const diffusionTerminalLog = $('diffusion-terminal-log');
  const diffusionTerminalSteps = [
    'Read crystallisation source · structural frame',
    'Connect StreamDiffusion · local GPU worker',
    'Apply structure guide · preserve formation topology',
    'Open output stream · imagination ready'
  ];

  const renderDiffusionRehearsal = async (session) => {
    const materialComplete = session?.kind === 'analysis_rehearsal'
      && session?.jobs?.material?.state === 'complete';
    // The terminal overlay belonged to the old sequential presentation. The
    // fixed Diffusion screen now starts once, exactly when Material completes.
    diffusionTerminal.classList.remove('visible');
    diffusionRehearsalSource.hidden = true;
    return materialComplete;
  };
  const sourceWindow = $('source-window');
  const sourceToggle = $('source-toggle');
  const notice = $('notice');
  const aiStatus = $('ai-status');
  const aiCountdown = $('ai-countdown');
  const aiToggle = $('ai-toggle');
  const imagineButton = $('imagine-button');
  const controlsPanel = $('controls-panel');
  const controlsToggle = $('controls-toggle');
  const thoughtStream = $('thought-stream') || document.querySelector('.thought-stream');
  const thoughtOutput = $('thought-output');
  const promptResult = $('prompt-result');
  const promptOutput = $('prompt-output');
  const aiIntervalInput = $('ai-interval');
  const aiIntervalValue = $('ai-interval-value');

  sourceToggle.addEventListener('click', () => {
    const collapsed = sourceWindow.classList.toggle('collapsed');
    sourceToggle.textContent = collapsed ? '+' : '\u2212';
    sourceToggle.setAttribute('aria-expanded', String(!collapsed));
    sourceToggle.setAttribute(
      'aria-label',
      collapsed ? 'Expand source video' : 'Collapse source video'
    );
  });
  const imaginationResizer = $('imagination-resizer');
  const diffusionStage = $('diffusion-stage');
  const debugPlaybackEvents = [];

  const IMAGINATION_WIDTH_KEY = 'morphogenesis.diffusion.imaginationWidth';
  const defaultImaginationWidth = 420;
  const imaginationWidthLimits = () => ({
    min: 300,
    max: Math.min(620, Math.max(320, window.innerWidth * 0.46))
  });
  const setImaginationWidth = (requestedWidth, remember = false) => {
    const limits = imaginationWidthLimits();
    const width = Math.round(Math.max(limits.min, Math.min(limits.max, requestedWidth)));
    diffusionStage.style.setProperty('--imagination-width', `${width}px`);
    imaginationResizer.setAttribute('aria-valuenow', String(width));
    imaginationResizer.setAttribute('aria-valuemax', String(Math.round(limits.max)));
    if (remember) window.localStorage.setItem(IMAGINATION_WIDTH_KEY, String(width));
    return width;
  };

  const storedImaginationWidth = Number(window.localStorage.getItem(IMAGINATION_WIDTH_KEY));
  setImaginationWidth(
    Number.isFinite(storedImaginationWidth) && storedImaginationWidth > 0
      ? storedImaginationWidth
      : defaultImaginationWidth
  );

  let resizingImagination = false;
  imaginationResizer.addEventListener('pointerdown', (event) => {
    if (window.matchMedia('(max-width: 820px)').matches) return;
    resizingImagination = true;
    imaginationResizer.classList.add('dragging');
    document.body.classList.add('resizing-imagination');
    imaginationResizer.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  });
  window.addEventListener('pointermove', (event) => {
    if (!resizingImagination) return;
    setImaginationWidth(window.innerWidth - event.clientX);
  });
  const finishImaginationResize = () => {
    if (!resizingImagination) return;
    resizingImagination = false;
    imaginationResizer.classList.remove('dragging');
    document.body.classList.remove('resizing-imagination');
    const width = parseFloat(
      getComputedStyle(diffusionStage).getPropertyValue('--imagination-width')
    );
    setImaginationWidth(width, true);
  };
  window.addEventListener('pointerup', finishImaginationResize);
  window.addEventListener('pointercancel', finishImaginationResize);
  imaginationResizer.addEventListener('dblclick', () => {
    setImaginationWidth(defaultImaginationWidth, true);
  });
  imaginationResizer.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home'].includes(event.key)) return;
    const current = parseFloat(
      getComputedStyle(diffusionStage).getPropertyValue('--imagination-width')
    );
    const next = event.key === 'Home'
      ? defaultImaginationWidth
      : current + (event.key === 'ArrowLeft' ? 16 : -16);
    setImaginationWidth(next, true);
    event.preventDefault();
  });
  window.addEventListener('resize', () => {
    const current = parseFloat(
      getComputedStyle(diffusionStage).getPropertyValue('--imagination-width')
    );
    setImaginationWidth(current);
  });

  if (new URLSearchParams(window.location.search).has('debugPlayback')) {
    const recordPlaybackEvent = (event) => {
      debugPlaybackEvents.push({
        type: event.type,
        currentTime: Number(archiveVideo.currentTime.toFixed(3)),
        duration: Number.isFinite(archiveVideo.duration)
          ? Number(archiveVideo.duration.toFixed(3))
          : null,
        readyState: archiveVideo.readyState,
        at: Date.now()
      });
      archiveVideo.dataset.playbackDebug = JSON.stringify(debugPlaybackEvents.slice(-40));
    };
    [
      'loadstart', 'loadedmetadata', 'emptied', 'seeking', 'seeked',
      'ended', 'abort', 'suspend'
    ].forEach((eventName) => archiveVideo.addEventListener(eventName, recordPlaybackEvent));
  }

  let cameraStream = null;
  let source = 'archive';
  let socket = null;
  let streaming = false;
  let framePending = false;
  let workerStatus = 'offline';
  let measuredFps = null;
  let currentObjectUrl = null;
  let aiConfigured = false;
  let aiEnabled = true;
  let aiBusy = false;
  let nextImaginationAt = null;
  let lastImagination = null;
  let lastFormationState = 'unknown';
  let typingRun = 0;
  let thoughtScrollFrame = 0;
  let sessionActive = false;
  let activeSessionId = '';
  let sessionRevision = 0;
  let sessionAutoStartRequested = false;
  let hasGeneratedFrame = false;
  let awaitingFirstGeneratedFrame = false;
  let activeSession = null;
  let backupUrl = '';
  let backupReady = false;
  let backupProbeAt = 0;
  let archiveImaginationSessionId = '';
  let archiveImaginationRetryAt = 0;
  let archiveImaginationCycleKey = '';
  let archiveImaginationSlots = new Set();
  let completedArchiveObservationKey = '';
  let recordingRequested = false;
  let recordingActive = false;
  let previousRecordingTime = null;
  let rehearsalImaginationKey = '';
  let rehearsalImaginationStartedAt = 0;
  let rehearsalImaginationPending = 0;
  let rehearsalImaginationSlots = new Set();
  let lastMirrorFrame = null;
  let mirrorStateTimer = 0;
  const AI_INTERVAL_KEY = 'morphogenesis.diffusion.aiIntervalSeconds.v2';
  const storedAiInterval = Number(window.localStorage.getItem(AI_INTERVAL_KEY));
  let imaginationInterval = (
    Number.isFinite(storedAiInterval) && storedAiInterval >= 15
      ? Math.min(180, storedAiInterval)
      : 90
  ) * 1000;
  aiIntervalInput.value = String(imaginationInterval / 1000);
  aiIntervalValue.value = `${Math.round(imaginationInterval / 1000)}s`;

  const currentObservationKey = () => [
    activeSessionId || 'standalone',
    activeSession?.crystal || sourceLabel.textContent || 'unknown',
    sessionRevision || 0
  ].join(':');

  const currentArchiveCycleKey = () => {
    if (activeSession?.kind !== 'archive_cycle') return '';
    const repeat = Math.max(1, Number(activeSession.archiveSequence?.repeat) || 1);
    const durationMs = Math.max(0, Number(activeSession.playback?.durationSeconds) || 0) * 1000;
    const repeatStartedAt = Number(activeSession.playback?.startedAtEpochMs) || 0;
    return [
      activeSession.crystal || 'archive',
      Math.round(repeatStartedAt - (repeat - 1) * durationMs)
    ].join(':');
  };

  const secondsUntilNextArchiveImagination = () => {
    if (activeSession?.kind !== 'archive_cycle' || archiveImaginationSlots.size >= 2) {
      return null;
    }
    if (archiveImaginationSlots.size === 0) return 0;
    const repeat = Math.max(1, Number(activeSession.archiveSequence?.repeat) || 1);
    const duration = Math.max(0, Number(activeSession.playback?.durationSeconds) || 0);
    const repeatStartedAt = Number(activeSession.playback?.startedAtEpochMs) || Date.now();
    const elapsed = Math.max(0, (Date.now() - repeatStartedAt) / 1000);
    return Math.max(0, (Math.max(0, 3 - repeat) * duration) - elapsed);
  };

  const compactCountdown = (seconds) => {
    const value = Math.max(0, Math.ceil(Number(seconds) || 0));
    const minutes = Math.floor(value / 60);
    const remainder = String(value % 60).padStart(2, '0');
    return `${String(minutes).padStart(2, '0')}:${remainder}`;
  };

  const followThoughtStream = () => {
    if (!thoughtStream) return;
    window.cancelAnimationFrame(thoughtScrollFrame);
    thoughtScrollFrame = window.requestAnimationFrame(() => {
      thoughtStream.scrollTop = thoughtStream.scrollHeight;
    });
  };

  const resetThoughtStream = () => {
    if (!thoughtStream) return;
    window.cancelAnimationFrame(thoughtScrollFrame);
    thoughtStream.scrollTop = 0;
  };

  if (thoughtStream) {
    new MutationObserver(followThoughtStream).observe(thoughtStream, {
      childList: true,
      characterData: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['hidden']
    });
  }

  const archiveTimelineIsComplete = () => {
    if (source !== 'archive') return false;
    const duration = Number(archiveVideo.duration);
    const currentTime = Number(archiveVideo.currentTime);
    return Number.isFinite(duration)
      && duration > 0
      && Number.isFinite(currentTime)
      && currentTime / duration >= 0.92;
  };

  const setNotice = (message, isError = false) => {
    notice.textContent = message;
    notice.style.color = isError ? 'var(--error)' : '';
  };

  const updateOutputMode = () => {
    const liveGenerated = (streaming || mirrorRole === 'receiver') && hasGeneratedFrame;
    // During a source/session change, keep the last generated still visible
    // until the first frame from the new source arrives. The recorded fallback
    // is reserved for a genuinely unavailable worker, not normal AI/model delay.
    const holdLiveTransition = awaitingFirstGeneratedFrame && workerStatus === 'ready';
    const useBackup = !liveGenerated && backupReady && !holdLiveTransition;
    output.hidden = useBackup;
    backupVideo.hidden = !useBackup;
    document.body.dataset.diffusionFallback = String(useBackup);
    if (useBackup) {
      runtimeLabel.textContent = 'Recorded diffusion / synchronized';
      fpsLabel.textContent = 'offline backup';
    }
  };

  const mirrorState = () => ({
    thought: thoughtOutput.textContent,
    thoughtClass: thoughtOutput.className,
    prompt: promptOutput.textContent,
    promptClass: promptOutput.className,
    promptHidden: promptResult.hidden,
    aiStatus: aiStatus.textContent,
    aiStatusClass: aiStatus.className,
    countdown: aiCountdown.textContent,
    promptValue: promptInput.value,
    fps: fpsLabel.textContent
  });

  const publishMirrorState = () => {
    if (mirrorRole !== 'primary' || !mirrorChannel) return;
    window.clearTimeout(mirrorStateTimer);
    mirrorStateTimer = window.setTimeout(() => {
      mirrorChannel.postMessage({ type: 'state', value: mirrorState() });
    }, 80);
  };

  const applyMirrorState = (state = {}) => {
    thoughtOutput.textContent = state.thought || '';
    thoughtOutput.className = state.thoughtClass || '';
    promptOutput.textContent = state.prompt || '';
    promptOutput.className = state.promptClass || '';
    promptResult.hidden = Boolean(state.promptHidden);
    aiStatus.textContent = state.aiStatus || 'Mirror / connected';
    aiStatus.className = state.aiStatusClass || 'ready';
    aiCountdown.textContent = state.countdown || '';
    if (state.promptValue) promptInput.value = state.promptValue;
    fpsLabel.textContent = state.fps || 'mirrored';
    followThoughtStream();
  };

  mirrorChannel?.addEventListener('message', (event) => {
    const message = event.data || {};
    if (mirrorRole === 'primary' && message.type === 'request') {
      mirrorChannel.postMessage({ type: 'state', value: mirrorState() });
      if (lastMirrorFrame) mirrorChannel.postMessage({ type: 'frame', blob: lastMirrorFrame });
      return;
    }
    if (mirrorRole !== 'receiver') return;
    if (message.type === 'state') {
      applyMirrorState(message.value);
      return;
    }
    if (message.type === 'frame' && message.blob instanceof Blob) {
      if (currentObjectUrl) URL.revokeObjectURL(currentObjectUrl);
      currentObjectUrl = URL.createObjectURL(message.blob);
      output.onload = () => {
        hasGeneratedFrame = true;
        output.dataset.generated = 'true';
        updateOutputMode();
      };
      output.src = currentObjectUrl;
    }
  });

  if (mirrorRole === 'primary') {
    [thoughtOutput, promptOutput, promptResult, aiStatus, aiCountdown].forEach((node) => {
      new MutationObserver(publishMirrorState).observe(node, {
        childList: true,
        characterData: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['hidden', 'class']
      });
    });
  }

  const probeBackup = async (force = false) => {
    if (!backupUrl || (!force && Date.now() < backupProbeAt)) return backupReady;
    backupProbeAt = Date.now() + 5000;
    try {
      const response = await fetch(backupUrl, {
        method: 'HEAD',
        cache: 'no-store'
      });
      if (!response.ok) throw new Error('backup not found');
      const absolute = new URL(backupUrl, window.location.origin).href;
      if (backupVideo.src !== absolute) {
        backupVideo.src = absolute;
        backupVideo.load();
      }
      backupReady = true;
      updateOutputMode();
      return true;
    } catch (_) {
      backupReady = false;
      updateOutputMode();
      return false;
    }
  };

  const recordingDuration = () => {
    const sessionDuration = Number(activeSession?.playback?.durationSeconds);
    if (Number.isFinite(sessionDuration) && sessionDuration > 0) return sessionDuration;
    const videoDuration = Number(archiveVideo.duration);
    return Number.isFinite(videoDuration) && videoDuration > 0 ? videoDuration : 0;
  };

  const requestRecordingStart = () => {
    const durationSeconds = recordingDuration();
    if (!activeSession?.crystal
      || durationSeconds <= 0
      || recordingRequested
      || backupReady
      || socket?.readyState !== WebSocket.OPEN) return;
    recordingRequested = true;
    socket.send(JSON.stringify({
      type: 'recording_start',
      crystal: activeSession.crystal,
      durationSeconds
    }));
  };

  const observeRecordingTimeline = () => {
    if (source !== 'archive'
      || !sessionActive
      || backupReady
      || socket?.readyState !== WebSocket.OPEN) return;
    const duration = recordingDuration();
    if (duration <= 0) return;
    const current = archiveVideo.currentTime;
    const wrapped = previousRecordingTime !== null
      && previousRecordingTime - current > duration * 0.5;
    if (!recordingRequested && (current < 0.65 || wrapped)) {
      requestRecordingStart();
    } else if (recordingActive && wrapped) {
      recordingActive = false;
      socket.send(JSON.stringify({ type: 'recording_stop' }));
      setNotice('Encoding the synchronized Diffusion backup.');
    }
    previousRecordingTime = current;
  };

  const setWorkerState = (health) => {
    workerStatus = health?.status || 'offline';
    runtimeDot.className = 'state-dot';
    if (health?.ready) {
      runtimeDot.classList.add('ready');
      runtimeLabel.textContent = health.transformationProfile === 'structural-association'
        ? 'GPU / structural association'
        : 'GPU service / ready';
      if (!streaming && !aiBusy && !aiStatus.classList.contains('error')) {
        setNotice('GPU model ready. Choose a source and start diffusion.');
      }
    } else if (health?.status === 'loading_model' || health?.status === 'starting') {
      runtimeLabel.textContent = 'GPU service / loading model';
      setNotice('Loading SD-Turbo into the GPU. This is slower on first start.');
    } else if (health?.status === 'error') {
      runtimeDot.classList.add('error');
      runtimeLabel.textContent = 'GPU service / error';
      setNotice(health.error || 'The GPU worker reported an error.', true);
    } else {
      runtimeDot.classList.add('error');
      runtimeLabel.textContent = 'GPU service / not running';
      setNotice('Start Morphogenesis System to run the GPU worker.', true);
    }
    updateOutputMode();
    if (!streaming && health?.fps) fpsLabel.textContent = `${health.fps.toFixed(1)} fps`;
  };

  const checkWorker = async () => {
    try {
      const response = await fetch(`${WORKER_HTTP}/health`, { cache: 'no-store' });
      if (!response.ok) throw new Error('Worker health failed');
      setWorkerState(await response.json());
    } catch (_) {
      setWorkerState(null);
    }
  };

  const stopCamera = () => {
    cameraStream?.getTracks().forEach((track) => track.stop());
    cameraStream = null;
    cameraVideo.srcObject = null;
  };

  const useArchive = async () => {
    stopCamera();
    source = 'archive';
    cameraVideo.hidden = true;
    archiveVideo.hidden = false;
    archiveButton.classList.add('active');
    cameraButton.classList.remove('active');
    sourceLabel.textContent = 'Source / ice_crystal_01 archive';
    await archiveVideo.play().catch(() => {});
  };

  const listCameras = async () => {
    const devices = (await navigator.mediaDevices.enumerateDevices())
      .filter((device) => device.kind === 'videoinput');
    cameraSelect.replaceChildren(new Option('Choose USB camera', ''));
    devices.forEach((device, index) => {
      cameraSelect.add(new Option(device.label || `Camera ${index + 1}`, device.deviceId));
    });
    const preferred = devices.find((device) => /uvc|usb|external|capture/i.test(device.label));
    cameraSelect.hidden = devices.length === 0;
    if (preferred) cameraSelect.value = preferred.deviceId;
    return preferred;
  };

  const openCamera = async (deviceId) => {
    if (!deviceId) {
      setNotice('Choose the USB/UVC camera from the list. The built-in camera is not selected automatically.', true);
      return;
    }
    stopCamera();
    try {
      cameraStream = await navigator.mediaDevices.getUserMedia({
        video: { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false
      });
      cameraVideo.srcObject = cameraStream;
      await cameraVideo.play();
      source = 'camera';
      cameraVideo.hidden = false;
      archiveVideo.hidden = true;
      archiveButton.classList.remove('active');
      cameraButton.classList.add('active');
      const selected = cameraSelect.options[cameraSelect.selectedIndex]?.text || 'USB camera';
      sourceLabel.textContent = `Source / ${selected}`;
      setNotice('USB camera connected.');
    } catch (error) {
      setNotice(`Camera could not open: ${error.message}`, true);
      await useArchive();
    }
  };

  const findUsbCamera = async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setNotice('This browser does not provide camera access.', true);
      return;
    }
    cameraButton.disabled = true;
    try {
      const permissionStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      permissionStream.getTracks().forEach((track) => track.stop());
      const preferred = await listCameras();
      if (preferred) await openCamera(preferred.deviceId);
      else setNotice('No camera labelled USB/UVC was found. Choose the correct device manually.', true);
    } catch (error) {
      setNotice(`Camera permission failed: ${error.message}`, true);
    } finally {
      cameraButton.disabled = false;
    }
  };

  const activeVideo = () => source === 'camera' ? cameraVideo : archiveVideo;

  const drawVideoFrame = (video, targetContext, targetCanvas) => {
    const isAIReading = targetCanvas === aiCanvas;
    // The plate's two screw holes sit in the top border of several recordings.
    // Crop a matched 6% from the total width and height (top + both sides) so
    // the ROI keeps its native aspect and the hardware does not become a visual
    // anchor for either the AI reading or StreamDiffusion.
    // The private AI reading crops a further 8% in both dimensions, enlarging
    // pale crystal ridges without exposing this diagnostic view on the page.
    const roiSide = video.videoWidth * (isAIReading ? 0.07 : 0.03);
    const roiTop = video.videoHeight * (isAIReading ? 0.10 : 0.06);
    const roiBottom = video.videoHeight * (isAIReading ? 0.04 : 0);
    const roiWidth = video.videoWidth - roiSide * 2;
    const roiHeight = video.videoHeight - roiTop - roiBottom;
    const sourceAspect = roiWidth / roiHeight;
    const targetAspect = targetCanvas.width / targetCanvas.height;
    let sx = roiSide;
    let sy = roiTop;
    let sourceWidth = roiWidth;
    let sourceHeight = roiHeight;
    if (sourceAspect > targetAspect) {
      sourceWidth = roiHeight * targetAspect;
      sx = roiSide + (roiWidth - sourceWidth) / 2;
    } else if (sourceAspect < targetAspect) {
      sourceHeight = roiWidth / targetAspect;
      sy = roiTop + (roiHeight - sourceHeight) / 2;
    }
    targetContext.save();
    // Reduce literal camera colour but retain enough context to keep the
    // generated palette connected to the observed material.
    targetContext.filter = isAIReading
      ? 'contrast(1.9) brightness(0.72) saturate(0.68)'
      : 'contrast(1.42) brightness(0.88) saturate(0.38)';
    targetContext.drawImage(
      video,
      sx, sy, sourceWidth, sourceHeight,
      0, 0, targetCanvas.width, targetCanvas.height
    );
    targetContext.restore();
  };

  const setAIStatus = (label, state = '') => {
    aiStatus.textContent = label;
    aiStatus.className = state;
  };

  const checkAI = async () => {
    try {
      const response = await fetch('/api/agent/health', { cache: 'no-store' });
      if (!response.ok) throw new Error('Agent health unavailable');
      const health = await response.json();
      aiConfigured = Boolean(health.creativeAI?.configured);
      imagineButton.disabled = !aiConfigured || aiBusy;
      if (!aiConfigured) {
        setAIStatus('OpenAI / not connected', 'error');
        aiCountdown.textContent = 'manual prompt';
      } else if (/quota|billing|rate limit|429/i.test(health.creativeAI?.lastError || '')) {
        aiEnabled = false;
        aiToggle.setAttribute('aria-pressed', 'false');
        aiToggle.textContent = 'AI / off';
        aiToggle.classList.remove('active');
        setAIStatus('OpenAI / quota unavailable', 'error');
        aiCountdown.textContent = 'add API credit';
      } else if (!aiBusy) {
        setAIStatus(
          completedArchiveObservationKey === currentObservationKey()
            ? 'OpenAI / crystallisation complete'
            : `OpenAI / ${health.creativeAI.model}`,
          'ready'
        );
      }
    } catch (_) {
      aiConfigured = false;
      imagineButton.disabled = true;
      setAIStatus('Agent / unavailable', 'error');
    }
  };

  const waitForMediaEvent = (video, eventName, timeout = 9000) => new Promise((resolve, reject) => {
    let timer = null;
    const cleanup = () => {
      video.removeEventListener(eventName, onReady);
      video.removeEventListener('error', onError);
      if (timer) window.clearTimeout(timer);
    };
    const onReady = () => {
      cleanup();
      resolve();
    };
    const onError = () => {
      cleanup();
      reject(new Error('The source timeline could not be loaded.'));
    };
    video.addEventListener(eventName, onReady, { once: true });
    video.addEventListener('error', onError, { once: true });
    timer = window.setTimeout(() => {
      cleanup();
      reject(new Error(`Timed out while waiting for the source ${eventName}.`));
    }, timeout);
  });

  const seekVideo = async (video, targetTime) => {
    const safeTime = Math.max(0, Math.min(targetTime, Math.max(0, video.duration - 0.04)));
    if (Math.abs(video.currentTime - safeTime) < 0.025
      && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) return;
    const ready = waitForMediaEvent(video, 'seeked');
    video.currentTime = safeTime;
    await ready;
    const wasPaused = video.paused;
    let playedForDecode = false;
    try {
      await video.play();
      playedForDecode = true;
    } catch (_) {
      // A timed decode fallback below still prevents the capture from hanging.
    }
    if (typeof video.requestVideoFrameCallback === 'function') {
      await new Promise((resolve) => {
        let settled = false;
        const finish = () => {
          if (settled) return;
          settled = true;
          resolve();
        };
        video.requestVideoFrameCallback(finish);
        // Paused diagnostic videos do not consistently emit another presented
        // frame after `seeked`; never let that browser quirk block AI reading.
        window.setTimeout(finish, 420);
      });
    } else {
      await new Promise((resolve) => window.setTimeout(resolve, 180));
    }
    if (wasPaused && playedForDecode) video.pause();
  };

  const representativeFormationFraction = (duration) => {
    const detection = activeSession?.detection || {};
    const trimStart = Number(detection.trimStartSeconds);
    const completion = Number(detection.completionSeconds);
    if (Number.isFinite(trimStart) && Number.isFinite(completion) && completion > trimStart) {
      // Read shortly before the plateau rather than the post-completion hold.
      return Math.max(0.58, Math.min(0.9, (completion - trimStart - 1) / duration));
    }
    return 0.78;
  };

  const snapshotArchiveFormationForAI = async () => {
    const sourceUrl = archiveVideo.currentSrc || archiveVideo.getAttribute('src');
    if (!sourceUrl) throw new Error('The formation clip has no video source.');

    const formationVideo = document.createElement('video');
    formationVideo.muted = true;
    formationVideo.playsInline = true;
    formationVideo.preload = 'auto';
    Object.assign(formationVideo.style, {
      position: 'fixed',
      left: '-10000px',
      top: '0',
      width: '640px',
      height: '640px',
      opacity: '0.001',
      pointerEvents: 'none'
    });
    document.body.appendChild(formationVideo);
    formationVideo.src = sourceUrl;
    formationVideo.load();
    if (formationVideo.readyState < HTMLMediaElement.HAVE_METADATA) {
      await waitForMediaEvent(formationVideo, 'loadedmetadata');
    }
    const duration = Number(formationVideo.duration);
    if (!Number.isFinite(duration) || duration <= 0) {
      throw new Error('The formation clip duration is unavailable.');
    }

    const sampleFraction = representativeFormationFraction(duration);
    await seekVideo(formationVideo, duration * sampleFraction);
    drawVideoFrame(formationVideo, aiContext, aiCanvas);
    formationVideo.removeAttribute('src');
    formationVideo.load();
    formationVideo.remove();
    return {
      image: aiCanvas.toDataURL('image/jpeg', 0.82),
      sequence: 'enlarged-high-contrast-formation-frame',
      sampleFraction
    };
  };

  const snapshotLiveFormationForAI = async () => {
    const video = activeVideo();
    if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !video.videoWidth) {
      throw new Error('The live source frame is not ready yet.');
    }
    drawVideoFrame(video, aiContext, aiCanvas);
    return {
      image: aiCanvas.toDataURL('image/jpeg', 0.82),
      sequence: 'enlarged-high-contrast-live-frame'
    };
  };

  const snapshotForAI = () => source === 'archive'
    ? snapshotArchiveFormationForAI()
    : snapshotLiveFormationForAI();

  if (new URLSearchParams(window.location.search).has('debugTimeline')) {
    const revealDebugFrame = async () => {
      const snapshot = await snapshotForAI();
      aiCanvas.hidden = false;
      Object.assign(aiCanvas.style, {
        position: 'fixed',
        inset: '0',
        width: 'min(100vw, 100vh)',
        height: 'min(100vw, 100vh)',
        zIndex: '9999'
      });
      return { sequence: snapshot.sequence, bytes: snapshot.image.length };
    };
    window.setTimeout(() => revealDebugFrame().catch(console.error), 1200);
  }

  const typeText = async (node, text, run, pace = 15) => {
    if (node === thoughtOutput) resetThoughtStream();
    node.textContent = '';
    node.classList.add('typing');
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      node.textContent = text;
      node.classList.remove('typing');
      return;
    }
    for (let index = 0; index < text.length; index += 1) {
      if (run !== typingRun) return;
      node.textContent += text[index];
      const character = text[index];
      const pause = /[.!?]/.test(character) ? 180 : character === '\n' ? 240 : pace;
      await new Promise((resolve) => window.setTimeout(resolve, pause));
    }
    node.classList.remove('typing');
  };

  const revealTrace = async (trace) => {
    const run = ++typingRun;
    const formationThought = {
      preformation: 'I am observing a thin film of water before visible ice formation, so I should not force an association yet.',
      emerging: 'I am observing water beginning to crystallise into ice; a local structure is organising, so the association should remain restrained.',
      active: 'I am observing water crystallising into an organised ice structure that can support a wider association.'
    }[trace.formationState] || 'The degree of formation remains uncertain.';
    const associationThought = trace.imaginationMode === 'hold'
      ? 'I will wait for a visible structure before extending the image.'
      : `I am searching within ${String(trace.associationField || 'an open morphological field').toLowerCase()}, looking for the same rhythm rather than the same material.`;
    const thought = [
      formationThought,
      trace.observation,
      trace.curiosity,
      associationThought,
      trace.transformation
    ].filter(Boolean).join('\n\n');

    promptResult.hidden = true;
    promptOutput.textContent = '';
    await typeText(thoughtOutput, thought, run, 28);
    if (run !== typingRun) return;
    if (trace.imaginationMode === 'hold') return;
    await new Promise((resolve) => window.setTimeout(resolve, 420));
    promptResult.hidden = false;
    await typeText(promptOutput, trace.prompt, run, 22);
  };

  const scheduleNextImagination = () => {
    const observationComplete = (
      source === 'archive'
      && completedArchiveObservationKey === currentObservationKey()
    );
    if (['archive_cycle', 'analysis_rehearsal'].includes(activeSession?.kind)) {
      nextImaginationAt = null;
      return;
    }
    const interval = imaginationInterval;
    nextImaginationAt = aiEnabled
      && aiConfigured
      && streaming
      && !observationComplete
      ? Date.now() + interval
      : null;
  };

  const imagine = async () => {
    if (aiBusy || !aiConfigured) return;
    aiBusy = true;
    imagineButton.disabled = true;
    nextImaginationAt = null;
    setAIStatus('OpenAI / examining formation structure', 'ready');
    aiCountdown.textContent = 'imagining';
    typingRun += 1;
    thoughtOutput.classList.add('typing');
    resetThoughtStream();
    thoughtOutput.textContent = 'Magnifying the emerged structure…';
    promptResult.hidden = true;
    try {
      const snapshot = await snapshotForAI();
      const response = await fetch('/api/agent/imagine-prompt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image: snapshot.image,
          sequence: snapshot.sequence,
          source: source === 'camera'
            ? 'live macro camera observing water crystallising into ice'
            : 'recorded macro video of water crystallising into ice',
          crystal: activeSession?.crystal || sourceLabel.textContent || 'unlabelled crystal',
          observationId: [
            activeSession?.crystal || 'standalone',
            activeSession?.createdAt || 'recorded',
            activeSession?.playback?.revision || 0
          ].join(':'),
          previous: lastImagination
        })
      });
      const trace = await response.json();
      if (!response.ok) throw new Error(trace.error || 'OpenAI request failed');
      setAIStatus('OpenAI / unfolding association', 'ready');
      lastFormationState = trace.formationState || 'unknown';
      await revealTrace(trace);
      lastImagination = trace;
      if (trace.imaginationMode === 'hold') {
        setAIStatus('OpenAI / waiting for visible formation', 'ready');
        setNotice('No visible formation yet. The current diffusion prompt is held; observing again in 15 seconds.');
      } else {
        promptInput.value = trace.prompt;
        if (socket?.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: 'prompt', value: trace.prompt }));
        }
        setAIStatus(
          trace.imaginationMode === 'subtle'
            ? 'OpenAI / early formation, subtle association'
            : 'OpenAI / imagination complete',
          'ready'
        );
        setNotice(
          trace.imaginationMode === 'subtle'
            ? 'Early structure detected. A restrained association entered the stream.'
            : 'A new association has entered the diffusion stream.'
        );
      }
    } catch (error) {
      setAIStatus('OpenAI / reconnecting', 'error');
      typingRun += 1;
      thoughtOutput.classList.remove('typing');
      resetThoughtStream();
      thoughtOutput.textContent = 'The current observation is being held while the imagination connection recovers.';
      promptResult.hidden = true;
      setNotice('OpenAI imagination is temporarily reconnecting; the current generated view will continue.', true);
      if (/quota|billing|rate limit|429/i.test(error.message)) {
        aiEnabled = false;
        aiToggle.setAttribute('aria-pressed', 'false');
        aiToggle.textContent = 'AI / off';
        aiToggle.classList.remove('active');
      }
    } finally {
      aiBusy = false;
      imagineButton.disabled = !aiConfigured;
      scheduleNextImagination();
    }
  };

  const captureFrame = () => {
    if (!streaming || framePending || socket?.readyState !== WebSocket.OPEN) return;
    const video = activeVideo();
    if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !video.videoWidth) {
      window.setTimeout(captureFrame, 100);
      return;
    }
    drawVideoFrame(video, context, canvas);
    framePending = true;
    canvas.toBlob((blob) => {
      if (!blob || socket?.readyState !== WebSocket.OPEN) {
        framePending = false;
        return;
      }
      socket.send(blob);
    }, 'image/jpeg', 0.82);
  };

  const stopDiffusion = () => {
    streaming = false;
    awaitingFirstGeneratedFrame = false;
    framePending = false;
    socket?.close();
    socket = null;
    streamButton.textContent = 'Start';
    streamButton.classList.add('primary');
    nextImaginationAt = null;
    recordingRequested = false;
    recordingActive = false;
    previousRecordingTime = null;
    updateOutputMode();
    setNotice(workerStatus === 'ready' ? 'Diffusion paused. Source video remains active.' : 'GPU worker unavailable.');
  };

  const observeArchiveOnce = () => {
    const observationKey = currentObservationKey();
    const cycleKey = currentArchiveCycleKey();
    if (cycleKey && archiveImaginationCycleKey !== cycleKey) {
      archiveImaginationCycleKey = cycleKey;
      archiveImaginationSlots = new Set();
      archiveImaginationSessionId = '';
    }
    const repeat = Math.max(1, Number(activeSession?.archiveSequence?.repeat) || 1);
    const slot = repeat >= 3 ? 2 : 1;
    const requestKey = `${cycleKey}:association-${slot}`;
    if (activeSession?.kind !== 'archive_cycle'
      || !backupReady
      || !aiEnabled
      || !aiConfigured
      || aiBusy
      || completedArchiveObservationKey === observationKey
      || archiveImaginationSlots.has(slot)
      || archiveImaginationSessionId === requestKey
      || Date.now() < archiveImaginationRetryAt) return;
    const requestedSessionId = requestKey;
    archiveImaginationSessionId = requestedSessionId;
    window.setTimeout(async () => {
      if (`${currentArchiveCycleKey()}:association-${slot}` !== requestedSessionId) return;
      const previousImagination = lastImagination;
      await imagine();
      if (lastImagination !== previousImagination) {
        archiveImaginationSlots.add(slot);
        archiveImaginationSessionId = '';
      } else if (archiveImaginationSessionId === requestedSessionId) {
        archiveImaginationSessionId = '';
        archiveImaginationRetryAt = Date.now() + 15000;
      }
    }, 900);
  };

  const observeRehearsalDiffusion = () => {
    if (activeSession?.kind !== 'analysis_rehearsal'
      || activeSession?.jobs?.material?.state !== 'complete') return;
    const key = `${activeSession.id}:${activeSession.crystal}`;
    if (rehearsalImaginationKey !== key) {
      rehearsalImaginationKey = key;
      rehearsalImaginationStartedAt = Date.now();
      rehearsalImaginationPending = 0;
      rehearsalImaginationSlots = new Set();
      completedArchiveObservationKey = '';
    }
    const elapsed = Math.max(0, (Date.now() - rehearsalImaginationStartedAt) / 1000);
    // Each rehearsal reserves two complete OpenAI reading/typing windows.
    // The GPU stream is pre-warmed during diffusion_terminal, so the first
    // association can begin almost immediately after the terminal clears.
    const slot = elapsed >= 60 ? 2 : elapsed >= 4 ? 1 : 0;
    if (!slot
      || rehearsalImaginationSlots.has(slot)
      || rehearsalImaginationPending === slot
      || !aiEnabled
      || !aiConfigured
      || aiBusy
      || (!streaming && !backupReady)) return;
    rehearsalImaginationPending = slot;
    const previousImagination = lastImagination;
    imagine().finally(() => {
      // A rehearsal slot is an attempt, not an open-ended retry window. If the
      // network is unavailable, wait for the second planned slot instead of
      // hammering the Agent every session tick.
      rehearsalImaginationSlots.add(slot);
      if (rehearsalImaginationPending === slot) rehearsalImaginationPending = 0;
    });
  };

  const startDiffusion = async () => {
    if (streaming) {
      stopDiffusion();
      return;
    }
    await checkWorker();
    if (workerStatus !== 'ready') {
      setNotice('The GPU worker is not ready yet.', true);
      return;
    }

    awaitingFirstGeneratedFrame = true;
    updateOutputMode();
    socket = new WebSocket(WORKER_WS);
    socket.binaryType = 'blob';
    socket.addEventListener('open', () => {
      streaming = true;
      socket.send(JSON.stringify({ type: 'prompt', value: promptInput.value }));
      streamButton.textContent = 'Stop';
      streamButton.classList.remove('primary');
      setNotice('StreamDiffusion connected. Priming the first generated frame…');
      previousRecordingTime = archiveVideo.currentTime;
      if (archiveVideo.currentTime < 0.65) requestRecordingStart();
      captureFrame();
      scheduleNextImagination();
      if (aiEnabled && aiConfigured && !lastImagination
        && !['archive_cycle', 'analysis_rehearsal'].includes(activeSession?.kind)) {
        window.setTimeout(imagine, 1800);
      }
    });
    socket.addEventListener('message', (event) => {
      if (typeof event.data === 'string') {
        const message = JSON.parse(event.data);
        if (message.type === 'frame') {
          measuredFps = message.fps;
          fpsLabel.textContent = measuredFps ? `${measuredFps.toFixed(1)} fps` : '— fps';
        } else if (message.type === 'error') {
          setNotice(message.message || 'Generation failed.', true);
          framePending = false;
        } else if (message.type === 'recording_started') {
          recordingActive = true;
          setNotice(`Recording synchronized Diffusion backup / ${message.crystal}`);
        } else if (message.type === 'recording_busy') {
          recordingRequested = false;
          recordingActive = false;
          setNotice('Another exhibition page is recording this Diffusion backup.');
        } else if (message.type === 'recording_ready') {
          recordingRequested = false;
          recordingActive = false;
          if (message.url) backupUrl = message.url;
          probeBackup(true);
          setNotice(message.existing
            ? 'Synchronized Diffusion backup is already available.'
            : 'Synchronized Diffusion backup saved.');
        }
        return;
      }
      if (currentObjectUrl) URL.revokeObjectURL(currentObjectUrl);
      lastMirrorFrame = event.data;
      if (mirrorRole === 'primary') {
        mirrorChannel?.postMessage({ type: 'frame', blob: event.data });
      }
      currentObjectUrl = URL.createObjectURL(event.data);
      output.onload = () => {
        hasGeneratedFrame = true;
        awaitingFirstGeneratedFrame = false;
        output.dataset.generated = 'true';
        framePending = false;
        updateOutputMode();
        observeRecordingTimeline();
        setNotice(`Live generation / ${source === 'camera' ? 'USB camera' : 'archive video'}`);
        // Exhibition-safe pacing: leaving a short gap between GPU frames keeps
        // the Live video and both display outputs responsive on one laptop.
        window.setTimeout(captureFrame, 520);
      };
      output.src = currentObjectUrl;
    });
    socket.addEventListener('close', () => {
      if (streaming) setNotice('StreamDiffusion connection closed.', true);
      streaming = false;
      framePending = false;
      hasGeneratedFrame = false;
      awaitingFirstGeneratedFrame = false;
      output.dataset.generated = 'false';
      sessionAutoStartRequested = false;
      nextImaginationAt = null;
      streamButton.textContent = 'Start';
      streamButton.classList.add('primary');
      recordingRequested = false;
      recordingActive = false;
      previousRecordingTime = null;
      updateOutputMode();
    });
    socket.addEventListener('error', () => setNotice('Could not connect to GPU worker on port 8091.', true));
  };

  promptInput.addEventListener('change', () => {
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'prompt', value: promptInput.value }));
      setNotice('Prompt updated for the next generated frame.');
    }
  });
  aiToggle.addEventListener('click', () => {
    aiEnabled = !aiEnabled;
    aiToggle.setAttribute('aria-pressed', String(aiEnabled));
    aiToggle.textContent = `AI / ${aiEnabled ? 'on' : 'off'}`;
    aiToggle.classList.toggle('active', aiEnabled);
    scheduleNextImagination();
  });
  controlsToggle.addEventListener('click', () => {
    const collapsed = controlsPanel.classList.toggle('collapsed');
    controlsToggle.setAttribute('aria-expanded', String(!collapsed));
    controlsToggle.setAttribute('aria-label', collapsed ? 'Expand controls' : 'Collapse controls');
    controlsToggle.textContent = collapsed ? '+' : '−';
  });
  imagineButton.addEventListener('click', imagine);
  archiveButton.addEventListener('click', useArchive);
  cameraButton.addEventListener('click', findUsbCamera);
  cameraSelect.addEventListener('change', () => openCamera(cameraSelect.value));
  streamButton.addEventListener('click', startDiffusion);
  aiIntervalInput.addEventListener('input', () => {
    imaginationInterval = Number(aiIntervalInput.value) * 1000;
    aiIntervalValue.value = activeSession?.kind === 'archive_cycle'
      ? '2×'
      : `${aiIntervalInput.value}s`;
    window.localStorage.setItem(AI_INTERVAL_KEY, aiIntervalInput.value);
    scheduleNextImagination();
  });
  navigator.mediaDevices?.addEventListener('devicechange', () => listCameras().catch(() => {}));
  window.addEventListener('pagehide', () => {
    stopDiffusion();
    stopCamera();
    mirrorChannel?.close();
    if (requestedMirrorRole === 'auto' && readPrimaryLease()?.token === primaryLeaseToken) {
      window.localStorage.removeItem(primaryLeaseKey);
    }
  });

  window.getMorphogenesisPageDetails = () => ({
    workerConnected: workerStatus === 'ready',
    workerStatus,
    source,
    cameraActive: Boolean(cameraStream),
    streaming,
    // Older running Agent instances understand this field as "a valid 03
    // visual is available"; include the synchronized backup for hot upgrades.
    hasGeneratedFrame: hasGeneratedFrame || !backupVideo.hidden,
    backupReady,
    backupActive: !backupVideo.hidden,
    recordingBackup: recordingActive,
    inputEnhancement: 'plate-roi-restrained-chroma-structure-contrast-1.42',
    aiObservation: 'enlarged-high-contrast-formation-frame',
    diffusionStructureGuide: 'temporal-formation-front-masked-v4',
    fps: measuredFps,
    creativeAI: aiConfigured,
    imaginationEnabled: aiEnabled,
    imaginationBusy: aiBusy,
    formationState: lastFormationState,
    sessionId: activeSessionId,
    sessionRevision
  });

  const applySession = async (session) => {
    const playback = session?.playback;
    if (!playback?.url) return;
    if (session.kind === 'analysis_rehearsal') {
      const rehearsalActive = await renderDiffusionRehearsal(session);
      if (!rehearsalActive) return;
    } else {
      diffusionTerminal.classList.remove('visible');
      diffusionRehearsalSource.hidden = true;
    }
    activeSessionId = session.id || '';
    activeSession = session;
    if (mirrorRole === 'receiver') {
      const receiverBackupUrl = session?.jobs?.diffusion?.recordingUrl
        || session?.jobs?.diffusion?.optionalRecordingUrl
        || (session?.crystal
          ? `/05_shared_data/exhibition/${session.crystal}/03_diffusion_imagination/diffusion_capture.mp4`
          : '');
      if (receiverBackupUrl && backupUrl !== receiverBackupUrl) {
        backupUrl = receiverBackupUrl;
        backupReady = false;
        backupProbeAt = 0;
        await probeBackup(true);
      }
      source = 'mirror';
      sourceLabel.textContent = `Mirror / ${session.crystal?.replaceAll('_', ' ') || 'current crystal'}`;
      archiveVideo.pause();
      archiveVideo.hidden = true;
      cameraVideo.hidden = true;
      if (backupReady) {
        await window.syncMorphogenesisVideo?.(
          backupVideo,
          session,
          backupUrl,
          { timeline: 'seconds' }
        );
      }
      updateOutputMode();
      return;
    }
    if (session.kind === 'archive_cycle' && session.runnerActive === false) {
      if (streaming) stopDiffusion();
      archiveVideo.pause();
      backupVideo.pause();
      nextImaginationAt = null;
      setAIStatus('System / standby', 'ready');
      aiCountdown.textContent = 'press Start in Control Room';
      return;
    }
    aiIntervalValue.value = session.kind === 'archive_cycle'
      ? '2×'
      : `${Math.round(imaginationInterval / 1000)}s`;
    const sessionBackupUrl = session?.jobs?.diffusion?.recordingUrl
      || session?.jobs?.diffusion?.optionalRecordingUrl
      || (session?.crystal
        ? `/05_shared_data/exhibition/${session.crystal}/03_diffusion_imagination/diffusion_capture.mp4`
        : '')
      || '';
    if (sessionBackupUrl && backupUrl !== sessionBackupUrl) {
      backupUrl = sessionBackupUrl;
      backupReady = false;
      backupProbeAt = 0;
      probeBackup(true);
    }
    if (!sessionActive) {
      sessionActive = true;
      stopCamera();
      source = 'archive';
      cameraVideo.hidden = true;
      archiveVideo.hidden = false;
      archiveVideo.loop = true;
      archiveButton.classList.add('active');
      cameraButton.classList.remove('active');
    }
    if (sessionRevision !== playback.revision) {
      sessionRevision = playback.revision;
      sessionAutoStartRequested = false;
      hasGeneratedFrame = false;
      awaitingFirstGeneratedFrame = workerStatus === 'ready';
      output.dataset.generated = 'false';
      sourceLabel.textContent = session.kind === 'archive_cycle'
        ? 'Archive source'
        : playback.stage === 'raw'
          ? `Shared source / ${session.crystal.replaceAll('_', ' ')}`
          : `Formation clip / ${session.crystal.replaceAll('_', ' ')}`;
      setNotice(session.kind === 'archive_cycle'
        ? 'Connecting live diffusion to the archive source.'
        : playback.stage === 'raw'
          ? 'Watching the same camera timeline as 01 and 02.'
          : 'Formation detected. Diffusion is receiving the two-second pre-roll clip.');
    }
    await window.syncMorphogenesisVideo?.(archiveVideo, session, playback.url);
    if (backupReady) {
      // Keep the primary main display on the same real-seconds clock as the
      // medium receivers. Using the default normalized timeline here made the
      // same saved Diffusion result land on different frames across screens.
      await window.syncMorphogenesisVideo?.(
        backupVideo,
        session,
        backupUrl,
        { timeline: 'seconds' }
      );
    } else {
      probeBackup();
    }
    updateOutputMode();
    const observationKey = currentObservationKey();
    if (session.kind === 'archive_cycle' && archiveTimelineIsComplete()) {
      completedArchiveObservationKey = observationKey;
      nextImaginationAt = null;
      if (!aiBusy) {
        setAIStatus('OpenAI / crystallisation complete', 'ready');
        aiCountdown.textContent = 'holding final association';
      }
    }
    observeArchiveOnce();
    observeRehearsalDiffusion();
    if (!spectatorMode
      && !sessionAutoStartRequested
      && session?.jobs?.material?.state === 'complete'
      && workerStatus === 'ready'
      && !streaming) {
      sessionAutoStartRequested = true;
      startDiffusion().catch(() => {
        sessionAutoStartRequested = false;
      });
    }
  };

  window.addEventListener('morphogenesis-session', (event) => applySession(event.detail));
  window.addEventListener('morphogenesis-session-tick', (event) => applySession(event.detail));

  window.setInterval(() => {
    if (nextImaginationAt && Date.now() >= nextImaginationAt) {
      imagine();
      return;
    }
    if (nextImaginationAt) {
      aiCountdown.textContent = `next / ${Math.max(0, Math.ceil((nextImaginationAt - Date.now()) / 1000))}s`;
    } else if (aiBusy) {
      aiCountdown.textContent = 'imagining';
    } else if (activeSession?.kind === 'archive_cycle') {
      const seconds = secondsUntilNextArchiveImagination();
      aiCountdown.textContent = archiveImaginationSlots.size >= 2
        ? '2/2 complete'
        : `next / ${compactCountdown(seconds)}`;
    } else if (completedArchiveObservationKey === currentObservationKey()) {
      aiCountdown.textContent = 'holding final association';
    } else {
      aiCountdown.textContent = aiEnabled ? 'waiting for stream' : 'paused';
    }
  }, 1000);

  if (mirrorRole === 'receiver') {
    document.body.dataset.mirrorRole = 'receiver';
    archiveVideo.pause();
    archiveVideo.hidden = true;
    cameraVideo.hidden = true;
    aiEnabled = false;
    streamButton.disabled = true;
    imagineButton.disabled = true;
    setAIStatus('Mirror / waiting for screen 1', 'ready');
    aiCountdown.textContent = 'synchronized receiver';
    mirrorChannel?.postMessage({ type: 'request' });
    window.setInterval(() => mirrorChannel?.postMessage({ type: 'request' }), 3000);
    if (requestedMirrorRole === 'auto') {
      window.setInterval(() => {
        const lease = readPrimaryLease();
        if (!lease?.token || Number(lease.expiresAt) <= Date.now()) window.location.reload();
      }, 3500);
    }
  } else {
    if (requestedMirrorRole === 'auto') {
      window.setInterval(() => {
        window.localStorage.setItem(primaryLeaseKey, JSON.stringify({
          token: primaryLeaseToken,
          expiresAt: Date.now() + primaryLeaseMs
        }));
      }, 2000);
    }
    useArchive();
    checkWorker();
    checkAI();
    window.setInterval(checkWorker, 2500);
    window.setInterval(checkAI, 10000);
  }
})();
