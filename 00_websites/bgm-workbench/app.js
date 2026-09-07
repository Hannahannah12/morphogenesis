(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const crystalTabs = $('crystal-tabs');
  const crystalVideo = $('crystal-video');
  const crystalTitle = $('crystal-title');
  const durationLabel = $('duration-label');
  const masterWaveform = $('master-waveform');
  const playButton = $('play-button');
  const stopButton = $('stop-button');
  const timeline = $('timeline');
  const currentTimeLabel = $('current-time');
  const totalTimeLabel = $('total-time');
  const loopProject = $('loop-project');
  const audioState = $('audio-state');
  const audioInput = $('audio-input');
  const dropZone = $('drop-zone');
  const tracksElement = $('tracks');
  const emptyTracks = $('empty-tracks');
  const exportButton = $('export-button');
  const projectStatus = $('project-status');
  const masterVolume = $('master-volume');
  const masterVolumeValue = $('master-volume-value');
  const noiseEnabled = $('noise-enabled');
  const noiseLevel = $('noise-level');
  const noiseLevelValue = $('noise-level-value');
  const noiseTone = $('noise-tone');
  const noiseToneValue = $('noise-tone-value');
  const noisePulse = $('noise-pulse');
  const noisePulseValue = $('noise-pulse-value');
  const noiseGrain = $('noise-grain');
  const noiseGrainValue = $('noise-grain-value');
  const randomiseNoise = $('randomise-noise');
  const noiseSeed = $('noise-seed');

  const crystalDurations = [23.366633, 41.9333, 20, 23.178, 21.8667, 15.399933];
  // Normalized frame-to-frame motion sampled directly from each source video.
  const crystalMotionProfiles = [
    [0.655,0.769,0.252,0.028,0.055,0.089,0.053,0.142,0.25,0.211,0.196,0.245,0.325,0.432,0.487,0.525,0.872,1,0.849,0.39,0.231,0.214,0.131,0.093,0.091,0.103,0.116,0.085,0.031,0.046,0.058,0.034,0.022,0.078,0.144,0.218,0.346,0.217,0.167,0.167,0.122,0.043,0.108,0.299,0.499,0.763,0.716,0.463],
    [0.566,0.547,0.357,0.393,0.784,0.978,0.926,0.649,0.496,0.563,0.209,0.054,0.021,0.004,0.004,0.201,0.8,0.907,0.551,0.199,0.032,0.014,0.04,0.021,0.05,0.165,0.338,0.369,0.246,0.208,0.152,0.122,0.108,0.114,0.104,0.074,0.092,0.103,0.125,0.133,0.143,0.137,0.117,0.118,0.127,0.125,0.097,0.039],
    [0,0.2,0.8,1,1,0.995,0.898,0.585,0.375,0.441,0.365,0.13,0.167,0.603,0.729,0.697,0.711,0.494,0.408,0.395,0.462,0.395,0.127,0.061,0.218,0.378,0.48,0.297,0.3,0.26,0.235,0.226,0.225,0.168,0.242,0.388,0.441,0.384,0.377,0.37,0.57,0.489,0.382,0.409,0.288,0.433,0.46,0.339],
    [0.244,0.235,0.335,0.474,0.545,0.743,0.905,0.848,0.857,0.868,0.963,0.86,0.412,0.182,0.149,0.18,0.187,0.144,0.083,0.022,0.019,0.062,0.05,0.023,0.048,0.072,0.114,0.093,0.056,0.258,0.642,0.699,0.524,0.202,0.043,0.115,0.298,0.354,0.29,0.245,0.293,0.402,0.361,0.666,0.929,0.979,0.918,0.571],
    [0.549,0.916,0.999,0.896,0.664,0.809,0.883,0.539,0.154,0.143,0.096,0.021,0.032,0.121,0.153,0.193,0.182,0.122,0.188,0.183,0.167,0.113,0.178,0.199,0.159,0.106,0.175,0.199,0.188,0.202,0.161,0.091,0.185,0.185,0.182,0.143,0.086,0.203,0.258,0.287,0.415,0.688,0.789,0.47,0.47,0.484,0.652,0.522],
    [0.012,0.026,0.039,0.171,0.602,0.93,1,1,0.92,0.704,0.669,0.57,0.526,0.692,0.577,0.258,0.137,0.109,0.106,0.061,0.021,0.015,0.019,0.014,0.01,0.006,0.007,0.002,0,0,0.003,0.07,0.249,0.435,0.659,0.329,0.198,0.133,0.055,0.034,0.027,0.041,0.031,0.011,0.013,0.011,0.011,0.007]
  ];
  const crystals = Array.from({ length: 6 }, (_, index) => ({
    id: `ice_crystal_${String(index + 1).padStart(2, '0')}`,
    number: index + 1,
    duration: crystalDurations[index],
    tracks: [],
    noise: {
      enabled: true,
      level: 0.18,
      tone: 2800 + index * 420,
      pulse: 2.4 + index * 0.28,
      grain: 0.42 + index * 0.045,
      seed: 101 + index * 97,
      motionProfile: crystalMotionProfiles[index]
    }
  }));

  let activeCrystal = crystals[0];
  let audioContext = null;
  let masterGain = null;
  let transportPosition = 0;
  let transportStartedAt = 0;
  let transportFrame = 0;
  let playing = false;
  let liveNodes = [];
  let nextTrackId = 1;
  let exporting = false;

  const formatTime = (seconds, precise = true) => {
    const safe = Math.max(0, Number(seconds) || 0);
    const minutes = Math.floor(safe / 60);
    const remainder = safe - minutes * 60;
    return `${String(minutes).padStart(2, '0')}:${remainder.toFixed(precise ? 1 : 0).padStart(precise ? 4 : 2, '0')}`;
  };

  const formatFrequency = (value) => value >= 1000
    ? `${(value / 1000).toFixed(1)} kHz`
    : `${Math.round(value)} Hz`;

  const currentPosition = () => playing && audioContext
    ? Math.max(0, audioContext.currentTime - transportStartedAt)
    : transportPosition;

  const setAudioState = (label, ready = false) => {
    audioState.className = `status ${ready ? 'ready' : ''}`.trim();
    audioState.lastChild.textContent = label;
  };

  const ensureAudio = async () => {
    if (!audioContext) {
      audioContext = new AudioContext({ latencyHint: 'interactive' });
      masterGain = audioContext.createGain();
      masterGain.gain.value = Number(masterVolume.value);
      masterGain.connect(audioContext.destination);
    }
    if (audioContext.state !== 'running') await audioContext.resume();
    setAudioState('Audio ready', true);
    return audioContext;
  };

  const seededRandom = (initialSeed) => {
    let seed = initialSeed >>> 0;
    return () => {
      seed += 0x6d2b79f5;
      let value = seed;
      value = Math.imul(value ^ value >>> 15, value | 1);
      value ^= value + Math.imul(value ^ value >>> 7, value | 61);
      return ((value ^ value >>> 14) >>> 0) / 4294967296;
    };
  };

  const motionAt = (settings, progress) => {
    const profile = settings.motionProfile;
    if (!profile?.length) return 0.5;
    const position = Math.max(0, Math.min(1, progress)) * (profile.length - 1);
    const lower = Math.floor(position);
    const upper = Math.min(profile.length - 1, lower + 1);
    const mix = position - lower;
    return profile[lower] * (1 - mix) + profile[upper] * mix;
  };

  const smoothstep = (start, end, value) => {
    const normalized = Math.max(0, Math.min(1, (value - start) / (end - start)));
    return normalized * normalized * (3 - 2 * normalized);
  };

  const createNoiseBuffer = (context, settings, seconds = 8) => {
    const sampleRate = context.sampleRate;
    const frameCount = Math.max(1, Math.ceil(seconds * sampleRate));
    const buffer = context.createBuffer(2, frameCount, sampleRate);
    for (let channel = 0; channel < 2; channel += 1) {
      const random = seededRandom(settings.seed + channel * 7919);
      const data = buffer.getChannelData(channel);
      let coilPhase = channel * 0.18;
      let pulsePhase = channel * 0.07;
      let arc = 0;
      let arcRingPhase = channel * 0.41;
      for (let index = 0; index < frameCount; index += 1) {
        const time = index / sampleRate;
        const progress = time / seconds;
        const sourceMotion = motionAt(settings, progress);
        const formation = smoothstep(0.025, 0.76, progress);
        const settling = 1 - smoothstep(0.86, 1, progress) * 0.58;
        const visualActivity = (0.055 + sourceMotion * 0.945) * settling;
        const white = random() * 2 - 1;
        const stereoPhase = channel * 0.025;
        const hum =
          Math.sin(Math.PI * 2 * 50 * time + stereoPhase) * 0.62 +
          Math.sin(Math.PI * 2 * 100 * time + stereoPhase) * 0.27 +
          Math.sin(Math.PI * 2 * 150 * time + stereoPhase) * 0.13 +
          Math.sin(Math.PI * 2 * 250 * time + stereoPhase) * 0.06;

        const coilDrift = 1 + Math.sin(Math.PI * 2 * 0.17 * time + channel) * 0.004;
        const visualPitch = settings.tone * (0.72 + formation * 0.25 + sourceMotion * 0.08);
        coilPhase += Math.PI * 2 * visualPitch * coilDrift / sampleRate;
        const coil = Math.sin(coilPhase) + Math.sin(coilPhase * 2) * 0.23;

        pulsePhase += Math.PI * 2 * settings.pulse * (0.62 + sourceMotion * 0.9) / sampleRate;
        const pulseWave = settings.pulse > 0
          ? Math.sin(pulsePhase)
          : 1;
        const pulseEnvelope = settings.pulse > 0
          ? 0.16 + 0.84 * Math.pow((pulseWave + 1) / 2, 5)
          : 1;

        if (random() < (0.000008 + settings.grain * 0.00022) * visualActivity) {
          arc = 0.55 + random() * 0.45;
          arcRingPhase = random() * Math.PI * 2;
        }
        arc *= 0.961 + settings.grain * 0.008;
        arcRingPhase += Math.PI * 2 * (900 + settings.tone * 0.16) / sampleRate;
        const discharge = arc * (white * 0.72 + Math.sin(arcRingPhase) * 0.28);
        const contactBuzz = Math.tanh(Math.sin(Math.PI * 2 * (118 + settings.pulse * 4) * time) * 9);
        const thinHiss = white * (0.008 + settings.grain * 0.018);
        const electrical =
          hum * (0.105 + visualActivity * 0.13) +
          coil * (0.045 + settings.grain * 0.09) * pulseEnvelope * visualActivity +
          contactBuzz * 0.026 * pulseEnvelope * visualActivity +
          discharge * 0.48 +
          thinHiss * (0.35 + visualActivity * 0.65);
        data[index] = Math.tanh(electrical * 1.35) * 0.78;
      }
    }
    return buffer;
  };

  const createPanner = (context, pan) => {
    if (!context.createStereoPanner) return null;
    const panner = context.createStereoPanner();
    panner.pan.value = pan;
    return panner;
  };

  const connectTrack = (context, source, track, destination) => {
    const filter = context.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = track.filter;
    filter.Q.value = 0.45;
    const gain = context.createGain();
    gain.gain.value = track.muted ? 0 : track.volume;
    const panner = createPanner(context, track.pan);
    source.connect(filter);
    filter.connect(gain);
    if (panner) {
      gain.connect(panner);
      panner.connect(destination);
    } else {
      gain.connect(destination);
    }
    return { source, trackId: track.id, filter, gain, panner };
  };

  const stopSources = () => {
    liveNodes.forEach((node) => {
      try { node.source.stop(); } catch (_) { /* already stopped */ }
      try { node.source.disconnect(); } catch (_) { /* already disconnected */ }
    });
    liveNodes = [];
  };

  const scheduleNoise = (context, destination, settings, position, stopAt = null) => {
    if (!settings.enabled || settings.level <= 0) return null;
    const buffer = createNoiseBuffer(context, settings, activeCrystal.duration);
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.loop = true;
    const filter = context.createBiquadFilter();
    filter.type = 'peaking';
    filter.frequency.value = settings.tone;
    filter.Q.value = 1.25;
    filter.gain.value = 4.5;
    const gain = context.createGain();
    gain.gain.value = settings.level;
    source.connect(filter);
    filter.connect(gain);
    gain.connect(destination);
    const startTime = context.currentTime || 0;
    source.start(startTime, position % buffer.duration);
    if (stopAt !== null) source.stop(stopAt);
    return { source, trackId: 'noise', filter, gain, panner: null };
  };

  const scheduleTrack = (context, destination, track, position, stopAt = null) => {
    if (!track.buffer) return null;
    const relative = position - track.offset;
    if (!track.loop && relative >= track.buffer.duration) return null;
    const delay = Math.max(0, -relative);
    const offset = relative <= 0 ? 0 : track.loop
      ? relative % track.buffer.duration
      : relative;
    const source = context.createBufferSource();
    source.buffer = track.buffer;
    source.loop = track.loop;
    const nodes = connectTrack(context, source, track, destination);
    const startTime = (context.currentTime || 0) + delay;
    source.start(startTime, offset);
    if (stopAt !== null) source.stop(stopAt);
    return nodes;
  };

  const updateTimeline = () => {
    const position = Math.min(activeCrystal.duration, currentPosition());
    timeline.value = String(position);
    currentTimeLabel.textContent = formatTime(position);
    if (crystalVideo.readyState >= HTMLMediaElement.HAVE_METADATA
      && Math.abs(crystalVideo.currentTime - position) > 0.45) {
      crystalVideo.currentTime = Math.min(position, Math.max(0, crystalVideo.duration - 0.04));
    }
    drawMasterWaveform(position);
    if (playing && position >= activeCrystal.duration) {
      if (loopProject.checked) startPlayback(0);
      else pausePlayback(true);
      return;
    }
    if (playing) transportFrame = window.requestAnimationFrame(updateTimeline);
  };

  const startPlayback = async (position = transportPosition) => {
    await ensureAudio();
    stopSources();
    window.cancelAnimationFrame(transportFrame);
    transportPosition = Math.max(0, Math.min(position, activeCrystal.duration));
    transportStartedAt = audioContext.currentTime - transportPosition;
    liveNodes.push(...activeCrystal.tracks
      .map((track) => scheduleTrack(audioContext, masterGain, track, transportPosition))
      .filter(Boolean));
    const noiseNode = scheduleNoise(audioContext, masterGain, activeCrystal.noise, transportPosition);
    if (noiseNode) liveNodes.push(noiseNode);
    const videoDuration = Number.isFinite(crystalVideo.duration)
      ? crystalVideo.duration
      : activeCrystal.duration;
    crystalVideo.currentTime = Math.min(transportPosition, Math.max(0, videoDuration - 0.04));
    crystalVideo.loop = loopProject.checked;
    await crystalVideo.play().catch(() => {});
    playing = true;
    playButton.textContent = 'Ⅱ';
    playButton.setAttribute('aria-label', 'Pause');
    setAudioState('Playing mix', true);
    transportFrame = window.requestAnimationFrame(updateTimeline);
  };

  const pausePlayback = (atEnd = false) => {
    if (playing) transportPosition = Math.min(activeCrystal.duration, currentPosition());
    playing = false;
    stopSources();
    crystalVideo.pause();
    window.cancelAnimationFrame(transportFrame);
    if (atEnd) transportPosition = activeCrystal.duration;
    playButton.textContent = '▶';
    playButton.setAttribute('aria-label', 'Play');
    setAudioState('Audio paused', true);
    updateTimeline();
  };

  const stopPlayback = () => {
    pausePlayback();
    transportPosition = 0;
    crystalVideo.currentTime = 0;
    updateTimeline();
  };

  const restartIfPlaying = () => {
    if (playing) startPlayback(currentPosition()).catch(() => {});
  };

  const updateLiveNodes = (track) => {
    liveNodes.filter((node) => node.trackId === track.id).forEach((node) => {
      node.gain.gain.setTargetAtTime(track.muted ? 0 : track.volume, audioContext.currentTime, 0.02);
      node.filter.frequency.setTargetAtTime(track.filter, audioContext.currentTime, 0.02);
      node.panner?.pan.setTargetAtTime(track.pan, audioContext.currentTime, 0.02);
    });
  };

  const updateLiveNoise = () => {
    if (!audioContext) return;
    const node = liveNodes.find((item) => item.trackId === 'noise');
    if (!node && playing && activeCrystal.noise.enabled) {
      restartIfPlaying();
      return;
    }
    if (!node) return;
    node.gain.gain.setTargetAtTime(
      activeCrystal.noise.enabled ? activeCrystal.noise.level : 0,
      audioContext.currentTime,
      0.03
    );
    node.filter.frequency.setTargetAtTime(activeCrystal.noise.tone, audioContext.currentTime, 0.03);
  };

  const canvasContext = (canvas) => {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.round(canvas.clientWidth * ratio));
    const height = Math.max(1, Math.round(canvas.clientHeight * ratio));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    const context = canvas.getContext('2d');
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    return { context, width: canvas.clientWidth, height: canvas.clientHeight };
  };

  const drawGrid = (context, width, height) => {
    context.clearRect(0, 0, width, height);
    context.fillStyle = '#090d0e';
    context.fillRect(0, 0, width, height);
    context.strokeStyle = 'rgba(143, 220, 255, 0.08)';
    context.lineWidth = 1;
    for (let index = 0; index <= 8; index += 1) {
      const x = index / 8 * width;
      context.beginPath();
      context.moveTo(x, 0);
      context.lineTo(x, height);
      context.stroke();
    }
    context.beginPath();
    context.moveTo(0, height / 2);
    context.lineTo(width, height / 2);
    context.stroke();
  };

  const drawBufferWaveform = (canvas, buffer, color = '#8fdcff') => {
    const { context, width, height } = canvasContext(canvas);
    drawGrid(context, width, height);
    if (!buffer) return;
    const data = buffer.getChannelData(0);
    const columns = Math.max(1, Math.floor(width));
    const block = Math.max(1, Math.floor(data.length / columns));
    context.strokeStyle = color;
    context.lineWidth = 1;
    context.beginPath();
    for (let x = 0; x < columns; x += 1) {
      let peak = 0;
      const start = x * block;
      const end = Math.min(data.length, start + block);
      for (let index = start; index < end; index += 1) peak = Math.max(peak, Math.abs(data[index]));
      context.moveTo(x, height / 2 - peak * height * 0.42);
      context.lineTo(x, height / 2 + peak * height * 0.42);
    }
    context.stroke();
  };

  const drawMasterWaveform = (playhead = currentPosition()) => {
    const { context, width, height } = canvasContext(masterWaveform);
    drawGrid(context, width, height);
    const tracks = activeCrystal.tracks.filter((track) => track.buffer && !track.muted);
    const columns = Math.max(1, Math.floor(width));
    context.strokeStyle = 'rgba(143, 220, 255, 0.72)';
    context.lineWidth = 1;
    context.beginPath();
    for (let x = 0; x < columns; x += 1) {
      const time = x / columns * activeCrystal.duration;
      const motion = motionAt(activeCrystal.noise, time / activeCrystal.duration);
      let mixed = activeCrystal.noise.enabled
        ? activeCrystal.noise.level * (0.08 + motion * 0.42)
        : 0;
      tracks.forEach((track) => {
        const localTime = time - track.offset;
        if (localTime < 0 || (!track.loop && localTime >= track.buffer.duration)) return;
        const sampleTime = track.loop ? localTime % track.buffer.duration : localTime;
        const sampleIndex = Math.min(
          track.buffer.length - 1,
          Math.max(0, Math.floor(sampleTime * track.buffer.sampleRate))
        );
        mixed += Math.abs(track.buffer.getChannelData(0)[sampleIndex]) * track.volume;
      });
      const peak = Math.min(1, mixed / Math.max(1, tracks.length * 0.55));
      context.moveTo(x, height / 2 - peak * height * 0.38);
      context.lineTo(x, height / 2 + peak * height * 0.38);
    }
    context.stroke();
    const playheadX = activeCrystal.duration > 0 ? playhead / activeCrystal.duration * width : 0;
    context.strokeStyle = '#e0bf7c';
    context.beginPath();
    context.moveTo(playheadX, 0);
    context.lineTo(playheadX, height);
    context.stroke();
  };

  const noiseValuesToUI = () => {
    const settings = activeCrystal.noise;
    noiseEnabled.checked = settings.enabled;
    noiseLevel.value = String(settings.level);
    noiseTone.value = String(settings.tone);
    noisePulse.value = String(settings.pulse);
    noiseGrain.value = String(settings.grain);
    noiseLevelValue.value = `${Math.round(settings.level * 100)}%`;
    noiseToneValue.value = formatFrequency(settings.tone);
    noisePulseValue.value = `${settings.pulse.toFixed(1)} Hz`;
    noiseGrainValue.value = `${Math.round(settings.grain * 100)}%`;
    noiseSeed.textContent = `Seed ${String(settings.seed).padStart(4, '0')}`;
  };

  const renderTabs = () => {
    crystalTabs.replaceChildren();
    crystals.forEach((crystal) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `crystal-tab ${crystal === activeCrystal ? 'active' : ''}`.trim();
      button.innerHTML = `
        <span class="crystal-number">${String(crystal.number).padStart(2, '0')}</span>
        <span class="crystal-meta">
          <span>${formatTime(crystal.duration, false)}</span>
          <span>${crystal.tracks.length} imported</span>
        </span>`;
      button.addEventListener('click', () => selectCrystal(crystal));
      crystalTabs.append(button);
    });
  };

  const trackOutput = (label, value) => {
    if (label === 'Volume') return `${Math.round(value * 100)}%`;
    if (label === 'Pan') return value === 0 ? 'C' : `${value < 0 ? 'L' : 'R'}${Math.round(Math.abs(value) * 100)}`;
    if (label === 'Filter') return formatFrequency(value);
    return `${Number(value).toFixed(1)}s`;
  };

  const makeTrackSlider = (track, label, property, min, max, step) => {
    const wrapper = document.createElement('label');
    const name = document.createElement('span');
    name.textContent = label;
    const output = document.createElement('output');
    output.value = trackOutput(label, track[property]);
    const input = document.createElement('input');
    input.type = 'range';
    input.min = String(min);
    input.max = String(max);
    input.step = String(step);
    input.value = String(track[property]);
    input.addEventListener('input', () => {
      track[property] = Number(input.value);
      output.value = trackOutput(label, track[property]);
      if (property === 'offset') restartIfPlaying();
      else if (audioContext) updateLiveNodes(track);
      drawMasterWaveform();
    });
    wrapper.append(name, output, input);
    return wrapper;
  };

  const renderTracks = () => {
    tracksElement.replaceChildren();
    emptyTracks.hidden = activeCrystal.tracks.length > 0;
    activeCrystal.tracks.forEach((track) => {
      const row = document.createElement('article');
      row.className = 'track';
      const identity = document.createElement('div');
      identity.className = 'track-identity';
      const name = document.createElement('strong');
      name.textContent = track.name;
      name.title = track.name;
      const meta = document.createElement('span');
      meta.textContent = `${formatTime(track.buffer.duration)} · ${Math.round(track.buffer.sampleRate / 1000)} kHz`;
      identity.append(name, meta);
      const waveform = document.createElement('canvas');
      waveform.className = 'track-waveform';
      waveform.width = 520;
      waveform.height = 84;
      const controls = document.createElement('div');
      controls.className = 'track-controls';
      const mute = document.createElement('button');
      mute.type = 'button';
      mute.textContent = 'M';
      mute.title = 'Mute';
      mute.classList.toggle('active', track.muted);
      mute.addEventListener('click', () => {
        track.muted = !track.muted;
        mute.classList.toggle('active', track.muted);
        if (audioContext) updateLiveNodes(track);
        drawMasterWaveform();
      });
      const loop = document.createElement('button');
      loop.type = 'button';
      loop.textContent = 'L';
      loop.title = 'Loop track';
      loop.classList.toggle('active', track.loop);
      loop.addEventListener('click', () => {
        track.loop = !track.loop;
        loop.classList.toggle('active', track.loop);
        restartIfPlaying();
      });
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = '×';
      remove.title = 'Remove track';
      remove.className = 'remove';
      remove.addEventListener('click', () => {
        activeCrystal.tracks = activeCrystal.tracks.filter((item) => item !== track);
        restartIfPlaying();
        renderTracks();
        renderTabs();
        drawMasterWaveform();
      });
      controls.append(mute, loop, remove);
      const sliders = document.createElement('div');
      sliders.className = 'track-sliders';
      sliders.append(
        makeTrackSlider(track, 'Volume', 'volume', 0, 1.4, 0.01),
        makeTrackSlider(track, 'Pan', 'pan', -1, 1, 0.01),
        makeTrackSlider(track, 'Filter', 'filter', 180, 20000, 10),
        makeTrackSlider(track, 'Offset', 'offset', 0, activeCrystal.duration, 0.1)
      );
      row.append(identity, waveform, controls, sliders);
      tracksElement.append(row);
      window.requestAnimationFrame(() => drawBufferWaveform(waveform, track.buffer));
    });
    projectStatus.textContent = `Crystal ${String(activeCrystal.number).padStart(2, '0')} / ${activeCrystal.tracks.length} imported layers`;
  };

  const selectCrystal = (crystal) => {
    if (crystal === activeCrystal) return;
    stopPlayback();
    activeCrystal = crystal;
    transportPosition = 0;
    crystalVideo.src = `/05_shared_data/exhibition/${crystal.id}/source/crystallization.mp4`;
    crystalVideo.load();
    crystalTitle.textContent = `Crystal ${String(crystal.number).padStart(2, '0')}`;
    timeline.max = String(crystal.duration);
    durationLabel.textContent = `${crystal.duration.toFixed(2)} seconds`;
    totalTimeLabel.textContent = formatTime(crystal.duration);
    noiseValuesToUI();
    renderTabs();
    renderTracks();
    updateTimeline();
  };

  const loadFiles = async (files) => {
    const accepted = [...files].filter((file) => file.type.startsWith('audio/') || /\.(wav|mp3|m4a|aac|ogg|flac)$/i.test(file.name));
    if (!accepted.length) return;
    await ensureAudio();
    setAudioState(`Decoding ${accepted.length} sound${accepted.length > 1 ? 's' : ''}`);
    for (const file of accepted) {
      try {
        const buffer = await audioContext.decodeAudioData(await file.arrayBuffer());
        activeCrystal.tracks.push({
          id: `track-${nextTrackId++}`,
          name: file.name,
          buffer,
          volume: 0.72,
          pan: 0,
          filter: 20000,
          offset: 0,
          loop: true,
          muted: false
        });
      } catch (_) {
        setAudioState(`Could not decode ${file.name}`);
      }
    }
    setAudioState('Audio ready', true);
    renderTabs();
    renderTracks();
    drawMasterWaveform();
    audioInput.value = '';
  };

  const interleaveWav = (buffer) => {
    const channels = Math.min(2, buffer.numberOfChannels);
    const frameCount = buffer.length;
    const bytesPerSample = 2;
    const dataSize = frameCount * channels * bytesPerSample;
    const result = new ArrayBuffer(44 + dataSize);
    const view = new DataView(result);
    const writeString = (offset, value) => {
      for (let index = 0; index < value.length; index += 1) view.setUint8(offset + index, value.charCodeAt(index));
    };
    writeString(0, 'RIFF');
    view.setUint32(4, 36 + dataSize, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, channels, true);
    view.setUint32(24, buffer.sampleRate, true);
    view.setUint32(28, buffer.sampleRate * channels * bytesPerSample, true);
    view.setUint16(32, channels * bytesPerSample, true);
    view.setUint16(34, 16, true);
    writeString(36, 'data');
    view.setUint32(40, dataSize, true);
    let offset = 44;
    for (let frame = 0; frame < frameCount; frame += 1) {
      for (let channel = 0; channel < channels; channel += 1) {
        const sample = Math.max(-1, Math.min(1, buffer.getChannelData(channel)[frame]));
        view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
        offset += 2;
      }
    }
    return result;
  };

  const exportMix = async () => {
    if (exporting) return;
    exporting = true;
    exportButton.disabled = true;
    exportButton.textContent = 'Rendering…';
    setAudioState('Rendering WAV');
    try {
      const sampleRate = 44100;
      const duration = activeCrystal.duration;
      const offline = new OfflineAudioContext(2, Math.ceil(duration * sampleRate), sampleRate);
      const offlineMaster = offline.createGain();
      offlineMaster.gain.value = Number(masterVolume.value);
      offlineMaster.connect(offline.destination);
      const noiseNode = scheduleNoise(offline, offlineMaster, activeCrystal.noise, 0, duration);
      if (noiseNode) noiseNode.source.stop(duration);
      activeCrystal.tracks.forEach((track) => {
        const nodes = scheduleTrack(offline, offlineMaster, track, 0, duration);
        if (nodes && track.loop) nodes.source.stop(duration);
      });
      const rendered = await offline.startRendering();
      const blob = new Blob([interleaveWav(rendered)], { type: 'audio/wav' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${activeCrystal.id}_bgm_mix.wav`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 2000);
      setAudioState('WAV exported', true);
    } catch (error) {
      setAudioState(`Export failed: ${error.message}`);
    } finally {
      exporting = false;
      exportButton.disabled = false;
      exportButton.textContent = 'Export WAV';
    }
  };

  const updateNoiseSetting = (property, value, restart = false) => {
    activeCrystal.noise[property] = value;
    noiseValuesToUI();
    if (restart) restartIfPlaying();
    else updateLiveNoise();
    drawMasterWaveform();
  };

  playButton.addEventListener('click', () => {
    if (playing) pausePlayback();
    else startPlayback(transportPosition >= activeCrystal.duration ? 0 : transportPosition).catch(() => {
      setAudioState('Audio could not start');
    });
  });
  stopButton.addEventListener('click', stopPlayback);
  timeline.addEventListener('input', () => {
    transportPosition = Number(timeline.value);
    if (playing) startPlayback(transportPosition).catch(() => {});
    else {
      const videoDuration = Number.isFinite(crystalVideo.duration)
        ? crystalVideo.duration
        : activeCrystal.duration;
      crystalVideo.currentTime = Math.min(transportPosition, Math.max(0, videoDuration - 0.04));
      updateTimeline();
    }
  });
  loopProject.addEventListener('change', () => { crystalVideo.loop = loopProject.checked; });
  masterVolume.addEventListener('input', () => {
    const value = Number(masterVolume.value);
    masterVolumeValue.value = `${Math.round(value * 100)}%`;
    if (masterGain && audioContext) masterGain.gain.setTargetAtTime(value, audioContext.currentTime, 0.02);
  });
  noiseEnabled.addEventListener('change', () => updateNoiseSetting('enabled', noiseEnabled.checked));
  noiseLevel.addEventListener('input', () => updateNoiseSetting('level', Number(noiseLevel.value)));
  noiseTone.addEventListener('input', () => updateNoiseSetting('tone', Number(noiseTone.value)));
  noiseTone.addEventListener('change', restartIfPlaying);
  noisePulse.addEventListener('input', () => updateNoiseSetting('pulse', Number(noisePulse.value)));
  noisePulse.addEventListener('change', restartIfPlaying);
  noiseGrain.addEventListener('input', () => updateNoiseSetting('grain', Number(noiseGrain.value)));
  noiseGrain.addEventListener('change', restartIfPlaying);
  randomiseNoise.addEventListener('click', () => {
    activeCrystal.noise.seed = Math.floor(1000 + Math.random() * 8999);
    noiseValuesToUI();
    restartIfPlaying();
  });
  audioInput.addEventListener('change', () => loadFiles(audioInput.files));
  ['dragenter', 'dragover'].forEach((eventName) => dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add('dragging');
  }));
  ['dragleave', 'drop'].forEach((eventName) => dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove('dragging');
  }));
  dropZone.addEventListener('drop', (event) => loadFiles(event.dataTransfer.files));
  exportButton.addEventListener('click', exportMix);
  crystalVideo.addEventListener('loadedmetadata', () => {
    if (Number.isFinite(crystalVideo.duration) && crystalVideo.duration > 0) {
      activeCrystal.duration = crystalVideo.duration;
      timeline.max = String(activeCrystal.duration);
      durationLabel.textContent = `${activeCrystal.duration.toFixed(2)} seconds`;
      totalTimeLabel.textContent = formatTime(activeCrystal.duration);
      renderTabs();
      renderTracks();
      drawMasterWaveform();
    }
  });
  window.addEventListener('keydown', (event) => {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLButtonElement) return;
    if (event.code === 'Space') {
      event.preventDefault();
      playButton.click();
    } else if (event.key.toLowerCase() === 'r') {
      randomiseNoise.click();
    }
  });
  window.addEventListener('resize', () => {
    drawMasterWaveform();
    tracksElement.querySelectorAll('.track-waveform').forEach((canvas, index) => {
      drawBufferWaveform(canvas, activeCrystal.tracks[index]?.buffer);
    });
  });

  const heartbeat = () => {
    fetch('/api/agent/client', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        page: document.body.dataset.page,
        active: true,
        visible: document.visibilityState === 'visible',
        title: document.title,
        url: window.location.href,
        details: {
          crystal: activeCrystal.id,
          importedTracks: activeCrystal.tracks.length,
          playing,
          position: Number(currentPosition().toFixed(2)),
          duration: activeCrystal.duration,
          noiseEnabled: activeCrystal.noise.enabled
        }
      }),
      keepalive: true
    }).catch(() => {});
  };

  document.addEventListener('visibilitychange', heartbeat);
  window.addEventListener('pagehide', stopSources);
  window.getMorphogenesisPageDetails = () => ({
    crystal: activeCrystal.id,
    importedTracks: activeCrystal.tracks.length,
    playing,
    duration: activeCrystal.duration,
    noise: { ...activeCrystal.noise }
  });

  selectCrystal(activeCrystal);
  crystalVideo.src = `/05_shared_data/exhibition/${activeCrystal.id}/source/crystallization.mp4`;
  crystalVideo.load();
  timeline.max = String(activeCrystal.duration);
  durationLabel.textContent = `${activeCrystal.duration.toFixed(2)} seconds`;
  totalTimeLabel.textContent = formatTime(activeCrystal.duration);
  noiseValuesToUI();
  renderTabs();
  renderTracks();
  drawMasterWaveform();
  heartbeat();
  window.setInterval(heartbeat, 3000);
})();
