(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const connectionDot = $('connection-dot');
  const connectionLabel = $('connection-label');
  const lastUpdate = $('last-update');
  const currentState = $('current-state');
  const stateDescription = $('state-description');
  const centerTemperature = $('center-temperature');
  const minimumTemperature = $('minimum-temperature');
  const ambientTemperature = $('ambient-temperature');
  const sensorSource = $('sensor-source');
  const sensorPort = $('sensor-port');
  const sensorConnectButton = $('sensor-connect-button');
  const connectionSensorButton = $('connection-sensor-button');
  const connectionCameraButton = $('connection-camera-button');
  const cameraDeviceSelect = $('camera-device-select');
  const manualCoolingButton = $('manual-cooling-button');
  const manualCoolingStatus = $('manual-cooling-status');
  const manualCoolingTime = $('manual-cooling-time');
  const pagesGrid = $('pages-grid');
  const exhibitionPagesGrid = $('exhibition-pages-grid');
  const progressGrid = $('progress-grid');
  const currentRunNote = $('current-run-note');
  const projectList = $('project-list');
  const notebookBadge = $('notebook-badge');
  const notebookSummary = $('notebook-summary');
  const activityLog = $('activity-log');
  const notice = $('notice');
  const systemView = $('system-view');
  const monitorPhase = $('monitor-phase');
  const monitorCrystal = $('monitor-crystal');
  const monitorJobs = $('monitor-jobs');
  const startTestButton = $('start-test-button');
  const sampleButton = $('sample-button');
  const analysisButton = $('analysis-button');
  const startAnalysisButton = $('start-analysis-button');
  let noticeTimer = null;
  let lastHealth = null;
  let latestSession = null;
  let sensorPortOpen = false;
  const CAMERA_STORAGE_KEY = 'morphogenesis-camera-id';

  const stateCopy = {
    IDLE: 'System at rest / archive view',
    OBSERVING: 'Live observation requested',
    GROWING: 'Growth state requested / sensing remains physical',
    ARCHIVING: 'Recorded media and experiment memory'
  };

  const sectionNames = {
    websites: 'Exhibition websites',
    materialAnalysis: '01 / Material analysis',
    structural: '02 / Structural resonance',
    diffusion: '03 / Diffusion imagination',
    sharedData: 'Shared data',
    hardware: 'Hardware',
    touchdesigner: 'TouchDesigner / 3D',
    systemAgent: 'System Agent'
  };

  const showNotice = (message) => {
    notice.textContent = message;
    notice.classList.add('visible');
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => notice.classList.remove('visible'), 2300);
  };

  const badge = (text, tone = '') => {
    const element = document.createElement('span');
    element.className = `badge ${tone}`.trim();
    element.textContent = text;
    return element;
  };

  const renderPages = (pages) => {
    pagesGrid.replaceChildren();
    exhibitionPagesGrid.replaceChildren();
    pages
      .filter((page) => !['material_edge', 'material_motion'].includes(page.key))
      .map((page) => page.key === 'resonance_attention'
        ? { ...page, label: 'Display / Only Small Screen — Rotating Analysis' }
        : page)
      .forEach((page) => {
      const card = document.createElement('article');
      card.className = 'page-card';
      const header = document.createElement('div');
      header.className = 'page-card-header';
      const title = document.createElement('h3');
      title.textContent = page.label;
      header.append(title, badge(
        !page.ready ? 'Error' : page.open ? (page.visible ? 'Open / visible' : 'Open') : 'Ready / closed',
        !page.ready ? 'error' : page.open ? 'good' : 'warn'
      ));
      const description = document.createElement('p');
      if (!page.ready) description.textContent = 'Required page file is missing.';
      else if (page.key === 'current' && page.open) {
        const detail = page.details || {};
        description.textContent = detail.cameraActive
          ? `Raw camera / ${detail.cameraLabel || 'connected'}`
          : detail.cameraError || 'Raw camera page connected / camera waiting';
      } else if (page.key === 'live' && page.open) {
        const detail = page.details || {};
        description.textContent = `${detail.source || 'Live client connected'} · ${detail.sensor || 'Sensor unknown'}`;
      } else if (page.key === 'resonance_attention') {
        const detail = page.details || {};
        description.textContent = page.open
          ? `${detail.crystal?.replaceAll('_', ' ') || 'Current crystal'} / ${detail.output || 'synchronized output'}${detail.playing ? ' / playing' : ' / waiting'}`
          : 'Only small-screen webpage / rotates Attention Map, Spacetime Row 200 and Edge for the current crystal.';
      } else if (['medium_display', 'medium_display_2'].includes(page.key)) {
        const detail = page.details || {};
        const scene = detail.scene === 'diffusion' ? 'Diffusion Imagination' : 'Structural Resonance';
        description.textContent = page.open
          ? `${scene} / synchronized rotation every ${detail.rotationSeconds || 30}s`
          : page.key === 'medium_display_2'
            ? 'Second medium-screen identity / synchronized companion with reliable Diffusion playback.'
            : 'Primary medium-screen page / Structural Resonance and live Diffusion Imagination.';
      } else if (page.key === 'bgm_workbench') {
        const detail = page.details || {};
        description.textContent = page.open
          ? `${detail.crystal?.replaceAll('_', ' ') || 'Current crystal'} / ${detail.importedTracks || 0} imported layers${detail.playing ? ' / playing' : ''}`
          : 'Local audio mixer / import sound layers, shape electrical interference and export a synchronized WAV.';
      } else if (page.key === 'spacetime_row_200') {
        const detail = page.details || {};
        description.textContent = page.open
          ? `${detail.crystal?.replaceAll('_', ' ') || 'Current crystal'} / Row 200${detail.playing ? ' / playing' : ' / waiting'}`
          : 'Full-screen space-time display / source sampling row 200 / synchronized crystal.';
      } else if (page.key === 'crystal_cut_preview') {
        description.textContent = 'Crystal 01 timing preview / Source 0–5s / Edge 5–7s / Threshold 7–9s / Motion 9–11s.';
      } else if (page.key === 'stabilization_preview') {
        description.textContent = 'Crystal 01 original / stabilized comparison with synchronized Material outputs.';
      } else if (page.key === 'diffusion' && page.open) {
        const detail = page.details || {};
        const worker = detail.workerConnected ? 'GPU worker ready' : `GPU worker ${detail.workerStatus || 'offline'}`;
        const stream = detail.streaming ? `streaming${detail.fps ? ` / ${Number(detail.fps).toFixed(1)} fps` : ''}` : 'not streaming';
        description.textContent = `${worker} · ${stream} · ${detail.source || 'source unknown'}`;
      } else if (page.open) description.textContent = 'The page is reporting to Morphogenesis Agent.';
      else description.textContent = 'Files are ready. The page is not currently open.';
      const footer = document.createElement('footer');
      const path = document.createElement('span');
      path.className = 'eyebrow';
      path.textContent = page.key;
      const link = document.createElement('a');
      link.href = page.url;
      link.target = '_blank';
      link.rel = 'noopener';
      link.textContent = 'Open page ↗';
      footer.append(path, link);
      card.append(header, description, footer);
      const targetGrid = page.key.startsWith('exhibition_') ? exhibitionPagesGrid : pagesGrid;
      targetGrid.append(card);
    });
  };

  const renderProject = (project) => {
    projectList.replaceChildren();
    Object.entries(project.sections).forEach(([key, section]) => {
      const row = document.createElement('div');
      row.className = 'diagnostic-row';
      const name = document.createElement('strong');
      name.textContent = sectionNames[key] || key;
      const count = document.createElement('span');
      count.textContent = section.exists ? `${section.fileCount} files` : 'Missing';
      if (!section.exists) count.style.color = 'var(--red)';
      row.append(name, count);
      projectList.append(row);
    });
  };

  const renderConnections = (connections) => {
    const devices = {
      agent: { connected: connections.agent, yes: 'Running', no: 'Offline' },
      live: { connected: connections.livePage, yes: 'Open / reporting', no: 'Not open' },
      arduino: { connected: connections.arduino, yes: 'Connected / receiving data', no: 'Disconnected' },
      camera: { connected: connections.camera, yes: 'Connected in Live page', no: 'Disconnected' },
      ai: { connected: connections.creativeAI, yes: 'Configured / ready', no: 'API key not configured' }
    };
    Object.entries(devices).forEach(([key, device]) => {
      $(`connection-${key}`).textContent = device.connected ? device.yes : device.no;
      $(`connection-${key}-dot`).className = `device-dot ${device.connected ? 'connected' : 'disconnected'}`;
    });
  };

  const renderCurrentProgress = (session) => {
    progressGrid.replaceChildren();
    const isCurrentRun = Boolean(
      session?.runnerActive
      || (
        ['live_capture', 'recorded_rehearsal'].includes(session?.kind)
        && !['idle', 'archive'].includes(session?.phase)
      )
    );
    const jobs = isCurrentRun ? (session?.jobs || {}) : {};
    const steps = [
      ['detection', 'Formation detection'],
      ['trim', 'Video capture'],
      ['material', '01 / Material'],
      ['structural', '02 / Structural'],
      ['diffusion', '03 / Diffusion']
    ];
    currentRunNote.textContent = session?.kind === 'analysis_rehearsal'
      ? `Analysis rehearsal · ${String(session.phase || 'starting').replaceAll('_', ' ')} · ${Math.max(0, Math.ceil(Number(session.presentation?.remainingSeconds || 0)))}s`
      : session?.kind === 'archive_cycle' && session?.crystal
      ? `Archive loop · ${session.crystal.replaceAll('_', ' ')} · repeat ${session.archiveSequence?.repeat || 1}/${session.archiveSequence?.repeatTotal || 5} · next crystal in ${Math.max(0, Math.ceil(Number(session.archiveSequence?.remainingSeconds || 0)))}s`
      : isCurrentRun && session?.crystal
      ? `${session.crystal.replaceAll('_', ' ')} · ${String(session.phase || 'idle').replaceAll('_', ' ')}`
      : 'Waiting for cooling start';
    steps.forEach(([key, label]) => {
      const job = jobs[key] || { state: 'standby', progress: 0, message: 'Waiting' };
      const percent = Math.max(0, Math.min(100, Math.round(Number(job.progress || 0) * 100)));
      const card = document.createElement('article');
      card.className = 'progress-card';
      const header = document.createElement('header');
      const identity = document.createElement('div');
      const title = document.createElement('h3');
      title.textContent = label;
      const stage = document.createElement('p');
      stage.className = 'stage';
      stage.textContent = String(job.state || 'standby').replaceAll('_', ' ');
      identity.append(title, stage);
      const value = document.createElement('span');
      value.className = 'progress-value';
      value.textContent = `${percent}%`;
      header.append(identity, value);
      const track = document.createElement('div');
      track.className = 'progress-track';
      const fill = document.createElement('div');
      fill.className = 'progress-fill';
      fill.style.width = `${percent}%`;
      track.append(fill);
      const list = document.createElement('div');
      list.className = 'milestone-list';
      const status = document.createElement('div');
      status.className = `milestone ${percent === 100 ? 'complete' : ''}`.trim();
      status.textContent = job.message || 'Waiting for this run';
      list.append(status);
      card.append(header, track, list);
      progressGrid.append(card);
    });
  };

  const renderNotebooks = (notebooks) => {
    const healthy = notebooks.invalid.length === 0;
    notebookBadge.className = `badge ${healthy ? 'good' : 'error'}`;
    notebookBadge.textContent = healthy ? 'All valid' : `${notebooks.invalid.length} errors`;
    notebookSummary.replaceChildren();
    const count = document.createElement('div');
    count.className = 'notebook-count';
    count.textContent = `${notebooks.valid}/${notebooks.total}`;
    const copy = document.createElement('p');
    copy.textContent = healthy
      ? 'Every notebook could be parsed successfully when the Agent started.'
      : 'One or more notebooks could not be parsed. See the paths below.';
    notebookSummary.append(count, copy);
    if (!healthy) {
      const errors = document.createElement('div');
      errors.className = 'notebook-errors';
      errors.textContent = notebooks.invalid.map((item) => item.path).join(' · ');
      notebookSummary.append(errors);
    }
  };

  const renderLogs = (logs) => {
    activityLog.replaceChildren();
    [...logs].reverse().slice(0, 12).forEach((entry) => {
      const row = document.createElement('div');
      row.className = 'log-row';
      const time = document.createElement('time');
      const date = new Date(entry.timestamp);
      time.textContent = Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('en-GB');
      const event = document.createElement('strong');
      event.textContent = String(entry.event || '').replaceAll('_', ' ');
      const detail = document.createElement('span');
      detail.textContent = entry.from && entry.to ? `${entry.from} → ${entry.to}` : entry.state || '';
      row.append(time, event, detail);
      activityLog.append(row);
    });
  };

  const monitorJobNames = {
    detection: 'Formation',
    trim: 'Capture',
    material: '01 / Material',
    structural: '02 / Structural',
    diffusion: '03 / Diffusion'
  };

  const renderSession = (session) => {
    latestSession = session;
    renderCurrentProgress(session);
    const phase = String(session?.phase || 'idle');
    monitorPhase.textContent = phase.replaceAll('_', ' ');
    monitorPhase.className = `badge ${
      phase === 'error' ? 'error' : phase === 'outputs_ready' ? 'good' : 'warn'
    }`;
    monitorCrystal.textContent = session?.kind === 'analysis_rehearsal'
      ? `Internal source sequence / ${String(session.phase || 'starting').replaceAll('_', ' ')}`
      : session?.crystal
      ? session.kind === 'archive_cycle'
        ? `Archive loop / ${String(session.archiveSequence?.index || 1).padStart(2, '0')} of ${String(session.archiveSequence?.total || 3).padStart(2, '0')} / repeat ${session.archiveSequence?.repeat || 1} of ${session.archiveSequence?.repeatTotal || 5} / ${session.crystal.replaceAll('_', ' ')}`
        : `${session.crystal.replaceAll('_', ' ')} / ${session.runnerActive ? 'processing' : 'complete'}`
      : 'Waiting for cooling start';
    const sampleVisible = session?.kind !== 'archive_cycle';
    const sampleDisabled = Boolean(session?.runnerActive) || !sampleVisible;
    startTestButton.disabled = sampleDisabled;
    sampleButton.disabled = sampleDisabled;
    analysisButton.disabled = false;
    startAnalysisButton.disabled = false;
    analysisButton.textContent = session?.kind === 'analysis_rehearsal'
      ? 'Stop analysis rehearsal'
      : 'Start analysis rehearsal';
    startAnalysisButton.textContent = session?.kind === 'analysis_rehearsal'
      ? 'Stop analysis'
      : 'Start analysis';
    startTestButton.textContent = session?.runnerActive
      ? 'Analysis finishing…'
      : sampleVisible ? 'Start archive loop' : 'Archive loop running';
    sampleButton.textContent = session?.runnerActive
      ? 'Analysis finishing...'
      : sampleVisible ? 'Start archive loop' : 'Archive loop running';

    const jobs = session?.jobs || {};
    monitorJobs.replaceChildren();
    Object.entries(monitorJobNames).forEach(([key, label]) => {
      const job = jobs[key] || { state: 'standby', progress: 0 };
      const item = document.createElement('div');
      const state = String(job.state || 'standby');
      item.className = `monitor-job ${state}`;
      const name = document.createElement('strong');
      name.textContent = label;
      name.title = job.message || '';
      const value = document.createElement('span');
      const percent = Math.round(Number(job.progress || 0) * 100);
      value.textContent = `${state.replaceAll('_', ' ')} / ${percent}%`;
      item.append(name, value);
      monitorJobs.append(item);
    });

    $('monitor-live-state').textContent = ['starting', 'observing', 'formation_detected'].includes(phase)
      ? 'Simulated input / awaiting formation'
      : phase === 'idle' ? 'Input' : 'Replay';
    $('monitor-material-state').textContent = jobs.material?.state || 'standby';
    $('monitor-structural-state').textContent = jobs.structural?.state || 'standby';
    $('monitor-diffusion-state').textContent = jobs.diffusion?.state || 'standby';
  };

  const refreshSession = async () => {
    try {
      const response = await fetch('/api/agent/session', { cache: 'no-store' });
      if (!response.ok) throw new Error('Session request failed');
      renderSession(await response.json());
    } catch (_) {
      renderSession({ phase: 'offline', jobs: {} });
    }
  };

  const loadMonitorFrames = () => {
    systemView.querySelectorAll('iframe[data-src]').forEach((frame) => {
      if (!frame.src || frame.src === 'about:blank') frame.src = frame.dataset.src;
    });
  };

  const openSystemView = () => {
    systemView.hidden = false;
    document.body.style.overflow = 'hidden';
    loadMonitorFrames();
    refreshSession();
  };

  const closeSystemView = () => {
    systemView.hidden = true;
    document.body.style.overflow = '';
    systemView.querySelectorAll('iframe[data-src]').forEach((frame) => {
      frame.src = 'about:blank';
    });
  };

  const reloadSystemView = () => {
    const revision = Date.now();
    systemView.querySelectorAll('iframe[data-src]').forEach((frame) => {
      const url = new URL(frame.dataset.src, window.location.origin);
      url.searchParams.set('monitorRevision', String(revision));
      frame.src = url.href;
    });
    showNotice('System views reloaded.');
  };

  const startArchiveCycle = async () => {
    startTestButton.disabled = true;
    sampleButton.disabled = true;
    try {
      const response = await fetch('/api/agent/archive-cycle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'start' })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Archive start failed');
      renderSession(result);
      startTestButton.textContent = 'Archive loop running';
      sampleButton.textContent = 'Archive loop running';
      reloadSystemView();
      showNotice('Archive loop started at ice crystal 01.');
      window.setTimeout(refreshSession, 1200);
    } catch (error) {
      showNotice(error.message || 'Archive loop could not be started.');
      startTestButton.disabled = Boolean(latestSession?.runnerActive);
      sampleButton.disabled = Boolean(latestSession?.runnerActive);
    }
  };

  const toggleAnalysisRehearsal = async () => {
    const action = latestSession?.kind === 'analysis_rehearsal' ? 'stop' : 'start';
    analysisButton.disabled = true;
    startAnalysisButton.disabled = true;
    try {
      const response = await fetch('/api/agent/analysis-rehearsal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `Analysis rehearsal could not ${action}`);
      renderSession(result);
      if (action === 'start') reloadSystemView();
      showNotice(action === 'stop'
        ? 'Rehearsal stopped. All displays and Diffusion are entering standby.'
        : 'Analysis rehearsal started from ice crystal 01. Live and Control Room are synchronized.');
      window.setTimeout(refreshSession, 500);
    } catch (error) {
      showNotice(error.message || 'Analysis rehearsal could not start.');
    } finally {
      analysisButton.disabled = false;
      startAnalysisButton.disabled = false;
    }
  };

  const renderHealth = (health) => {
    lastHealth = health;
    const agent = health.agent;
    connectionDot.className = 'connection-dot online';
    connectionLabel.textContent = 'Agent online';
    lastUpdate.textContent = `Updated ${new Date().toLocaleTimeString('en-GB')}`;
    currentState.textContent = agent.state;
    stateDescription.textContent = stateCopy[agent.state] || 'Unknown state';
    const sensing = health.sensing;
    centerTemperature.textContent = sensing.centerTemperature === null
      ? '--.-'
      : Number(sensing.centerTemperature).toFixed(1);
    minimumTemperature.textContent = sensing.minimumTemperature === null
      ? '--.-'
      : Number(sensing.minimumTemperature).toFixed(1);
    ambientTemperature.textContent = sensing.ambientTemperature === null
      ? '--.-'
      : Number(sensing.ambientTemperature).toFixed(1);
    sensorSource.textContent = sensing.connected
      ? `MLX90640 ${sensing.port || ''} / live thermal data`
      : sensing.portOpen
        ? sensing.error || 'Mega connected / waiting for thermal frame'
        : sensing.error || 'Arduino disconnected / no readings';
    $('sensor-source-dot').className = sensing.connected ? '' : 'disconnected';
    sensorPortOpen = Boolean(sensing.portOpen);
    sensorConnectButton.textContent = sensorPortOpen ? 'Disconnect Mega' : 'Connect Mega';
    sensorPort.disabled = sensorPortOpen;
    const manualCooling = agent.manualCooling || {};
    manualCoolingStatus.textContent = manualCooling.active
      ? 'Cooling started manually'
      : 'Not cooling';
    manualCoolingStatus.className = manualCooling.active ? 'active' : '';
    manualCoolingTime.textContent = manualCooling.active && manualCooling.startedAt
      ? `Started ${new Date(manualCooling.startedAt).toLocaleString('en-GB')}`
      : 'No manual cooling recorded';
    manualCoolingButton.textContent = manualCooling.active
      ? 'Mark cooling stopped'
      : 'Mark cooling started';
    manualCoolingButton.dataset.action = manualCooling.active ? 'stop' : 'start';
    document.querySelectorAll('[data-state]').forEach((button) => {
      button.classList.toggle('active', button.dataset.state === agent.state);
    });
    $('hardware-badge').textContent = agent.hardwareEnabled ? 'Hardware enabled' : 'Hardware off';
    $('hardware-badge').className = `badge ${agent.hardwareEnabled ? 'error' : 'protected'}`;
    $('safety-title').textContent = agent.hardwareEnabled ? 'Hardware output enabled' : 'Hardware protected';
    $('safety-copy').textContent = agent.hardwareEnabled
      ? 'Verify Arduino safety and physical emergency stop'
      : 'V0 observation mode — physical outputs disabled';
    renderConnections(health.connections);
    connectionSensorButton.textContent = sensorPortOpen ? 'Disconnect' : 'Connect Mega';
    connectionSensorButton.disabled = !sensorPortOpen && !sensorPort.value;
    const livePage = (health.pages || []).find((page) => page.key === 'live');
    const cameraError = livePage?.details?.cameraError;
    if (!health.connections.camera && cameraError) {
      $('connection-camera').textContent = cameraError;
    }
    connectionCameraButton.textContent = health.connections.camera
      ? 'Open ice crystallizing camera'
      : 'Connect camera';
    renderPages(health.pages);
    renderProject(health.project);
    renderNotebooks(health.notebooks);
  };

  const refresh = async (announce = false) => {
    try {
      const [healthResponse, logsResponse] = await Promise.all([
        fetch('/api/agent/health', { cache: 'no-store' }),
        fetch('/api/agent/logs', { cache: 'no-store' })
      ]);
      if (!healthResponse.ok || !logsResponse.ok) throw new Error('Agent health request failed');
      renderHealth(await healthResponse.json());
      renderLogs((await logsResponse.json()).logs || []);
      if (announce) showNotice('System check complete.');
    } catch (_) {
      connectionDot.className = 'connection-dot offline';
      connectionLabel.textContent = 'Agent offline';
      lastUpdate.textContent = 'Start Morphogenesis Agent to reconnect';
      if (!lastHealth) currentState.textContent = 'OFFLINE';
    }
  };

  const setState = async (state) => {
    try {
      const response = await fetch('/api/agent/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state })
      });
      if (!response.ok) throw new Error('Command rejected');
      showNotice(state === 'IDLE' ? 'System returned to safe idle.' : `Agent changed to ${state}.`);
      await refresh();
    } catch (_) {
      showNotice('Agent command failed. Check the Agent window.');
    }
  };

  const setManualCooling = async () => {
    const action = manualCoolingButton.dataset.action || 'start';
    manualCoolingButton.disabled = true;
    try {
      const response = await fetch('/api/agent/manual-cooling', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Manual cooling record failed');
      showNotice(action === 'start'
        ? 'Manual cooling started. Peltier remains under physical control.'
        : 'Manual cooling stopped.');
      await refresh();
    } catch (error) {
      showNotice(error.message || 'Manual cooling record failed.');
    } finally {
      manualCoolingButton.disabled = false;
    }
  };

  const refreshSerialPorts = async () => {
    try {
      const response = await fetch('/api/agent/serial-ports', { cache: 'no-store' });
      if (!response.ok) throw new Error('Serial ports unavailable');
      const ports = (await response.json()).ports || [];
      const selected = sensorPort.value;
      sensorPort.replaceChildren();
      ports.forEach((port) => {
        const option = document.createElement('option');
        option.value = port.device;
        option.textContent = `${port.device} / ${port.description}`;
        sensorPort.append(option);
      });
      if (!ports.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No serial device found';
        sensorPort.append(option);
      } else if (ports.some((port) => port.device === selected)) {
        sensorPort.value = selected;
      }
      sensorConnectButton.disabled = !sensorPortOpen && !ports.length;
      connectionSensorButton.disabled = !sensorPortOpen && !ports.length;
    } catch (_) {
      sensorConnectButton.disabled = true;
    }
  };

  const isPhysicalCamera = (device) => {
    const label = device.label.toLowerCase();
    return !/obs|virtual camera|meta quest/.test(label);
  };

  const refreshCameraDevices = async () => {
    const saved = localStorage.getItem(CAMERA_STORAGE_KEY) || cameraDeviceSelect.value;
    cameraDeviceSelect.replaceChildren();
    const automatic = document.createElement('option');
    automatic.value = '';
    automatic.textContent = 'USB camera (auto)';
    cameraDeviceSelect.append(automatic);
    if (!navigator.mediaDevices?.enumerateDevices) {
      automatic.textContent = 'Camera unavailable in this browser';
      cameraDeviceSelect.disabled = true;
      return;
    }
    try {
      const devices = (await navigator.mediaDevices.enumerateDevices())
        .filter((device) => device.kind === 'videoinput')
        .filter(isPhysicalCamera);
      const selectableDevices = devices.filter((device) => device.deviceId);
      selectableDevices.forEach((device, index) => {
        const option = document.createElement('option');
        option.value = device.deviceId;
        option.textContent = device.label || `Camera ${index + 1}`;
        cameraDeviceSelect.append(option);
      });
      if (!devices.length) automatic.textContent = 'No camera visible / use Chrome';
      else if (!selectableDevices.length) automatic.textContent = 'Allow camera once to list devices';
      cameraDeviceSelect.disabled = false;
      cameraDeviceSelect.value = selectableDevices.some((device) => device.deviceId === saved) ? saved : '';
    } catch (_) {
      automatic.textContent = 'Camera list unavailable';
      cameraDeviceSelect.disabled = true;
    }
  };

  const setSensorConnection = async () => {
    const action = sensorPortOpen ? 'disconnect' : 'connect';
    sensorConnectButton.disabled = true;
    try {
      const response = await fetch('/api/agent/sensor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, port: sensorPort.value })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Sensor command failed');
      showNotice(action === 'connect'
        ? `Mega opened on ${sensorPort.value}; waiting for MLX90640 frames.`
        : 'Mega disconnected.');
      await refresh();
      await refreshSerialPorts();
    } catch (error) {
      showNotice(error.message || 'Sensor connection failed.');
    } finally {
      sensorConnectButton.disabled = false;
    }
  };

  const requestCameraConnection = () => {
    const deviceId = cameraDeviceSelect.value;
    if (deviceId) localStorage.setItem(CAMERA_STORAGE_KEY, deviceId);
    try {
      const channel = new BroadcastChannel('morphogenesis-control');
      channel.postMessage({ type: 'start-camera', deviceId });
      channel.close();
    } catch (_) {
      // The query parameter provides a fallback when BroadcastChannel is unavailable.
    }
    const liveUrl = new URL('/00_websites/live/', window.location.origin);
    liveUrl.searchParams.set('startCamera', '1');
    if (deviceId) liveUrl.searchParams.set('camera', deviceId);
    window.open(liveUrl, 'morphogenesis-live');
    showNotice('Camera request sent. Allow camera access in the Ice Crystallizing page if prompted.');
  };

  document.querySelectorAll('[data-state]').forEach((button) => {
    button.addEventListener('click', () => setState(button.dataset.state));
  });
  $('safe-stop').addEventListener('click', () => setState('IDLE'));
  manualCoolingButton.addEventListener('click', setManualCooling);
  sensorConnectButton.addEventListener('click', setSensorConnection);
  connectionSensorButton.addEventListener('click', setSensorConnection);
  connectionCameraButton.addEventListener('click', requestCameraConnection);
  cameraDeviceSelect.addEventListener('change', () => {
    if (cameraDeviceSelect.value) localStorage.setItem(CAMERA_STORAGE_KEY, cameraDeviceSelect.value);
  });
  $('refresh-button').addEventListener('click', () => refresh(true));
  $('system-view-button').addEventListener('click', openSystemView);
  $('close-view-button').addEventListener('click', closeSystemView);
  $('reload-view-button').addEventListener('click', reloadSystemView);
  startTestButton.addEventListener('click', startArchiveCycle);
  sampleButton.addEventListener('click', startArchiveCycle);
  analysisButton.addEventListener('click', toggleAnalysisRehearsal);
  startAnalysisButton.addEventListener('click', toggleAnalysisRehearsal);

  refresh();
  refreshSerialPorts();
  refreshCameraDevices();
  refreshSession();
  window.setInterval(refresh, 2000);
  window.setInterval(refreshSession, 1500);
  window.addEventListener('focus', refreshCameraDevices);
  navigator.mediaDevices?.addEventListener('devicechange', refreshCameraDevices);
  if (new URLSearchParams(window.location.search).get('systemView') === '1') {
    openSystemView();
  }
})();
