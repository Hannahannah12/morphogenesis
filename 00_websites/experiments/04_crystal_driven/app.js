(() => {
  const $ = (id) => document.getElementById(id);
  const canvas = $('field-canvas');
  const ctx = canvas.getContext('2d');
  const analysisCanvas = $('analysis-canvas');
  const analysis = analysisCanvas.getContext('2d', { willReadFrequently: true });
  const archiveVideo = $('archive-video');
  const cameraVideo = $('camera-video');
  const archiveButton = $('archive-button');
  const cameraButton = $('camera-button');
  const cameraSelect = $('camera-select');
  const audioGate = $('audio-gate');
  const audioButton = $('audio-button');
  const fullscreenButton = $('fullscreen-button');
  const controlsPanel = $('controls-panel');
  const controlsToggle = $('controls-toggle');
  const runtimeDot = $('runtime-dot');
  const runtimeLabel = $('runtime-label');
  const audioLabel = $('audio-label');
  const sourceLabel = $('source-label');
  const signalState = $('signal-state');
  const notice = $('notice');
  const reliefValue = $('activity-value');
  const depthValue = $('edge-value');
  const verticesValue = $('growth-value');
  const voicesValue = $('resonator-value');
  const reading = $('translation-reading');

  const W = 80;
  const H = 60;
  analysisCanvas.width = W;
  analysisCanvas.height = H;
  const modelCanvas = document.createElement('canvas');
  modelCanvas.width = 224;
  modelCanvas.height = 224;
  const modelContext = modelCanvas.getContext('2d');

  let source = 'archive';
  let stream = null;
  let previous = null;
  let layers = [];
  let currentSegments = [];
  let pulses = [];
  let lastPulseAt = 0;
  let lastLayerAt = 0;
  let growthActivity = 0;
  let currentFront = 0;
  let audioContext = null;
  let master = null;
  let echoInput = null;
  let delayA = null;
  let delayB = null;
  let feedbackA = null;
  let feedbackB = null;
  let filterA = null;
  let filterB = null;
  let audioEnabled = false;
  let droneNodes = [];
  let activeVoices = 0;
  let dpr = 1;
  let modelBusy = false;
  let modelSignals = null;
  let lastModelVoiceAt = 0;

  const clamp = (n, min = 0, max = 1) => Math.max(min, Math.min(max, n));
  const activeVideo = () => source === 'camera' ? cameraVideo : archiveVideo;
  const setNotice = (message) => { notice.textContent = message; };

  const resize = () => {
    dpr = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.floor(innerWidth * dpr);
    canvas.height = Math.floor(innerHeight * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };

  const resetField = () => {
    previous = null;
    layers = [];
    currentSegments = [];
    pulses = [];
    growthActivity = 0;
    currentFront = 0;
  };

  const emitPulse = (x, y, strength) => {
    const now = performance.now();
    pulses.push({ x, y, strength, created: now });
    pulses = pulses.slice(-28);
  };

  const analyseFrame = () => {
    const video = activeVideo();
    if (video.readyState < 2 || !video.videoWidth) {
      signalState.textContent = 'Waiting for video frame';
      return;
    }
    analysis.drawImage(video, 0, 0, W, H);
    const data = analysis.getImageData(0, 0, W, H).data;
    const current = new Float32Array(W * H);
    let changeTotal = 0;
    let edgeTotal = 0;
    let frontCount = 0;
    const edgeMask = new Uint8Array(W * H);
    const bins = Array.from({ length: 48 }, () => ({ weight: 0, x: 0, y: 0, count: 0 }));

    for (let i = 0; i < current.length; i += 1) {
      const p = i * 4;
      current[i] = (data[p] * 0.2126 + data[p + 1] * 0.7152 + data[p + 2] * 0.0722) / 255;
      if (previous) changeTotal += Math.abs(current[i] - previous[i]);
    }
    if (!previous) {
      previous = current;
      return;
    }

    const averageChange = changeTotal / current.length;
    const threshold = Math.max(0.045, averageChange * 1.85);
    for (let y = 1; y < H - 1; y += 1) {
      for (let x = 1; x < W - 1; x += 1) {
        const i = y * W + x;
        const gx = current[i + 1] - current[i - 1];
        const gy = current[i + W] - current[i - W];
        const edge = Math.hypot(gx, gy);
        const difference = Math.abs(current[i] - previous[i]);
        const newGrowth = difference > threshold && edge > 0.04
          ? clamp((difference - threshold) * 3.8 + edge * 0.5)
          : 0;
        edgeTotal += edge;
        if (edge > 0.095) edgeMask[i] = 1;
        if (newGrowth > 0.12) frontCount += 1;
        if (newGrowth > 0.12) {
          const bx = Math.min(7, Math.floor(x / W * 8));
          const by = Math.min(5, Math.floor(y / H * 6));
          const bin = bins[by * 8 + bx];
          bin.weight += newGrowth;
          bin.x += x * newGrowth;
          bin.y += y * newGrowth;
          bin.count += 1;
        }
      }
    }

    growthActivity += (clamp(averageChange * 11) - growthActivity) * 0.18;
    currentFront += (clamp(frontCount / 90) - currentFront) * 0.2;
    const now = performance.now();
    const segments = [];
    for (let y = 2; y < H - 2; y += 2) {
      let start = -1;
      for (let x = 1; x < W - 1; x += 1) {
        const active = edgeMask[y * W + x] === 1;
        if (active && start < 0) start = x;
        if ((!active || x === W - 2) && start >= 0) {
          const end = active ? x : x - 1;
          if (end - start >= 1) segments.push({ x1: start / W, x2: end / W, y: y / H });
          start = -1;
        }
      }
    }
    currentSegments = segments;
    if (segments.length > 4 && now - lastLayerAt > 850) {
      layers.push({ segments: segments.slice(0, 180), created: now, activity: growthActivity });
      layers = layers.slice(-34);
      lastLayerAt = now;
    }
    const candidate = bins
      .filter((bin) => bin.count >= 3 && bin.weight > 0.52)
      .sort((a, b) => b.weight - a.weight)[0];
    if (candidate && now - lastPulseAt > 950) {
      emitPulse(
        candidate.x / candidate.weight / W,
        candidate.y / candidate.weight / H,
        clamp(candidate.weight / 6, 0.18, 1)
      );
      lastPulseAt = now;
    }
    previous = current;
    pulses = pulses.filter((pulse) => now - pulse.created < 10000);
    reliefValue.textContent = String(layers.length);
    depthValue.textContent = modelSignals ? modelSignals.drift.toFixed(3) : '--';
    verticesValue.textContent = modelSignals ? modelSignals.coherence.toFixed(3) : '--';
    voicesValue.textContent = modelSignals ? String(modelSignals.fragments) : '--';
    signalState.textContent = modelSignals ? 'DINO structure model / live' : 'Awaiting DINO structure model';
    runtimeDot.classList.add('ready');
    runtimeLabel.textContent = source === 'camera' ? 'Camera field / live' : 'Archive field / live';
    reading.textContent = !modelSignals
      ? 'Visual time layers continue while the structure model connects.'
      : layers.length < 3
      ? 'The first structural traces are entering temporal depth.'
      : `${layers.length} moments coexist in depth; DINO structure now shapes the acoustic space.`;
  };

  const applyModelSignals = (signals) => {
    modelSignals = signals;
    const nowMs = performance.now();
    if (audioContext) {
      const now = audioContext.currentTime;
      const entropyRange = clamp((signals.entropy - 0.94) / 0.06);
      const firstDelay = 0.34 + entropyRange * 0.38;
      delayA?.delayTime.setTargetAtTime(firstDelay, now, 0.7);
      delayB?.delayTime.setTargetAtTime(firstDelay * (1.42 + signals.anisotropy * 0.22), now, 0.7);
      feedbackA?.gain.setTargetAtTime(0.15 + Math.min(signals.fragments, 12) / 12 * 0.2, now, 0.8);
      feedbackB?.gain.setTargetAtTime(0.12 + signals.coherence * 0.16, now, 0.8);
      filterA?.frequency.setTargetAtTime(650 + signals.coherence * 1500, now, 0.8);
      filterB?.frequency.setTargetAtTime(520 + signals.entropy * 1100, now, 0.8);
      const centreDetune = (signals.centroid.y - 0.5) * 12;
      droneNodes.forEach((node, index) => {
        node.oscillator.detune.setTargetAtTime(centreDetune + [-5, 0, 6][index], now, 0.9);
      });
    }
    if (
      audioEnabled
      && signals.drift > 0.006
      && nowMs - lastModelVoiceAt > 2200
    ) {
      playGlassVoice(signals.centroid.x, signals.centroid.y, clamp(signals.drift * 55, 0.2, 1));
      lastModelVoiceAt = nowMs;
    }
  };

  const analyseWithModel = async () => {
    if (modelBusy) return;
    const video = activeVideo();
    if (video.readyState < 2 || !video.videoWidth) return;
    modelBusy = true;
    try {
      modelContext.drawImage(video, 0, 0, 224, 224);
      const response = await fetch('http://127.0.0.1:8892/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image: modelCanvas.toDataURL('image/jpeg', 0.72)
        })
      });
      if (!response.ok) throw new Error(`model HTTP ${response.status}`);
      applyModelSignals(await response.json());
    } catch (error) {
      modelSignals = null;
      signalState.textContent = 'Standalone DINO worker / disconnected';
    } finally {
      modelBusy = false;
    }
  };

  const createImpulse = (context, seconds, decay) => {
    const length = Math.floor(context.sampleRate * seconds);
    const buffer = context.createBuffer(2, length, context.sampleRate);
    for (let c = 0; c < 2; c += 1) {
      const channel = buffer.getChannelData(c);
      for (let i = 0; i < length; i += 1) {
        channel[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / length, decay);
      }
    }
    return buffer;
  };

  const buildAudio = async () => {
    if (!audioContext) {
      audioContext = new AudioContext();
      master = audioContext.createGain();
      master.gain.value = 0.0001;
      const compressor = audioContext.createDynamicsCompressor();
      compressor.threshold.value = -24;
      compressor.ratio.value = 3;
      master.connect(compressor).connect(audioContext.destination);

      echoInput = audioContext.createGain();
      echoInput.gain.value = 0.7;
      echoInput.connect(master);

      delayA = audioContext.createDelay(2);
      delayB = audioContext.createDelay(2);
      delayA.delayTime.value = 0.47;
      delayB.delayTime.value = 0.71;
      feedbackA = audioContext.createGain();
      feedbackB = audioContext.createGain();
      feedbackA.gain.value = 0.32;
      feedbackB.gain.value = 0.24;
      filterA = audioContext.createBiquadFilter();
      filterB = audioContext.createBiquadFilter();
      filterA.type = filterB.type = 'lowpass';
      filterA.frequency.value = 1500;
      filterB.frequency.value = 1100;
      echoInput.connect(delayA);
      echoInput.connect(delayB);
      delayA.connect(filterA).connect(feedbackA).connect(delayA);
      delayB.connect(filterB).connect(feedbackB).connect(delayB);

      const reverb = audioContext.createConvolver();
      reverb.buffer = createImpulse(audioContext, 5.5, 2.8);
      const wet = audioContext.createGain();
      wet.gain.value = 0.34;
      delayA.connect(reverb);
      delayB.connect(reverb);
      reverb.connect(wet).connect(master);
      delayA.connect(master);
      delayB.connect(master);
      startDrone();
    }
    await audioContext.resume();
    audioEnabled = true;
    master.gain.setTargetAtTime(0.2, audioContext.currentTime, 1.8);
    audioGate.hidden = true;
    audioButton.textContent = 'Mute audio';
    audioButton.classList.add('active');
    audioLabel.textContent = 'Audio / drifting';
    setNotice('A narrow band of near tones is moving through two feedback delays.');
  };

  const startDrone = () => {
    const base = 109;
    [-6, 0, 7].forEach((cents, index) => {
      const oscillator = audioContext.createOscillator();
      oscillator.type = index === 1 ? 'sine' : 'triangle';
      oscillator.frequency.value = base;
      oscillator.detune.value = cents;
      const gain = audioContext.createGain();
      gain.gain.value = index === 1 ? 0.035 : 0.012;
      const filter = audioContext.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.value = 430 + index * 90;
      oscillator.connect(filter).connect(gain).connect(echoInput);
      oscillator.start();
      droneNodes.push({ oscillator, gain, filter });
    });
  };

  const playGlassVoice = (x, y, strength) => {
    if (!audioContext || !audioEnabled || activeVoices >= 3) return;
    const now = audioContext.currentTime;
    const nearbyRatios = [1, 1.014, 1.029, 1.045];
    const ratio = nearbyRatios[Math.min(nearbyRatios.length - 1, Math.floor(y * nearbyRatios.length))];
    const frequency = 218 * ratio;
    const duration = 3.8 + strength * 2.8;
    const oscillator = audioContext.createOscillator();
    oscillator.type = 'sine';
    oscillator.frequency.setValueAtTime(frequency, now);
    oscillator.frequency.exponentialRampToValueAtTime(frequency * 0.997, now + duration);
    const shimmer = audioContext.createOscillator();
    shimmer.type = 'sine';
    shimmer.frequency.value = frequency * 2.003;
    const shimmerGain = audioContext.createGain();
    shimmerGain.gain.value = 0.13;
    const gain = audioContext.createGain();
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.03 + strength * 0.025, now + 0.18);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);
    const pan = audioContext.createStereoPanner();
    pan.pan.value = clamp(x * 1.2 - 0.6, -0.6, 0.6);
    oscillator.connect(gain);
    shimmer.connect(shimmerGain).connect(gain);
    gain.connect(pan).connect(echoInput);
    oscillator.start(now);
    shimmer.start(now);
    oscillator.stop(now + duration + 0.1);
    shimmer.stop(now + duration + 0.1);
    activeVoices += 1;
    voicesValue.textContent = String(activeVoices);
    window.setTimeout(() => {
      activeVoices = Math.max(0, activeVoices - 1);
      voicesValue.textContent = String(activeVoices);
    }, duration * 1000);
  };

  const toggleAudio = async () => {
    if (!audioContext || !audioEnabled) return buildAudio();
    audioEnabled = false;
    master.gain.setTargetAtTime(0.0001, audioContext.currentTime, 0.7);
    audioButton.textContent = 'Start audio';
    audioButton.classList.remove('active');
    audioLabel.textContent = 'Audio / muted';
  };

  const project = (nx, ny, z, yaw, width, height) => {
    const x = (nx - 0.5) * Math.min(width * 0.72, 850);
    const y = (ny - 0.5) * Math.min(height * 0.7, 520);
    const cosY = Math.cos(yaw);
    const sinY = Math.sin(yaw);
    const rx = x * cosY + z * sinY;
    const rz = -x * sinY + z * cosY;
    const pitch = -0.1;
    const py = y * Math.cos(pitch) - rz * Math.sin(pitch);
    const pz = y * Math.sin(pitch) + rz * Math.cos(pitch);
    const perspective = 920 / (1120 - pz);
    return {
      x: width * 0.5 + rx * perspective,
      y: height * 0.5 + 18 + py * perspective,
      depth: pz,
      scale: perspective
    };
  };

  const draw = () => {
    const width = innerWidth;
    const height = innerHeight;
    const now = performance.now();
    const yaw = -0.34 + Math.sin(now * 0.00012) * 0.22;
    ctx.fillStyle = '#050505';
    ctx.fillRect(0, 0, width, height);

    ctx.save();
    ctx.globalCompositeOperation = 'screen';
    layers.forEach((layer, index) => {
      const age = layers.length <= 1 ? 0 : 1 - index / (layers.length - 1);
      const z = 160 - age * 620;
      const alpha = 0.07 + (1 - age) * 0.42;
      layer.segments.forEach((segment) => {
        const a = project(segment.x1, segment.y, z, yaw, width, height);
        const b = project(segment.x2, segment.y, z, yaw, width, height);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = `rgba(218, 220, 219, ${alpha})`;
        ctx.lineWidth = index === layers.length - 1 ? 1.05 : 0.55;
        ctx.stroke();
      });
      if (index % 4 === 0 || index === layers.length - 1) {
        const corners = [
          project(0, 0, z, yaw, width, height),
          project(1, 0, z, yaw, width, height),
          project(1, 1, z, yaw, width, height),
          project(0, 1, z, yaw, width, height)
        ];
        ctx.beginPath();
        corners.forEach((point, corner) => {
          if (corner === 0) ctx.moveTo(point.x, point.y);
          else ctx.lineTo(point.x, point.y);
        });
        ctx.closePath();
        ctx.strokeStyle = `rgba(184, 186, 185, ${alpha * 0.23})`;
        ctx.lineWidth = 0.45;
        ctx.stroke();
      }
    });
    ctx.restore();

    if (layers.length > 1) {
      const oldCorner = project(0, 0, -460, yaw, width, height);
      const newCorner = project(0, 0, 160, yaw, width, height);
      ctx.beginPath();
      ctx.moveTo(oldCorner.x, oldCorner.y);
      ctx.lineTo(newCorner.x, newCorner.y);
      ctx.strokeStyle = 'rgba(194, 196, 195, 0.18)';
      ctx.lineWidth = 0.5;
      ctx.stroke();
    }

    pulses.forEach((pulse, index) => {
      const point = project(pulse.x, pulse.y, 170, yaw, width, height);
      const age = clamp((now - pulse.created) / 10000);
      const radius = 2.5 + pulse.strength * 3;
      ctx.beginPath();
      ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(222, 224, 223, ${0.32 - age * 0.2})`;
      ctx.lineWidth = 0.5;
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(point.x, point.y);
      ctx.lineTo(point.x, point.y - 10 - pulse.strength * 10);
      ctx.strokeStyle = `rgba(196, 198, 197, ${0.16 - age * 0.1})`;
      ctx.stroke();
    });

    ctx.fillStyle = 'rgba(210, 212, 211, 0.42)';
    ctx.font = '9px Helvetica Neue, Arial, sans-serif';
    ctx.fillText('CRYSTAL TIME VOLUME / XY = STRUCTURE / Z = TIME', Math.max(32, width * 0.28), height - 40);
    requestAnimationFrame(draw);
  };

  const populateCameras = async () => {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const cameras = devices.filter((device) => device.kind === 'videoinput');
    cameraSelect.innerHTML = '<option value="">Choose USB camera</option>';
    cameras.forEach((camera, index) => {
      const option = document.createElement('option');
      option.value = camera.deviceId;
      option.textContent = camera.label || `Camera ${index + 1}`;
      cameraSelect.append(option);
    });
    const preferred = cameras.find((camera) => /uvc|usb|macro/i.test(camera.label));
    if (preferred) cameraSelect.value = preferred.deviceId;
  };

  const useCamera = async (deviceId = '') => {
    stream?.getTracks().forEach((track) => track.stop());
    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: deviceId ? { deviceId: { exact: deviceId } } : true
    });
    cameraVideo.srcObject = stream;
    cameraVideo.hidden = false;
    archiveVideo.hidden = true;
    source = 'camera';
    resetField();
    sourceLabel.textContent = 'Source / USB macro camera';
    archiveButton.classList.remove('active');
    setNotice('USB camera is generating a live spatial field.');
    await populateCameras();
  };

  const findCamera = async () => {
    try {
      await useCamera(cameraSelect.value);
    } catch (error) {
      setNotice(`Camera unavailable: ${error.message}`);
    }
  };

  const useArchive = (name = 'ice_crystal_01') => {
    stream?.getTracks().forEach((track) => track.stop());
    stream = null;
    cameraVideo.srcObject = null;
    cameraVideo.hidden = true;
    archiveVideo.hidden = false;
    archiveVideo.src = name === 'ice_crystal_02'
      ? '../../../05_shared_data/input/ice_crystal_02.mp4'
      : '../../../05_shared_data/input/ice_crystal_01.mp4';
    archiveVideo.play().catch(() => {});
    source = 'archive';
    resetField();
    sourceLabel.textContent = `Source / ${name === 'ice_crystal_02' ? 'ice_crystal_02' : 'ice_crystal_01'} archive`;
    archiveButton.classList.add('active');
    setNotice('Archive video is generating a spatial field.');
  };

  controlsToggle.addEventListener('click', () => {
    const collapsed = controlsPanel.classList.toggle('collapsed');
    controlsToggle.setAttribute('aria-expanded', String(!collapsed));
    controlsToggle.setAttribute('aria-label', collapsed ? 'Expand controls' : 'Collapse controls');
    controlsToggle.textContent = collapsed ? '+' : '−';
  });
  archiveButton.addEventListener('click', () => useArchive('ice_crystal_01'));
  cameraButton.addEventListener('click', findCamera);
  cameraSelect.addEventListener('change', () => cameraSelect.value && findCamera());
  audioGate.addEventListener('click', buildAudio);
  audioButton.addEventListener('click', toggleAudio);
  fullscreenButton.addEventListener('click', () => {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen?.();
    else document.exitFullscreen?.();
  });
  archiveVideo.addEventListener('loadeddata', () => {
    signalState.textContent = 'Video frame ready';
    setNotice('Archive ready. Geometry begins before audio is enabled.');
  });
  window.addEventListener('resize', resize);

  window.getMorphogenesisPageDetails = () => ({
    source: sourceLabel.textContent,
    cameraActive: Boolean(cameraVideo.srcObject),
    audioEnabled,
    timeLayers: layers.length,
    structureModel: modelSignals?.model || 'disconnected',
    modelDrift: modelSignals ? Number(modelSignals.drift.toFixed(4)) : null,
    coherence: modelSignals ? Number(modelSignals.coherence.toFixed(4)) : null,
    fragments: modelSignals?.fragments ?? null
  });

  window.handleMorphogenesisCommand = async (command) => {
    if (command?.action !== 'setSource') return false;
    if (command.value === 'camera') await findCamera();
    else useArchive(command.value === 'ice_crystal_02' ? 'ice_crystal_02' : 'ice_crystal_01');
    return true;
  };

  resize();
  draw();
  window.setInterval(analyseFrame, 110);
  window.setInterval(analyseWithModel, 1600);
  useArchive('ice_crystal_01');
})();
