(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const video = $('source-video');
  const jobOrder = ['capture', 'detection', 'trim', 'material', 'structural', 'diffusion'];
  const jobLabels = {
    capture: 'Camera capture',
    detection: 'Formation detection',
    trim: 'Automatic edit',
    material: '01 / Material',
    structural: '02 / Structural',
    diffusion: '03 / Diffusion',
  };
  let session = null;
  const consoleSeen = new Set();
  const consoleQueue = [];
  let lastHealthSignature = '';

  const formatSeconds = (value) => value !== null && value !== undefined && Number.isFinite(Number(value))
    ? `${Number(value).toFixed(1)} s`
    : '--.- s';

  const renderJobs = (jobs = {}, health = null, sessionId = '') => {
    const diffusionPage = health?.pages?.find((page) => page.key === 'diffusion');
    const merged = { ...jobs };
    if (merged.diffusion
      && diffusionPage?.open
      && diffusionPage.details?.sessionId === sessionId) {
      const details = diffusionPage.details || {};
      merged.diffusion = {
        ...merged.diffusion,
        state: details.hasGeneratedFrame
          ? 'complete'
          : (details.streaming ? 'running' : (details.workerConnected ? 'ready' : merged.diffusion.state)),
        progress: details.hasGeneratedFrame ? 1 : (details.streaming ? 0.72 : merged.diffusion.progress),
        message: details.hasGeneratedFrame
          ? `Live StreamDiffusion connected${details.fps ? ` / ${details.fps.toFixed(1)} fps` : ''}`
          : details.streaming
          ? `StreamDiffusion is generating${details.fps ? ` / ${details.fps.toFixed(1)} fps` : ''}`
          : (details.workerConnected ? 'GPU worker ready / waiting to stream' : merged.diffusion.message),
      };
    }
    $('jobs').replaceChildren(...jobOrder.map((key) => {
      const job = merged[key] || { state: 'waiting', progress: 0, message: 'Waiting' };
      const article = document.createElement('article');
      article.className = `job ${job.state}`;
      const progress = Math.max(0, Math.min(1, Number(job.progress || 0)));
      article.innerHTML = `
        <header><span>${jobLabels[key]}</span><strong>${String(job.state).replace('_', ' ')}</strong></header>
        <p></p>
        <div class="bar"><span style="width:${progress * 100}%"></span></div>
      `;
      article.querySelector('p').textContent = job.message || '';
      return article;
    }));
  };

  const queueConsole = (items) => {
    items.forEach((item) => {
      const key = `${item.at}|${item.channel}|${item.message}`;
      if (consoleSeen.has(key)) return;
      consoleSeen.add(key);
      consoleQueue.push(item);
    });
  };

  const fallbackConsole = (current) => {
    const at = current.updatedAt || new Date().toISOString();
    const lines = [
      { at: current.createdAt || at, channel: 'agent', message: `boot session ${current.id}` },
      { at: current.createdAt || at, channel: 'capture', message: `mount ${current.sourceUrl}` },
      {
        at,
        channel: 'playback',
        message: `revision ${current.playback?.revision || 0} / ${current.playback?.stage || 'unavailable'} / ${current.playback?.durationSeconds || 0}s`,
      },
    ];
    if (current.detection && current.detection.onsetSeconds !== null) {
      lines.push(
        { at, channel: 'vision', message: 'sample rate 5 Hz / baseline texture model locked' },
        { at, channel: 'vision', message: 'candidate change persisted across 1.4 second validation window' },
        {
          at,
          channel: 'vision',
          message: `onset ${current.detection.onsetSeconds}s / confidence ${current.detection.confidence}`,
        },
        {
          at,
          channel: 'edit',
          message: `ring-buffer lookup -> retain frames from ${current.detection.trimStartSeconds}s`,
        },
      );
    }
    (current.events || []).forEach((event) => lines.push({
      at: event.at,
      channel: event.kind,
      message: event.message,
    }));
    Object.entries(current.jobs || {}).forEach(([channel, job]) => {
      lines.push({
        at: job.updatedAt || at,
        channel,
        message: `${job.state} ${String(Math.round(Number(job.progress || 0) * 100)).padStart(3, '0')}% / ${job.message}`,
      });
      (job.outputUrls || []).forEach((url, index) => {
        const filename = String(url).split('/').pop() || '';
        const method = filename.match(/^\d+_([a-z]+)/i)?.[1] || channel;
        const operations = {
          edge: 'Canny gradient field / thresholds 35:110',
          threshold: 'adaptive Gaussian threshold / local block 31',
          spacetime: 'centre-row sampling / temporal row accumulation',
          motion: 'absolute frame difference / temporal decay 0.94',
        };
        lines.push(
          {
            at: job.updatedAt || at,
            channel: method,
            message: `restore completed worker / ${operations[method] || 'frame transformation'}`,
          },
          {
            at: job.updatedAt || at,
            channel: method,
            message: 'frame loop complete / browser VP8 writer flushed',
          },
          {
            at: job.updatedAt || at,
            channel: method,
            message: `output[${String(index).padStart(2, '0')}] ${url}`,
          },
        );
      });
      if (job.outputUrl) lines.push({
        at: job.updatedAt || at,
        channel,
        message: `output ${job.outputUrl}`,
      });
    });
    return lines;
  };

  const appendConsoleLine = (item) => {
    const line = document.createElement('div');
    line.className = 'console-line';
    const time = document.createElement('time');
    const channel = document.createElement('b');
    const message = document.createElement('span');
    time.textContent = `[${new Date(item.at).toLocaleTimeString()}]`;
    channel.textContent = `[${item.channel || 'process'}]`;
    message.textContent = item.message || '';
    line.append(time, channel, message);
    $('console-output').append(line);
    while ($('console-output').children.length > 220) {
      $('console-output').firstElementChild?.remove();
    }
    $('console-output').scrollTop = $('console-output').scrollHeight;
  };

  const refreshHealth = async () => {
    if (!session) return;
    try {
      const response = await fetch('/api/agent/health', { cache: 'no-store' });
      if (response.ok) {
        const health = await response.json();
        renderJobs(session.jobs, health, session.id);
        const watched = (health.pages || [])
          .filter((page) => ['material', 'structural', 'diffusion', 'backstage'].includes(page.key));
        const signature = JSON.stringify(watched.map((page) => [
          page.key,
          page.open,
          page.details?.source,
          page.details?.streaming,
          page.details?.workerStatus,
        ]));
        if (signature !== lastHealthSignature) {
          lastHealthSignature = signature;
          queueConsole(watched.map((page) => ({
            at: new Date().toISOString(),
            channel: 'page',
            message: `${page.key} / ${page.open ? 'connected' : 'offline'} / ${page.details?.source || page.details?.stage || 'heartbeat only'}`,
          })));
        }
      }
    } catch {
      renderJobs(session.jobs, null, session.id);
    }
  };

  const applySession = async (nextSession) => {
    session = nextSession;
    const playback = session.playback;
    $('phase').textContent = String(session.phase || 'idle').replaceAll('_', ' ').toUpperCase();
    $('source-name').textContent = `${session.crystal.replaceAll('_', ' ')} / ${playback?.stage || 'waiting'}`;
    $('onset').textContent = formatSeconds(session.detection?.onsetSeconds);
    $('trim').textContent = formatSeconds(session.detection?.trimStartSeconds);
    $('updated').textContent = session.updatedAt
      ? new Date(session.updatedAt).toLocaleTimeString()
      : 'not connected';
    $('state-dot').className = session.phase === 'error' ? 'error' : 'active';
    if (playback?.url) await window.syncMorphogenesisVideo?.(video, session, playback.url);
    renderJobs(session.jobs, null, session.id);
    queueConsole(session.console?.length ? session.console : fallbackConsole(session));
    $('events').replaceChildren(...[...(session.events || [])].reverse().map((event) => {
      const item = document.createElement('li');
      const time = new Date(event.at).toLocaleTimeString();
      item.innerHTML = `<time>${time}</time><b></b><span></span>`;
      item.querySelector('b').textContent = event.kind;
      item.querySelector('span').textContent = event.message;
      return item;
    }));
    refreshHealth();
  };

  window.addEventListener('morphogenesis-session', (event) => applySession(event.detail));
  window.addEventListener('morphogenesis-session-tick', async (event) => {
    session = event.detail;
    await window.syncMorphogenesisVideo?.(video, session, session.playback?.url);
  });

  window.getMorphogenesisPageDetails = () => ({
    session: session?.id || null,
    phase: session?.phase || 'idle',
    crystal: session?.crystal || null,
  });

  window.setInterval(() => {
    if (!session?.playback?.startedAtEpochMs) return;
    const seconds = Math.max(0, (Date.now() - session.playback.startedAtEpochMs) / 1000);
    $('clock').textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
  }, 250);
  window.setInterval(refreshHealth, 2000);
  window.setInterval(() => {
    const next = consoleQueue.shift();
    if (next) appendConsoleLine(next);
    else if (!$('console-output').querySelector('.console-cursor')) {
      const cursor = document.createElement('i');
      cursor.className = 'console-cursor';
      $('console-output').append(cursor);
    }
    const cursor = $('console-output').querySelector('.console-cursor');
    if (next && cursor) cursor.remove();
  }, 58);
})();
