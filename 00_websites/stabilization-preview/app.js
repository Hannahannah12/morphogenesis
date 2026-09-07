(() => {
  'use strict';

  const root = document.getElementById('comparison');
  const original = document.getElementById('original-video');
  const stabilized = document.getElementById('stabilized-video');
  const divider = document.getElementById('divider');
  const buttons = [...document.querySelectorAll('[data-channel]')];
  const requestedCrystal = new URLSearchParams(window.location.search).get('crystal') || '01';
  const crystalNumber = /^0[1-6]$/.test(requestedCrystal) ? requestedCrystal : '01';
  const stabilizedRoots = {
    '01': '/09_experiments/05_stabilization/ice_crystal_01_fixed_lock',
    '02': '/09_experiments/05_stabilization/ice_crystal_02_plate_lock_v3'
  };
  const originalRoot = `/05_shared_data/exhibition/ice_crystal_${crystalNumber}`;
  const stabilizedRoot = stabilizedRoots[crystalNumber] || stabilizedRoots['01'];
  const crystalLabel = document.getElementById('crystal-label');
  const stabilizationLabel = document.getElementById('stabilization-label');
  crystalLabel.textContent = `Crystal ${crystalNumber}`;
  stabilizationLabel.textContent = crystalNumber === '02'
    ? 'Top screw lock / 6% optical crop'
    : 'Fixed plate lock / 7% optical crop';
  document.title = `Crystal ${crystalNumber} — Stabilization Comparison`;
  const channels = {
    source: {
      original: `${originalRoot}/source/crystallization.mp4`,
      stabilized: `${stabilizedRoot}/source/crystallization_stabilized.mp4`
    },
    edge: {
      original: `${originalRoot}/01_material_analysis/edge.mp4`,
      stabilized: `${stabilizedRoot}/01_material_analysis/edge.mp4`
    },
    threshold: {
      original: `${originalRoot}/01_material_analysis/threshold.mp4`,
      stabilized: `${stabilizedRoot}/01_material_analysis/threshold.mp4`
    },
    spacetime: {
      original: `${originalRoot}/01_material_analysis/spacetime.mp4`,
      stabilized: `${stabilizedRoot}/01_material_analysis/spacetime.mp4`
    },
    motion: {
      original: `${originalRoot}/01_material_analysis/motion.mp4`,
      stabilized: `${stabilizedRoot}/01_material_analysis/motion.mp4`
    }
  };
  let channel = 'source';
  let dragging = false;

  [original, stabilized].forEach((video) => {
    video.defaultMuted = true;
    video.muted = true;
    video.playsInline = true;
    video.loop = true;
  });

  const setSplit = (clientX) => {
    const bounds = root.getBoundingClientRect();
    const percent = Math.max(2, Math.min(98, (clientX - bounds.left) / bounds.width * 100));
    document.documentElement.style.setProperty('--split', `${percent}%`);
    divider.setAttribute('aria-valuenow', String(Math.round(percent)));
  };

  const play = () => Promise.allSettled([original.play(), stabilized.play()]);

  const loadChannel = (next) => {
    if (!channels[next]) return;
    channel = next;
    buttons.forEach((button) => button.classList.toggle('active', button.dataset.channel === channel));
    original.src = channels[channel].original;
    stabilized.src = channels[channel].stabilized;
    original.load();
    stabilized.load();
    play();
  };

  const sync = () => {
    if (original.readyState >= 2 && stabilized.readyState >= 2) {
      const difference = original.currentTime - stabilized.currentTime;
      if (Math.abs(difference) > 0.08) {
        stabilized.currentTime = original.currentTime;
        stabilized.playbackRate = 1;
      } else {
        stabilized.playbackRate = Math.max(0.98, Math.min(1.02, 1 + difference * 0.2));
      }
    }
    window.requestAnimationFrame(sync);
  };

  buttons.forEach((button) => button.addEventListener('click', () => loadChannel(button.dataset.channel)));
  root.addEventListener('pointerdown', (event) => {
    if (event.target.closest('button')) return;
    dragging = true;
    root.setPointerCapture?.(event.pointerId);
    setSplit(event.clientX);
  });
  root.addEventListener('pointermove', (event) => {
    if (dragging) setSplit(event.clientX);
  });
  root.addEventListener('pointerup', () => { dragging = false; });
  root.addEventListener('pointercancel', () => { dragging = false; });
  divider.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const current = Number(divider.getAttribute('aria-valuenow')) || 50;
    setSplit(root.getBoundingClientRect().left + root.clientWidth * (current + (event.key === 'ArrowLeft' ? -2 : 2)) / 100);
  });
  window.addEventListener('pointerdown', play, { passive: true });

  loadChannel('source');
  window.requestAnimationFrame(sync);
})();
