(() => {
  'use strict';

  const videos = {
    source: document.getElementById('source-video'),
    edge: document.getElementById('edge-video'),
    threshold: document.getElementById('threshold-video'),
    motion: document.getElementById('motion-video')
  };
  const master = videos.source;
  const flash = document.getElementById('cut-flash');
  const readout = document.getElementById('cut-readout');
  const cuts = [
    { from: 0, to: 5, layer: 'source' },
    { from: 5, to: 7, layer: 'motion' },
    { from: 7, to: 9, layer: 'edge' },
    { from: 9, to: 11, layer: 'threshold' },
    { from: 11, to: Infinity, layer: 'source' }
  ];
  let activeLayer = 'source';
  let animationFrame = 0;

  Object.values(videos).forEach((video) => {
    video.defaultMuted = true;
    video.muted = true;
    video.playsInline = true;
    video.loop = true;
  });

  const layerAt = (time) => cuts.find((cut) => time >= cut.from && time < cut.to)?.layer || 'source';

  const fireFlash = () => {
    flash.classList.remove('fire');
    void flash.offsetWidth;
    flash.classList.add('fire');
  };

  const showLayer = (name, initial = false) => {
    if (name === activeLayer && !initial) return;
    Object.entries(videos).forEach(([key, video]) => video.classList.toggle('active', key === name));
    if (!initial) fireFlash();
    activeLayer = name;
  };

  const syncFollowers = (force = false) => {
    const time = master.currentTime || 0;
    ['edge', 'threshold', 'motion'].forEach((name) => {
      const follower = videos[name];
      const difference = time - (follower.currentTime || 0);
      if (force || Math.abs(difference) > 0.09) {
        if (follower.readyState >= HTMLMediaElement.HAVE_METADATA) follower.currentTime = time;
        follower.playbackRate = 1;
      } else {
        follower.playbackRate = Math.max(0.97, Math.min(1.03, 1 + difference * 0.18));
      }
    });
  };

  const render = () => {
    const time = master.currentTime || 0;
    showLayer(layerAt(time));
    syncFollowers();
    readout.value = `${activeLayer.toUpperCase()} / ${time.toFixed(1).padStart(4, '0')}`;
    animationFrame = window.requestAnimationFrame(render);
  };

  const playAll = async () => {
    await Promise.allSettled(Object.values(videos).map((video) => video.play()));
    window.cancelAnimationFrame(animationFrame);
    animationFrame = window.requestAnimationFrame(render);
  };

  master.addEventListener('seeked', () => syncFollowers(true));
  master.addEventListener('playing', playAll);
  master.addEventListener('timeupdate', () => showLayer(layerAt(master.currentTime || 0)));
  window.addEventListener('pointerdown', playAll, { passive: true });
  window.addEventListener('keydown', (event) => {
    if (event.code !== 'Space') return;
    event.preventDefault();
    if (master.paused) playAll();
    else Object.values(videos).forEach((video) => video.pause());
  });

  showLayer('source', true);
  playAll();
})();
