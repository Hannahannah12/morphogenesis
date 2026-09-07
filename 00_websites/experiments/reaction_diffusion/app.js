(() => {
  'use strict';

  const canvas = document.getElementById('diffusion-canvas');
  const video = document.getElementById('crystal-video');
  const sourceMonitor = document.getElementById('source-monitor');
  const sourcePreviewImage = document.getElementById('source-preview-image');
  const sourcePreviewPlaceholder = document.getElementById('source-preview-placeholder');
  const previewLabel = document.getElementById('preview-label');
  const sourceSelect = document.getElementById('seed-source');
  const feedInput = document.getElementById('feed');
  const killInput = document.getElementById('kill');
  const speedInput = document.getElementById('speed');
  const feedValue = document.getElementById('feed-value');
  const killValue = document.getElementById('kill-value');
  const speedValue = document.getElementById('speed-value');
  const pauseButton = document.getElementById('pause-button');
  const sourceReadout = document.getElementById('source-readout');
  const iterationReadout = document.getElementById('iteration-readout');
  const fpsReadout = document.getElementById('fps-readout');
  const runtimeLabel = document.getElementById('runtime-label');
  const runtimeDetail = document.getElementById('runtime-detail');
  const runtimeDot = document.getElementById('runtime-dot');
  const sensorDot = document.getElementById('sensor-dot');
  const sensorLabel = document.getElementById('sensor-label');
  const objectTemperature = document.getElementById('object-temperature');
  const ambientTemperature = document.getElementById('ambient-temperature');
  const notice = document.getElementById('notice');

  const gl = canvas.getContext('webgl2', {
    alpha: false,
    antialias: false,
    depth: false,
    preserveDrawingBuffer: false
  });

  let noticeTimer = null;
  const showNotice = (message, duration = 2200) => {
    notice.textContent = message;
    notice.classList.add('visible');
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => notice.classList.remove('visible'), duration);
  };

  if (!gl) {
    runtimeLabel.textContent = 'WebGL2 unavailable';
    runtimeDetail.textContent = 'Open in a current Chrome or Edge browser';
    runtimeDot.style.background = '#d28f87';
    showNotice('This browser cannot run the reaction–diffusion field.', 10000);
    return;
  }

  const vertexShaderSource = `#version 300 es
    precision highp float;
    out vec2 vUv;
    void main() {
      vec2 position = vec2(
        (gl_VertexID == 1) ? 3.0 : -1.0,
        (gl_VertexID == 2) ? 3.0 : -1.0
      );
      vUv = position * 0.5 + 0.5;
      gl_Position = vec4(position, 0.0, 1.0);
    }
  `;

  const simulationShaderSource = `#version 300 es
    precision highp float;
    uniform sampler2D uState;
    uniform vec2 uTexel;
    uniform float uFeed;
    uniform float uKill;
    in vec2 vUv;
    out vec4 outState;

    vec2 sampleState(vec2 offset) {
      return texture(uState, vUv + offset * uTexel).rg;
    }

    void main() {
      vec2 state = sampleState(vec2(0.0));
      vec2 laplacian = -state;
      laplacian += sampleState(vec2(-1.0, 0.0)) * 0.20;
      laplacian += sampleState(vec2( 1.0, 0.0)) * 0.20;
      laplacian += sampleState(vec2( 0.0,-1.0)) * 0.20;
      laplacian += sampleState(vec2( 0.0, 1.0)) * 0.20;
      laplacian += sampleState(vec2(-1.0,-1.0)) * 0.05;
      laplacian += sampleState(vec2( 1.0,-1.0)) * 0.05;
      laplacian += sampleState(vec2(-1.0, 1.0)) * 0.05;
      laplacian += sampleState(vec2( 1.0, 1.0)) * 0.05;

      float a = state.r;
      float b = state.g;
      float reaction = a * b * b;
      a += 1.0 * laplacian.r - reaction + uFeed * (1.0 - a);
      b += 0.5 * laplacian.g + reaction - (uKill + uFeed) * b;
      outState = vec4(clamp(a, 0.0, 1.0), clamp(b, 0.0, 1.0), 0.0, 1.0);
    }
  `;

  const renderShaderSource = `#version 300 es
    precision highp float;
    uniform sampler2D uState;
    uniform vec2 uTexel;
    in vec2 vUv;
    out vec4 outColor;

    void main() {
      vec2 state = texture(uState, vUv).rg;
      float field = clamp((state.g - state.r * 0.18) * 1.45, 0.0, 1.0);
      float dx = texture(uState, vUv + vec2(uTexel.x, 0.0)).g
               - texture(uState, vUv - vec2(uTexel.x, 0.0)).g;
      float dy = texture(uState, vUv + vec2(0.0, uTexel.y)).g
               - texture(uState, vUv - vec2(0.0, uTexel.y)).g;
      float edge = smoothstep(0.015, 0.15, length(vec2(dx, dy)));
      float body = smoothstep(0.06, 0.72, field);
      vec3 dark = vec3(0.012, 0.018, 0.015);
      vec3 mineral = vec3(0.70, 0.77, 0.72);
      vec3 highlight = vec3(0.94, 0.97, 0.93);
      vec3 color = mix(dark, mineral, body * 0.74);
      color = mix(color, highlight, edge * 0.78);
      float vignette = smoothstep(0.78, 0.18, distance(vUv, vec2(0.5)));
      color *= mix(0.58, 1.0, vignette);
      outColor = vec4(color, 1.0);
    }
  `;

  const compileShader = (type, source) => {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const message = gl.getShaderInfoLog(shader) || 'Shader compilation failed';
      gl.deleteShader(shader);
      throw new Error(message);
    }
    return shader;
  };

  const createProgram = (fragmentSource) => {
    const program = gl.createProgram();
    const vertex = compileShader(gl.VERTEX_SHADER, vertexShaderSource);
    const fragment = compileShader(gl.FRAGMENT_SHADER, fragmentSource);
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    gl.deleteShader(vertex);
    gl.deleteShader(fragment);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program) || 'Shader link failed');
    }
    return program;
  };

  let simulationProgram;
  let renderProgram;
  try {
    simulationProgram = createProgram(simulationShaderSource);
    renderProgram = createProgram(renderShaderSource);
  } catch (error) {
    runtimeLabel.textContent = 'Shader error';
    runtimeDetail.textContent = error.message;
    showNotice('The diffusion shaders could not start.', 10000);
    return;
  }

  const vao = gl.createVertexArray();
  gl.bindVertexArray(vao);
  const framebuffer = gl.createFramebuffer();
  const supportsFloat = Boolean(gl.getExtension('EXT_color_buffer_float'));
  const textureFormat = supportsFloat ? gl.RGBA16F : gl.RGBA8;
  const textureType = supportsFloat ? gl.FLOAT : gl.UNSIGNED_BYTE;
  let readTexture = null;
  let writeTexture = null;
  let simulationWidth = 0;
  let simulationHeight = 0;
  let iteration = 0;
  let paused = false;
  let dragging = false;
  let frameSamples = [];
  let previousFrameTime = performance.now();
  let resizeTimer = null;

  const createTexture = () => {
    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.REPEAT);
    gl.texImage2D(
      gl.TEXTURE_2D,
      0,
      textureFormat,
      simulationWidth,
      simulationHeight,
      0,
      gl.RGBA,
      textureType,
      null
    );
    return texture;
  };

  const stateArray = () => supportsFloat
    ? new Float32Array(simulationWidth * simulationHeight * 4)
    : new Uint8Array(simulationWidth * simulationHeight * 4);

  const writePixel = (data, index, a, b) => {
    const scale = supportsFloat ? 1 : 255;
    data[index] = a * scale;
    data[index + 1] = b * scale;
    data[index + 2] = 0;
    data[index + 3] = scale;
  };

  const uploadState = (data) => {
    [readTexture, writeTexture].forEach((texture) => {
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.texSubImage2D(
        gl.TEXTURE_2D,
        0,
        0,
        0,
        simulationWidth,
        simulationHeight,
        gl.RGBA,
        textureType,
        data
      );
    });
    iteration = 0;
  };

  const proceduralData = () => {
    const data = stateArray();
    for (let y = 0; y < simulationHeight; y += 1) {
      for (let x = 0; x < simulationWidth; x += 1) {
        const index = (y * simulationWidth + x) * 4;
        const nx = x / simulationWidth;
        const ny = y / simulationHeight;
        const branch = Math.abs(Math.sin(nx * 31 + Math.sin(ny * 13) * 2.8));
        const radial = Math.abs(Math.sin(Math.hypot(nx - .5, ny - .5) * 95));
        const noise = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453;
        const hashed = noise - Math.floor(noise);
        const seeded = (branch > .965 && radial > .62 && hashed > .46)
          || Math.hypot(nx - .5, ny - .5) < .026;
        writePixel(data, index, seeded ? .42 : 1, seeded ? 1 : 0);
      }
    }
    return data;
  };

  const initialiseTextures = () => {
    if (readTexture) gl.deleteTexture(readTexture);
    if (writeTexture) gl.deleteTexture(writeTexture);
    readTexture = createTexture();
    writeTexture = createTexture();
    uploadState(proceduralData());
    sourceReadout.textContent = 'Procedural seed';
  };

  const resize = () => {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.max(1, Math.floor(canvas.clientWidth * ratio));
    canvas.height = Math.max(1, Math.floor(canvas.clientHeight * ratio));
    const targetWidth = Math.min(720, Math.max(360, Math.floor(canvas.clientWidth * .62)));
    const targetHeight = Math.max(220, Math.floor(targetWidth * canvas.clientHeight / canvas.clientWidth));
    if (targetWidth !== simulationWidth || targetHeight !== simulationHeight) {
      simulationWidth = targetWidth;
      simulationHeight = targetHeight;
      initialiseTextures();
    }
  };

  const mediaCanvas = document.createElement('canvas');
  const mediaContext = mediaCanvas.getContext('2d', { willReadFrequently: true });

  const dataFromMedia = (element) => {
    mediaCanvas.width = simulationWidth;
    mediaCanvas.height = simulationHeight;
    mediaContext.fillStyle = '#000';
    mediaContext.fillRect(0, 0, simulationWidth, simulationHeight);
    const sourceWidth = element.videoWidth || element.naturalWidth;
    const sourceHeight = element.videoHeight || element.naturalHeight;
    const sourceAspect = sourceWidth / sourceHeight;
    const targetAspect = simulationWidth / simulationHeight;
    let sx = 0;
    let sy = 0;
    let sw = sourceWidth;
    let sh = sourceHeight;
    if (sourceAspect > targetAspect) {
      sw = sourceHeight * targetAspect;
      sx = (sourceWidth - sw) * .5;
    } else {
      sh = sourceWidth / targetAspect;
      sy = (sourceHeight - sh) * .5;
    }
    mediaContext.drawImage(element, sx, sy, sw, sh, 0, 0, simulationWidth, simulationHeight);
    const pixels = mediaContext.getImageData(0, 0, simulationWidth, simulationHeight).data;
    const luminance = new Float32Array(simulationWidth * simulationHeight);
    for (let i = 0; i < luminance.length; i += 1) {
      const offset = i * 4;
      luminance[i] = pixels[offset] * .2126 + pixels[offset + 1] * .7152 + pixels[offset + 2] * .0722;
    }

    const data = stateArray();
    let seedCount = 0;
    for (let y = 0; y < simulationHeight; y += 1) {
      for (let x = 0; x < simulationWidth; x += 1) {
        const pixelIndex = y * simulationWidth + x;
        const left = luminance[y * simulationWidth + Math.max(0, x - 2)];
        const right = luminance[y * simulationWidth + Math.min(simulationWidth - 1, x + 2)];
        const up = luminance[Math.max(0, y - 2) * simulationWidth + x];
        const down = luminance[Math.min(simulationHeight - 1, y + 2) * simulationWidth + x];
        const gradient = Math.abs(right - left) + Math.abs(down - up);
        const bright = luminance[pixelIndex];
        const sparse = ((x * 17 + y * 31) % 7) < 3;
        const seeded = sparse && (gradient > 28 || bright > 185);
        if (seeded) seedCount += 1;
        writePixel(data, pixelIndex * 4, seeded ? .38 : 1, seeded ? 1 : 0);
      }
    }
    return seedCount > 160 ? data : proceduralData();
  };

  const videoSources = {
    ice_crystal_01: '../../../05_shared_data/input/ice_crystal_01_resized.mp4',
    ice_crystal_02: '../../../05_shared_data/input/ice_crystal_02_resized.mp4'
  };

  const loadVideo = (source) => new Promise((resolve, reject) => {
    if (video.dataset.source === source && video.readyState >= 2) {
      resolve(video);
      return;
    }
    const cleanUp = () => {
      video.removeEventListener('loadeddata', onReady);
      video.removeEventListener('error', onError);
    };
    const onReady = () => {
      cleanUp();
      video.dataset.source = source;
      video.play().catch(() => {});
      resolve(video);
    };
    const onError = () => {
      cleanUp();
      reject(new Error('Crystal video could not be loaded'));
    };
    video.addEventListener('loadeddata', onReady);
    video.addEventListener('error', onError);
    video.src = source;
    video.load();
  });

  const loadImage = (source) => new Promise((resolve, reject) => {
    const image = new Image();
    image.addEventListener('load', () => resolve(image), { once: true });
    image.addEventListener('error', () => reject(new Error('Structural map could not be loaded')), { once: true });
    image.src = source;
  });

  const setPreviewElement = (activeElement) => {
    [video, sourcePreviewImage, sourcePreviewPlaceholder].forEach((element) => {
      element.classList.toggle('active', element === activeElement);
    });
  };

  const updateSourcePreview = async () => {
    const source = sourceSelect.value;
    if (source === 'procedural') {
      setPreviewElement(sourcePreviewPlaceholder);
      previewLabel.textContent = 'Procedural / no source media';
      return;
    }
    if (source === 'structural') {
      sourcePreviewImage.src = '../../archive/images/ice_crystal_01/structure.png';
      setPreviewElement(sourcePreviewImage);
      previewLabel.textContent = 'Structural map / Ice Crystal 01';
      return;
    }
    setPreviewElement(video);
    previewLabel.textContent = source === 'ice_crystal_01'
      ? 'Ice Crystal 01 / source video'
      : 'Ice Crystal 02 / source video';
    try {
      await loadVideo(videoSources[source]);
    } catch (_) {
      previewLabel.textContent = 'Source video unavailable';
    }
  };

  const seedFromSelectedSource = async (announce = true) => {
    const source = sourceSelect.value;
    try {
      runtimeLabel.textContent = 'Preparing seed';
      if (source === 'procedural') {
        uploadState(proceduralData());
        sourceReadout.textContent = 'Procedural field';
      } else if (source === 'structural') {
        const image = await loadImage('../../archive/images/ice_crystal_01/structure.png');
        uploadState(dataFromMedia(image));
        sourceReadout.textContent = 'Structural map / Ice Crystal 01';
      } else {
        const sourceVideo = await loadVideo(videoSources[source]);
        uploadState(dataFromMedia(sourceVideo));
        sourceReadout.textContent = source === 'ice_crystal_01' ? 'Ice Crystal 01 / video' : 'Ice Crystal 02 / video';
      }
      runtimeLabel.textContent = paused ? 'Paused' : 'Evolving';
      sourceMonitor.classList.remove('captured');
      requestAnimationFrame(() => sourceMonitor.classList.add('captured'));
      window.setTimeout(() => sourceMonitor.classList.remove('captured'), 420);
      if (announce) showNotice('Crystal structure applied as the diffusion seed.');
    } catch (error) {
      uploadState(proceduralData());
      sourceReadout.textContent = 'Procedural fallback';
      runtimeLabel.textContent = paused ? 'Paused' : 'Evolving';
      showNotice(`${error.message}. Procedural seed applied.`, 4000);
    }
  };

  const addMaterial = (event) => {
    if (!dragging && event.type !== 'pointerdown') return;
    const rect = canvas.getBoundingClientRect();
    const x = Math.floor((event.clientX - rect.left) / rect.width * simulationWidth);
    const y = Math.floor((rect.bottom - event.clientY) / rect.height * simulationHeight);
    const size = 18;
    const startX = Math.max(0, Math.min(simulationWidth - size, x - size / 2));
    const startY = Math.max(0, Math.min(simulationHeight - size, y - size / 2));
    const patch = supportsFloat ? new Float32Array(size * size * 4) : new Uint8Array(size * size * 4);
    for (let py = 0; py < size; py += 1) {
      for (let px = 0; px < size; px += 1) {
        const distance = Math.hypot(px - size / 2, py - size / 2);
        const seeded = distance < size * .43;
        writePixel(patch, (py * size + px) * 4, seeded ? .35 : 1, seeded ? 1 : 0);
      }
    }
    [readTexture, writeTexture].forEach((texture) => {
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.texSubImage2D(gl.TEXTURE_2D, 0, startX, startY, size, size, gl.RGBA, textureType, patch);
    });
  };

  const runSimulationStep = () => {
    gl.useProgram(simulationProgram);
    gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, writeTexture, 0);
    gl.viewport(0, 0, simulationWidth, simulationHeight);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, readTexture);
    gl.uniform1i(gl.getUniformLocation(simulationProgram, 'uState'), 0);
    gl.uniform2f(gl.getUniformLocation(simulationProgram, 'uTexel'), 1 / simulationWidth, 1 / simulationHeight);
    gl.uniform1f(gl.getUniformLocation(simulationProgram, 'uFeed'), Number(feedInput.value));
    gl.uniform1f(gl.getUniformLocation(simulationProgram, 'uKill'), Number(killInput.value));
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    [readTexture, writeTexture] = [writeTexture, readTexture];
    iteration += 1;
  };

  const render = (time) => {
    if (!paused) {
      const steps = Number(speedInput.value);
      for (let step = 0; step < steps; step += 1) runSimulationStep();
    }
    gl.useProgram(renderProgram);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, readTexture);
    gl.uniform1i(gl.getUniformLocation(renderProgram, 'uState'), 0);
    gl.uniform2f(gl.getUniformLocation(renderProgram, 'uTexel'), 1 / simulationWidth, 1 / simulationHeight);
    gl.drawArrays(gl.TRIANGLES, 0, 3);

    iterationReadout.textContent = iteration.toLocaleString('en-GB');
    const elapsed = Math.max(1, time - previousFrameTime);
    previousFrameTime = time;
    frameSamples.push(1000 / elapsed);
    if (frameSamples.length > 24) frameSamples.shift();
    if (iteration % 32 < Number(speedInput.value)) {
      fpsReadout.textContent = Math.round(frameSamples.reduce((sum, value) => sum + value, 0) / frameSamples.length);
    }
    requestAnimationFrame(render);
  };

  const pollAgent = async () => {
    try {
      const response = await fetch('/api/agent/health', { cache: 'no-store' });
      if (!response.ok) throw new Error('Agent unavailable');
      const health = await response.json();
      runtimeDetail.textContent = `Agent ${health.agent.state.toLowerCase()} / WebGL ${supportsFloat ? 'float' : 'standard'}`;
      const sensing = health.sensing;
      sensorDot.classList.toggle('connected', sensing.connected);
      sensorLabel.textContent = sensing.connected ? 'Arduino connected / live' : 'Arduino disconnected';
      objectTemperature.textContent = sensing.objectTemperature === null ? '--.-' : Number(sensing.objectTemperature).toFixed(1);
      ambientTemperature.textContent = sensing.ambientTemperature === null ? '--.-' : Number(sensing.ambientTemperature).toFixed(1);
    } catch (_) {
      runtimeDetail.textContent = 'Agent offline / local field continues';
      sensorDot.classList.remove('connected');
      sensorLabel.textContent = 'Arduino unavailable';
      objectTemperature.textContent = '--.-';
      ambientTemperature.textContent = '--.-';
    }
  };

  feedInput.addEventListener('input', () => { feedValue.textContent = Number(feedInput.value).toFixed(4); });
  killInput.addEventListener('input', () => { killValue.textContent = Number(killInput.value).toFixed(4); });
  speedInput.addEventListener('input', () => { speedValue.textContent = speedInput.value; });
  sourceSelect.addEventListener('change', updateSourcePreview);
  document.getElementById('seed-button').addEventListener('click', () => seedFromSelectedSource());
  document.getElementById('reset-button').addEventListener('click', () => {
    uploadState(proceduralData());
    sourceReadout.textContent = 'Procedural reset';
    showNotice('Diffusion field reset.');
  });
  pauseButton.addEventListener('click', () => {
    paused = !paused;
    pauseButton.textContent = paused ? 'Resume' : 'Pause';
    runtimeLabel.textContent = paused ? 'Paused' : 'Evolving';
  });
  document.getElementById('fullscreen-button').addEventListener('click', async () => {
    try {
      if (!document.fullscreenElement) await document.getElementById('diffusion').requestFullscreen();
      else await document.exitFullscreen();
    } catch (_) {
      showNotice('Fullscreen is unavailable in this browser.');
    }
  });
  canvas.addEventListener('pointerdown', (event) => {
    dragging = true;
    canvas.setPointerCapture(event.pointerId);
    addMaterial(event);
  });
  canvas.addEventListener('pointermove', addMaterial);
  canvas.addEventListener('pointerup', (event) => {
    dragging = false;
    canvas.releasePointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointercancel', () => { dragging = false; });
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(resize, 180);
  });

  resize();
  runtimeLabel.textContent = 'Evolving';
  runtimeDetail.textContent = `WebGL ${supportsFloat ? 'float' : 'standard'} reaction–diffusion`;
  requestAnimationFrame(render);
  pollAgent();
  window.setInterval(pollAgent, 2000);
  updateSourcePreview();
  window.setTimeout(() => seedFromSelectedSource(false), 500);
})();
