(() => {
  'use strict';

  const exhibitionEmbed = new URLSearchParams(window.location.search).get('exhibitionEmbed') === '1';
  document.body.classList.toggle('exhibition-embed', exhibitionEmbed);

  const $ = (id) => document.getElementById(id);
  const analysisVideo = $('analysis-video');
  const cameraVideo = $('camera-video');
  const cameraSelect = $('camera-select');
  const controlsPanel = $('controls-panel');
  const controlsToggle = $('controls-toggle');
  const resonanceCloud = $('resonance-cloud');
  const selectionCrosshair = $('selection-crosshair');
  const resonanceFocus = $('resonance-focus');
  const focusPatch = $('focus-patch');
  const focusIndex = $('focus-index');
  const searchResults = $('search-results');
  const cameraButton = $('camera-button');
  const sourceWindow = $('source-window');
  const sourcePreview = $('source-preview');
  const sourceLabel = $('source-label');
  const sourceToggle = $('source-toggle');

  const outputRoot = '../../09_experiments/previous_tests/02_structural_resonance/output';
  const archivePatchRoot = '../archive/images/patches';
  const recordedSource = (crystal) => (
    `/05_shared_data/exhibition/${crystal}/source/crystallization.mp4`
  );

  const patchFiles = [
    ...Array.from({ length: 8 }, (_, index) => `patch_328_${index}.jpg`),
    ...Array.from({ length: 5 }, (_, index) => `patch_338_${index + 8}.jpg`),
    ...Array.from({ length: 3 }, (_, index) => `patch_348_${index + 13}.jpg`),
    ...Array.from({ length: 3 }, (_, index) => `patch_358_${index + 16}.jpg`),
    ...Array.from({ length: 4 }, (_, index) => `patch_368_${index + 19}.jpg`),
    ...Array.from({ length: 5 }, (_, index) => `patch_378_${index + 23}.jpg`),
    ...Array.from({ length: 6 }, (_, index) => `patch_388_${index + 28}.jpg`),
    ...Array.from({ length: 7 }, (_, index) => `patch_398_${index + 34}.jpg`),
    ...Array.from({ length: 2 }, (_, index) => `patch_408_${index + 41}.jpg`),
    ...Array.from({ length: 7 }, (_, index) => `patch_418_${index + 43}.jpg`)
  ];

  const foundPhotos = (patchIndex, files) => files.map(
    (file) => `${archivePatchRoot}/patch_${patchIndex}/found_photos/${file}`
  );

  const resonanceSets = [
    {
      patchIndex: 0,
      results: foundPhotos(0, [
        'clip_00_sand dune_0.78.jpg',
        '01_sand dune_0.78.jpg',
        'clip_02_frost_0.76.jpg',
        '03_sand dune_0.76.jpg',
        '04_sand dune_0.75.jpg',
        '05_whirlpool_0.69.jpg',
        '06_foam_0.68.jpg',
        '07_glacier_0.67.jpg',
        '08_frost_0.67.jpg',
        '09_whirlpool_0.67.jpg',
        'hog_00_glacier_0.96.jpg',
        'hog_03_ice_0.96.jpg',
        'canny_03_Frost_0.77.jpg',
        'canny_06_glacier_0.72.jpg'
      ])
    },
    {
      patchIndex: 1,
      results: foundPhotos(1, [
        'clip_00_faulting_0.79.jpg',
        'clip_01_faulting_0.72.jpg',
        'clip_04_bacterium_0.66.jpg',
        'clip_05_nerve cell_0.66.jpg',
        'clip_06_neuron_0.66.jpg',
        'clip_08_convolution_0.61.jpg',
        'hog_00_faulting_0.84.jpg',
        'hog_02_neuron_0.82.jpg',
        'hog_04_bacterium_0.82.jpg',
        'hog_05_crevice_0.82.jpg',
        'canny_04_faulting_0.65.jpg',
        'threshold_05_neuron_0.68.jpg',
        'threshold_06_bacterium_0.67.jpg'
      ])
    },
    {
      patchIndex: 2,
      results: foundPhotos(2, [
        'clip_00_erosion_0.76.jpg',
        'clip_01_lava_0.74.jpg',
        'clip_02_sand dune_0.74.jpg',
        'clip_04_asteroid_0.72.jpg',
        'clip_05_foam_0.71.jpg',
        'clip_08_glacier_0.68.jpg',
        'hog_00_glacier_0.94.jpg',
        'hog_01_eroding_0.94.jpg',
        'hog_03_erosion_0.94.jpg',
        'hog_04_crevice_0.94.jpg',
        'hog_06_ice_0.94.jpg',
        'canny_01_sand dune_0.82.jpg',
        'canny_03_lava_0.79.jpg',
        'canny_05_tornado_0.76.jpg',
        'threshold_09_asteroid_0.65.jpg'
      ])
    },
    {
      patchIndex: 3,
      results: foundPhotos(3, [
        'clip_00_ice_0.91.jpg',
        'clip_01_faulting_0.78.jpg',
        'clip_02_ice_0.77.jpg',
        'clip_03_faulting_0.74.jpg',
        'clip_04_ice_0.71.jpg',
        'clip_05_diatom_0.69.jpg',
        'clip_06_bacterium_0.68.jpg',
        'clip_07_diatom_0.65.jpg',
        'clip_09_ice_0.63.jpg',
        'hog_00_headliner_0.92.jpg',
        'hog_01_diatom_0.92.jpg',
        'hog_04_convolution_0.91.jpg',
        'hog_05_bacterium_0.91.jpg',
        'hog_09_headliner_0.91.jpg',
        'threshold_04_faulting_0.73.jpg',
        'threshold_08_convolution_0.61.jpg'
      ])
    },
    {
      patchIndex: 4,
      results: foundPhotos(4, [
        'clip_00_ice_0.91.jpg',
        'clip_01_ice_0.77.jpg',
        'clip_02_mountain_0.72.jpg',
        'clip_03_ice_0.71.jpg',
        'clip_05_tornado_0.68.jpg',
        'clip_07_glacier_0.63.jpg',
        'hog_00_tornado_0.89.jpg',
        'hog_01_flake_0.88.jpg',
        'hog_02_mountain_0.88.jpg',
        'hog_04_asteroid_0.87.jpg',
        'hog_05_ice_0.87.jpg',
        'hog_09_ice_0.86.jpg',
        'canny_06_glacier_0.62.jpg',
        'threshold_04_mountain_0.70.jpg',
        'threshold_07_tornado_0.64.jpg'
      ])
    },
    {
      patchIndex: 5,
      results: foundPhotos(5, [
        'clip_00_mountain_0.68.jpg',
        'clip_02_diatom_0.66.jpg',
        'clip_03_diatom_0.65.jpg',
        'clip_04_mountain_0.65.jpg',
        'clip_05_snap_0.62.jpg',
        'clip_06_diatom_0.62.jpg',
        'hog_01_diatom_0.85.jpg',
        'hog_02_diatom_0.84.jpg',
        'hog_03_mountain_0.82.jpg',
        'hog_04_diatom_0.79.jpg',
        'hog_06_snap_0.79.jpg',
        'hog_08_headliner_0.77.jpg',
        'canny_05_mountain_0.64.jpg',
        'canny_08_convolution_0.63.jpg',
        'threshold_09_mountain_0.64.jpg'
      ])
    },
    {
      patchIndex: 6,
      results: foundPhotos(6, [
        'clip_00_ice_0.83.jpg',
        'clip_01_faulting_0.78.jpg',
        'clip_02_ice_0.77.jpg',
        'clip_03_faulting_0.73.jpg',
        'clip_04_gap_0.73.jpg',
        'clip_05_neuron_0.70.jpg',
        'clip_07_tornado_0.67.jpg',
        'clip_09_crevice_0.61.jpg',
        'hog_00_faulting_0.89.jpg',
        'hog_01_wad_0.88.jpg',
        'hog_02_ice_0.87.jpg',
        'hog_03_neuron_0.87.jpg',
        'hog_06_gap_0.87.jpg',
        'hog_09_crevice_0.86.jpg',
        'canny_01_gap_0.76.jpg',
        'threshold_04_gap_0.78.jpg'
      ])
    },
    {
      patchIndex: 7,
      results: foundPhotos(7, [
        'clip_00_faulting_0.69.jpg',
        'clip_01_faulting_0.67.jpg',
        'clip_02_hoar_0.61.jpg',
        'hog_00_mistake_0.78.jpg',
        'hog_01_convolution_0.77.jpg',
        'hog_02_hoar_0.77.jpg',
        'hog_03_maven_0.76.jpg',
        'hog_04_headliner_0.75.jpg',
        'hog_06_maven_0.75.jpg',
        'hog_08_first-rate_0.74.jpg',
        'canny_02_first-rate_0.63.jpg',
        'canny_03_hoar_0.61.jpg',
        'threshold_04_maven_0.67.jpg',
        'threshold_06_hoar_0.63.jpg',
        'threshold_08_hoar_0.62.jpg'
      ])
    }
  ];

  const manifests = {
    ice_crystal_01: {
      name: 'ice crystal 01',
      source: recordedSource('ice_crystal_01'),
      video: `${outputRoot}/ice_crystal_01/exhibition/attention_blob.webm?v=overlay-v1`,
      patches: patchFiles.map(
        (file) => `${outputRoot}/ice_crystal_01/attention_maps/patches/${file}`
      ),
      resonanceSets
    },
    ice_crystal_02: {
      name: 'ice crystal 02',
      source: recordedSource('ice_crystal_02'),
      video: `${outputRoot}/ice_crystal_02/exhibition/attention_blob.webm?v=overlay-v1`,
      patches: [
        `${outputRoot}/ice_crystal_02/attention_maps/patches/patch_259_11.jpg`,
        `${outputRoot}/ice_crystal_02/attention_maps/patches/patch_279_20.jpg`,
        `${outputRoot}/ice_crystal_02/attention_maps/patches/patch_299_31.jpg`,
        `${outputRoot}/ice_crystal_02/attention_maps/patches/patch_319_39.jpg`
      ],
      resonanceSets: []
    }
  };
  const recordedManifestUrls = {
    ice_crystal_01: '/05_shared_data/exhibition/ice_crystal_01/02_structural_resonance/manifest.json',
    ice_crystal_02: '/05_shared_data/exhibition/ice_crystal_02/02_structural_resonance/manifest.json',
    ice_crystal_03: '/05_shared_data/exhibition/ice_crystal_03/02_structural_resonance/manifest.json',
    ice_crystal_04: '/05_shared_data/exhibition/ice_crystal_04/02_structural_resonance/manifest.json',
    ice_crystal_05: '/05_shared_data/exhibition/ice_crystal_05/02_structural_resonance/manifest.json',
    ice_crystal_06: '/05_shared_data/exhibition/ice_crystal_06/02_structural_resonance/manifest.json'
  };
  const timings = {
    video: 1800,
    cloud: 2600,
    selected: 480,
    resultItem: 140,
    resultHold: 6800
  };

  let cameraStream = null;
  let mode = 'ice_crystal_01';
  let stage = 'video';
  let loopToken = 0;
  let resonanceCursor = 0;
  let sessionActive = false;
  let sessionRevision = 0;
  let sessionOutputUrl = '';
  let sessionManifestUrl = '';
  let sessionCreatedAt = '';
  let archiveCycleApplied = '';
  let resonanceRehearsalMode = false;
  let resonanceRehearsalKey = '';
  let prewarmedCrystal = '';
  const loadedRecordedManifests = new Set();
  let resonanceRandomState = 1;
  const resetResonanceRandom = (key) => {
    resonanceRandomState = [...String(key || 'morphogenesis')].reduce(
      (hash, character) => Math.imul(hash ^ character.charCodeAt(0), 16777619) >>> 0,
      2166136261
    ) || 1;
  };
  const resonanceRandom = () => {
    resonanceRandomState = (Math.imul(resonanceRandomState, 1664525) + 1013904223) >>> 0;
    return resonanceRandomState / 4294967296;
  };
  const resonanceTerminal = $('resonance-terminal');
  const resonanceTerminalLog = $('resonance-terminal-log');
  const resonanceTerminalSteps = [
    'Extract attention patches · DINO feature map',
    'Filter patches · confidence and spatial overlap',
    'Associate terms · visual vocabulary',
    'Query APIs · NASA and iNaturalist',
    'Store matches · resonance results ready'
  ];

  const renderResonanceTerminal = (session) => {
    const active = session?.kind === 'analysis_rehearsal'
      && session?.phase === 'resonance_terminal';
    resonanceTerminal.classList.toggle('visible', active);
    if (!active) return;
    const presentation = session.presentation || {};
    const currentIndex = Math.max(0, Number(presentation.terminalStepIndex || 0));
    const currentState = String(presentation.terminalStepState || 'processing');
    resonanceTerminalLog.replaceChildren();
    resonanceTerminalSteps.slice(0, currentIndex + 1).forEach((message, index) => {
      const line = document.createElement('span');
      const finished = index < currentIndex || currentState === 'success';
      line.className = finished ? 'success' : 'running';
      line.textContent = `${String(index + 1).padStart(2, '0')}  ${message}  ${finished ? '[success]' : '[running]'}`;
      resonanceTerminalLog.append(line);
    });
  };

  sourceToggle.addEventListener('click', () => {
    const collapsed = sourceWindow.classList.toggle('collapsed');
    sourceToggle.textContent = collapsed ? '+' : '\u2212';
    sourceToggle.setAttribute('aria-expanded', String(!collapsed));
    sourceToggle.setAttribute(
      'aria-label',
      collapsed ? 'Expand original video' : 'Collapse original video'
    );
  });

  const setSourcePreview = async (url, label = 'Original water crystallisation') => {
    sourceLabel.textContent = label;
    if (!url) return;
    const absolute = new URL(url, window.location.origin).href;
    if (sourcePreview.src !== absolute) sourcePreview.src = absolute;
    sourcePreview.loop = true;
    await sourcePreview.play().catch(() => {});
  };

  const delay = (milliseconds, token) => new Promise((resolve) => {
    window.setTimeout(() => resolve(token === loopToken), milliseconds);
  });

  const setStage = (nextStage) => {
    stage = nextStage;
    $('stage-label').textContent = nextStage;
  };

  const fitStageVideo = (video) => {
    if (
      !video
      || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA
      || !video.videoWidth
      || !video.videoHeight
    ) return;
    try {
      const canvas = document.createElement('canvas');
      canvas.width = 180;
      canvas.height = 90;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      const activeRows = [];
      for (let y = 0; y < canvas.height; y += 1) {
        let sum = 0;
        let maximum = 0;
        for (let x = 0; x < canvas.width; x += 1) {
          const offset = (y * canvas.width + x) * 4;
          const luminance = (
            pixels[offset]
            + pixels[offset + 1]
            + pixels[offset + 2]
          ) / 3;
          sum += luminance;
          maximum = Math.max(maximum, luminance);
        }
        const mean = sum / canvas.width;
        if (mean > 8 || maximum > 24) activeRows.push(y);
      }
      if (!activeRows.length) return;
      const top = activeRows[0];
      const bottom = activeRows[activeRows.length - 1];
      const contentRatio = (bottom - top + 1) / canvas.height;
      const contentCenter = (top + bottom + 1) / (2 * canvas.height);
      const scale = contentRatio < 0.86
        ? Math.min(2.4, 1 / contentRatio)
        : 1;
      const shift = contentRatio < 0.86
        ? (0.5 - contentCenter) * 100
        : 0;
      video.style.setProperty('--stage-video-scale', scale.toFixed(3));
      video.style.setProperty('--stage-video-shift', `${shift.toFixed(3)}%`);
      video.dataset.stageContentRatio = contentRatio.toFixed(3);
    } catch {
      video.style.setProperty('--stage-video-scale', '1');
      video.style.setProperty('--stage-video-shift', '0%');
    }
  };

  const parkCrosshair = () => {
    selectionCrosshair.hidden = false;
    selectionCrosshair.style.removeProperty('--cross-x');
    selectionCrosshair.style.removeProperty('--cross-y');
    selectionCrosshair.className = 'selection-crosshair idle';
  };

  analysisVideo.addEventListener('loadeddata', () => {
    window.requestAnimationFrame(() => fitStageVideo(analysisVideo));
  });
  analysisVideo.addEventListener('seeked', () => {
    window.requestAnimationFrame(() => fitStageVideo(analysisVideo));
  });

  const resetResonance = () => {
    parkCrosshair();
    resonanceCloud.hidden = true;
    resonanceCloud.className = 'resonance-cloud';
    resonanceCloud.replaceChildren();
    resonanceFocus.hidden = true;
    resonanceFocus.classList.remove('visible');
    focusPatch.removeAttribute('src');
    searchResults.replaceChildren();
  };

  const renderCloud = (manifest, selectedIndex, token) => {
    resonanceCloud.replaceChildren();
    resonanceCloud.hidden = false;
    resonanceCloud.className = 'resonance-cloud visible';

    const revealOrder = manifest.patches
      .map((_, index) => index)
      .sort(() => resonanceRandom() - 0.5);
    const revealDelay = new Map(
      revealOrder.map((patchIndex, orderIndex) => [patchIndex, orderIndex * 36])
    );

    manifest.patches.forEach((src, index) => {
      const item = document.createElement('figure');
      item.className = 'resonance-patch';
      item.dataset.patchIndex = String(index);
      item.style.left = `${1 + resonanceRandom() * 91}%`;
      item.style.top = `${1 + resonanceRandom() * 82}%`;
      item.style.width = `${40 + Math.round(resonanceRandom() * 44)}px`;

      const image = document.createElement('img');
      image.src = src;
      image.alt = `Crystal patch ${index}`;
      const label = document.createElement('figcaption');
      label.textContent = `[${index + 1}]`;
      item.append(image, label);
      resonanceCloud.append(item);

      window.setTimeout(() => {
        if (token === loopToken) item.classList.add('visible');
      }, revealDelay.get(index));
    });

    resonanceCloud.dataset.selectedIndex = String(selectedIndex);
  };

  const selectCloudPatch = (selectedIndex) => {
    resonanceCloud.classList.add('selecting');
    resonanceCloud
      .querySelector(`[data-patch-index="${selectedIndex}"]`)
      ?.classList.add('selected');
  };

  const animateCrosshair = async (selectedIndex, token) => {
    const stageRect = $('structural-stage').getBoundingClientRect();
    selectionCrosshair.hidden = false;
    selectionCrosshair.className = 'selection-crosshair scanning';

    const hops = 2 + Math.floor(resonanceRandom() * 2);
    for (let index = 0; index < hops; index += 1) {
      selectionCrosshair.style.setProperty(
        '--cross-x',
        `${42 + resonanceRandom() * Math.max(1, stageRect.width - 84)}px`
      );
      selectionCrosshair.style.setProperty(
        '--cross-y',
        `${96 + resonanceRandom() * Math.max(1, stageRect.height - 168)}px`
      );
      if (!await delay(300 + resonanceRandom() * 100, token)) return false;
    }

    const target = resonanceCloud.querySelector(`[data-patch-index="${selectedIndex}"]`);
    if (!target) return false;
    const targetRect = target.getBoundingClientRect();
    selectionCrosshair.style.setProperty(
      '--cross-x',
      `${targetRect.left - stageRect.left + targetRect.width / 2}px`
    );
    selectionCrosshair.style.setProperty(
      '--cross-y',
      `${targetRect.top - stageRect.top + targetRect.height / 2}px`
    );
    selectionCrosshair.className = 'selection-crosshair locked';
    return delay(360, token);
  };

  const beginFocus = (manifest, set) => {
    resonanceCloud.classList.add('receding');
    focusPatch.src = manifest.patches[set.patchIndex];
    focusIndex.textContent = `[${set.patchIndex + 1}]`;
    resonanceFocus.hidden = false;
    window.requestAnimationFrame(() => resonanceFocus.classList.add('visible'));
  };

  const addSearchResult = (src, index) => {
    const resultSlots = [
      [8, 7, 228],
      [49, 4, 252],
      [25, 22, 214],
      [62, 26, 238],
      [5, 43, 260],
      [42, 48, 226],
      [70, 55, 204],
      [20, 66, 242],
      [54, 70, 218],
      [34, 8, 192],
      [2, 65, 210],
      [74, 12, 220]
    ];
    const [left, top, width] = resultSlots[index % resultSlots.length];
    const figure = document.createElement('figure');
    figure.className = 'search-result visible';
    figure.style.left = `${left + (resonanceRandom() * 4 - 2)}%`;
    figure.style.top = `${top + (resonanceRandom() * 4 - 2)}%`;
    figure.style.width = `${width + Math.round(resonanceRandom() * 22)}px`;
    figure.style.zIndex = String(index + 2);
    const image = document.createElement('img');
    image.src = src;
    image.alt = 'Structural resonance search result';
    figure.append(image);
    searchResults.append(figure);
  };

  const clearFocus = () => {
    parkCrosshair();
    resonanceFocus.classList.remove('visible');
    resonanceCloud.classList.remove('selecting', 'receding');
    resonanceCloud.querySelectorAll('.selected').forEach((patch) => {
      patch.classList.remove('selected');
    });
  };

  const disposeFocus = () => {
    resonanceFocus.hidden = true;
    focusPatch.removeAttribute('src');
    focusIndex.textContent = '';
    searchResults.replaceChildren();
  };

  const runRecordedLoop = async (key, token) => {
    const manifest = manifests[key];
    resetResonance();
    setStage('video');
    if (!await delay(timings.video, token)) return;

    const firstSet = manifest.resonanceSets.length
      ? manifest.resonanceSets[0]
      : { patchIndex: 0, results: [] };
    setStage('patch field');
    renderCloud(manifest, firstSet.patchIndex, token);
    if (!await delay(timings.cloud, token)) return;

    while (token === loopToken && mode === key) {
      const set = manifest.resonanceSets.length
        ? manifest.resonanceSets[resonanceCursor % manifest.resonanceSets.length]
        : { patchIndex: resonanceCursor % manifest.patches.length, results: [] };

      setStage('scanning');
      if (!await animateCrosshair(set.patchIndex, token)) break;

      setStage('patch selected');
      selectCloudPatch(set.patchIndex);
      if (!await delay(timings.selected, token)) break;
      parkCrosshair();

      if (!set.results.length) {
        if (!await delay(timings.resultHold, token)) break;
      } else {
        setStage('resonance');
        beginFocus(manifest, set);
        const resultSequence = [...set.results]
          .sort(() => resonanceRandom() - 0.5)
          .slice(0, 12);
        for (let index = 0; index < resultSequence.length; index += 1) {
          if (token !== loopToken) return;
          addSearchResult(resultSequence[index], index);
          if (!await delay(timings.resultItem, token)) return;
        }
        if (!await delay(timings.resultHold, token)) break;
      }

      setStage('switching');
      clearFocus();
      if (!await delay(720, token)) break;
      disposeFocus();
      resonanceCursor += 1;
    }
  };

  const loadSessionManifest = async (url, session) => {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Manifest HTTP ${response.status}`);
    const data = await response.json();
    const base = new URL('.', new URL(url, window.location.origin)).href;
    const manifest = {
      name: session.crystal.replaceAll('_', ' '),
      source: data.source
        ? new URL(data.source, base).href
        : new URL(session.playback?.url || recordedSource(session.crystal), window.location.origin).href,
      video: new URL(data.video, base).href,
      patches: (data.patches || []).map((path) => new URL(path, base).href),
      resonanceSets: (data.resonanceSets || []).map((set) => ({
        patchIndex: Number(set.patchIndex || 0),
        results: (set.results || []).map((result) => (
          typeof result === 'string' ? result : result.url
        )).filter(Boolean)
      }))
    };
    manifests.session = manifest;
    mode = 'session';
    resonanceCursor = 0;
    loopToken += 1;
    const token = loopToken;
    resetResonance();
    analysisVideo.src = manifest.video;
    analysisVideo.hidden = false;
    cameraVideo.hidden = true;
    analysisVideo.loop = true;
    await setSourcePreview(
      manifest.source,
      `Original / ${session.crystal.replaceAll('_', ' ')}`
    );
    await analysisVideo.play().catch(() => {});
    runRecordedLoop('session', token);
  };

  const loadRecordedManifest = async (key) => {
    if (loadedRecordedManifests.has(key)) return;
    const url = recordedManifestUrls[key];
    if (!url) return;
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Manifest HTTP ${response.status}`);
    const data = await response.json();
    const base = new URL('.', new URL(url, window.location.origin)).href;
    manifests[key] = {
      name: key.replaceAll('_', ' '),
      source: data.source
        ? new URL(data.source, base).href
        : new URL(recordedSource(key), window.location.origin).href,
      video: new URL(data.video, base).href,
      patches: (data.patches || []).map((path) => new URL(path, base).href),
      resonanceSets: (data.resonanceSets || []).map((set) => ({
        patchIndex: Number(set.patchIndex || 0),
        results: (set.results || []).map((result) => (
          typeof result === 'string' ? result : result.url
        )).filter(Boolean)
      }))
    };
    loadedRecordedManifests.add(key);
  };

  const prewarmRecorded = async (key) => {
    if (!key || prewarmedCrystal === key) return;
    prewarmedCrystal = key;
    await loadRecordedManifest(key);
    const manifest = manifests[key];
    if (!manifest) return;
    analysisVideo.preload = 'auto';
    const absoluteVideo = new URL(manifest.video, window.location.origin).href;
    if (analysisVideo.src !== absoluteVideo) {
      analysisVideo.src = absoluteVideo;
      analysisVideo.load();
    }
    // Decode/cache the first visible patch field without starting animation.
    manifest.patches.slice(0, 16).forEach((src) => {
      const image = new Image();
      image.decoding = 'async';
      image.src = src;
    });
  };

  const stopCamera = () => {
    cameraStream?.getTracks().forEach((track) => track.stop());
    cameraStream = null;
    cameraVideo.srcObject = null;
    sourcePreview.srcObject = null;
  };

  const showRecorded = async (key) => {
    stopCamera();
    await loadRecordedManifest(key).catch((error) => {
      $('notice').textContent = `Recorded manifest fallback: ${error.message}`;
    });
    loopToken += 1;
    const token = loopToken;
    const manifest = manifests[key];
    mode = key;
    resetResonanceRandom(key);
    resonanceCursor = 0;
    resetResonance();
    setStage('video');
    analysisVideo.src = manifest.video;
    analysisVideo.hidden = false;
    cameraVideo.hidden = true;
    cameraButton.classList.remove('active');
    await setSourcePreview(manifest.source || recordedSource(key), `Original / ${manifest.name}`);
    $('mode-label').textContent = `Recorded process / ${manifest.name}`;
    $('notice').textContent = `Recorded structural process / ${manifest.name}`;
    await analysisVideo.play().catch(() => {});
    runRecordedLoop(key, token);
  };

  const listCameras = async () => {
    const devices = (await navigator.mediaDevices.enumerateDevices())
      .filter((device) => device.kind === 'videoinput');
    cameraSelect.replaceChildren(new Option('Choose USB camera', ''));
    devices.forEach((device, index) => {
      cameraSelect.add(new Option(device.label || `Camera ${index + 1}`, device.deviceId));
    });
    const preferred = devices.find((device) => /uvc|usb|external|capture/i.test(device.label));
    if (preferred) cameraSelect.value = preferred.deviceId;
    return preferred;
  };

  const openCamera = async (deviceId) => {
    if (!deviceId) {
      $('notice').textContent = 'Choose a USB/UVC camera. Live structural processing is not running yet.';
      return;
    }
    stopCamera();
    loopToken += 1;
    resetResonance();
    try {
      cameraStream = await navigator.mediaDevices.getUserMedia({
        video: {
          deviceId: { exact: deviceId },
          width: { ideal: 1280 },
          height: { ideal: 720 }
        },
        audio: false
      });
      cameraVideo.srcObject = cameraStream;
      sourcePreview.removeAttribute('src');
      sourcePreview.srcObject = cameraStream;
      await cameraVideo.play();
      await sourcePreview.play().catch(() => {});
      sourceLabel.textContent = 'Original / live macro camera';
      mode = 'camera';
      setStage('live input');
      analysisVideo.hidden = true;
      cameraVideo.hidden = false;
      cameraButton.classList.add('active');
      const label = cameraSelect.options[cameraSelect.selectedIndex]?.text || 'USB camera';
      $('mode-label').textContent = `Live input / ${label}`;
      $('notice').textContent = 'USB camera connected / Python worker not connected';
    } catch (error) {
      $('notice').textContent = `Camera could not open: ${error.message}`;
      await showRecorded('ice_crystal_01');
    }
  };

  const findUsbCamera = async () => {
    try {
      const permission = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      permission.getTracks().forEach((track) => track.stop());
      const preferred = await listCameras();
      if (preferred) await openCamera(preferred.deviceId);
      else $('notice').textContent = 'No USB/UVC camera was found. Choose a device manually.';
    } catch (error) {
      $('notice').textContent = `Camera permission failed: ${error.message}`;
    }
  };

  controlsToggle.addEventListener('click', () => {
    const collapsed = controlsPanel.classList.toggle('collapsed');
    controlsToggle.setAttribute('aria-expanded', String(!collapsed));
    controlsToggle.setAttribute('aria-label', collapsed ? 'Expand controls' : 'Collapse controls');
    controlsToggle.textContent = collapsed ? '+' : '−';
  });
  cameraButton.addEventListener('click', findUsbCamera);
  cameraSelect.addEventListener('change', () => openCamera(cameraSelect.value));
  $('fullscreen-button').addEventListener('click', () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen();
  });
  navigator.mediaDevices?.addEventListener('devicechange', () => listCameras().catch(() => {}));
  window.addEventListener('pagehide', () => {
    loopToken += 1;
    stopCamera();
  });

  window.getMorphogenesisPageDetails = () => ({
    mode,
    stage,
    cameraActive: Boolean(cameraStream),
    analysis: /^ice_crystal_0[1-6]$/.test(mode)
      ? 'recorded structural resonance'
      : 'not running'
  });

  window.handleMorphogenesisCommand = async (command = {}) => {
    const action = String(command.action || '');
    const value = String(command.value || '');
    if (action === 'setSource' || action === 'setMode') {
      if (/^ice_crystal_0[1-6]$/.test(value)) return showRecorded(value);
      if (value === 'camera') {
        return cameraSelect.value ? openCamera(cameraSelect.value) : findUsbCamera();
      }
    }
    const activeVideo = cameraVideo.hidden ? analysisVideo : cameraVideo;
    if (action === 'play') return activeVideo.play();
    if (action === 'pause') return activeVideo.pause();
  };

  window.addEventListener('morphogenesis-command', (event) => {
    window.handleMorphogenesisCommand(event.detail).catch(() => {});
  });

  const applySession = async (session) => {
    if (session?.kind === 'analysis_rehearsal') {
      const materialComplete = session?.jobs?.material?.state === 'complete';
      if (!materialComplete) {
        prewarmRecorded(session.crystal).catch(() => {});
        resonanceTerminal.classList.remove('visible');
        // Prewarm may set the video source, but playback must remain stopped
        // behind WAITING_ until Material emits its completion signal.
        analysisVideo.pause();
        sourcePreview.pause();
        if (resonanceRehearsalMode) {
          resonanceRehearsalMode = false;
          resonanceRehearsalKey = '';
          loopToken += 1;
          analysisVideo.pause();
          resetResonance();
        }
        return;
      }

      // Material completion is the only start cue. Ignore the later legacy
      // resonance/diffusion phase names and keep this animation running.
      resonanceTerminal.classList.remove('visible');
      resonanceRehearsalMode = true;
      const key = [
        session.crystal,
        session.presentation?.rehearsalCycle || 1
      ].join(':');
      if (resonanceRehearsalKey !== key) {
        resonanceRehearsalKey = key;
        await showRecorded(session.crystal);
        setStage('structure resonance');
      }
      return;
    }
    resonanceTerminal.classList.remove('visible');
    resonanceRehearsalMode = false;
    if (session?.kind === 'archive_cycle') {
      const archiveKey = `${session.crystal}:${session.playback?.revision || 0}`;
      const archiveChanged = archiveCycleApplied !== archiveKey;
      if (archiveChanged) {
        archiveCycleApplied = archiveKey;
        sessionActive = false;
        sessionOutputUrl = '';
        await showRecorded(session.crystal);
      }
      $('mode-label').textContent = 'Archive replay';
      $('notice').textContent = 'Recorded structural process';
      const archiveManifest = manifests[session.crystal];
      if (archiveManifest?.video) {
        await window.syncMorphogenesisVideo?.(
          analysisVideo,
          session,
          archiveManifest.video,
          { timeline: 'normalized' }
        );
        await window.syncMorphogenesisVideo?.(
          sourcePreview,
          session,
          archiveManifest.source || recordedSource(session.crystal),
          { timeline: 'normalized' }
        );
      }
      return;
    }
    archiveCycleApplied = '';
    if (session?.createdAt && sessionCreatedAt !== session.createdAt) {
      sessionCreatedAt = session.createdAt;
      analysisVideo.pause();
      analysisVideo.removeAttribute('src');
      analysisVideo.load();
      sessionOutputUrl = '';
      sessionManifestUrl = '';
      sessionRevision = 0;
      sessionActive = false;
    }
    const playback = session?.playback;
    if (!playback?.url) return;
    await window.syncMorphogenesisVideo?.(
      sourcePreview,
      session,
      playback.url,
      { timeline: 'normalized' }
    );
    sourceLabel.textContent = `Original / ${session.crystal.replaceAll('_', ' ')}`;
    if (!sessionActive) {
      sessionActive = true;
      loopToken += 1;
      stopCamera();
      resetResonance();
      analysisVideo.hidden = false;
      cameraVideo.hidden = true;
      analysisVideo.loop = true;
    }
    const job = session?.jobs?.structural;
    const nextUrl = job?.state === 'complete' && job.outputUrl
      ? job.outputUrl
      : playback.url;
    if (sessionOutputUrl !== nextUrl || sessionRevision !== playback.revision) {
      sessionOutputUrl = nextUrl;
      sessionRevision = playback.revision;
    }
    if (job?.state !== 'complete') setStage('observing input');
    else if (!sessionManifestUrl) setStage('structural result');
    $('mode-label').textContent = job?.state === 'complete'
      ? session.kind === 'archive_cycle'
        ? `Archive replay / ${session.crystal.replaceAll('_', ' ')}`
        : `New live result / ${session.crystal.replaceAll('_', ' ')}`
      : `Current experiment source / ${session.crystal.replaceAll('_', ' ')}`;
    $('notice').textContent = job?.message || 'Following the shared experiment source';
    if (job?.state === 'complete') {
      const absolute = new URL(nextUrl, window.location.origin).href;
      if (analysisVideo.src !== absolute) analysisVideo.src = absolute;
      if (analysisVideo.paused) await analysisVideo.play().catch(() => {});
      if (job.manifestUrl && sessionManifestUrl !== job.manifestUrl) {
        sessionManifestUrl = job.manifestUrl;
        await loadSessionManifest(job.manifestUrl, session).catch((error) => {
          $('notice').textContent = `Structural manifest failed: ${error.message}`;
        });
      }
      return;
    }
    await window.syncMorphogenesisVideo?.(analysisVideo, session, nextUrl);
  };

  const standaloneMode = new URLSearchParams(window.location.search).get('standalone');
  if (/^ice_crystal_0[1-6]$/.test(standaloneMode || '')) {
    showRecorded(standaloneMode);
  } else if (window.morphogenesisSession) {
    window.addEventListener('morphogenesis-session', (event) => applySession(event.detail));
    window.addEventListener('morphogenesis-session-tick', (event) => applySession(event.detail));
    applySession(window.morphogenesisSession);
  } else {
    window.addEventListener('morphogenesis-session', (event) => applySession(event.detail));
    window.addEventListener('morphogenesis-session-tick', (event) => applySession(event.detail));
    mode = 'agent';
    analysisVideo.hidden = true;
    setStage('connecting');
    $('mode-label').textContent = 'Agent session / current crystal';
    $('notice').textContent = 'Waiting for the current Agent structural output';
  }
})();
