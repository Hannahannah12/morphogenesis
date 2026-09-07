(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const root = $('current-image');
  const cameraVideo = $('camera-video');
  const cameraEmpty = $('camera-empty');
  const cameraStart = $('camera-start');
  const cameraButton = $('camera-button');
  const cameraSelect = $('camera-select');
  const controlsToggle = $('controls-toggle');
  const controlsBody = $('controls-body');
  const sourceLabel = $('source-label');
  const notice = $('notice');
  const CAMERA_STORAGE_KEY = 'morphogenesis-camera-id';

  let cameraStream = null;
  let cameraLabel = 'USB camera';
  let cameraError = '';

  const isPhysicalCamera = (device) => (
    !/obs|virtual camera|meta quest/i.test(device.label)
  );

  const cameraPreferenceScore = (device) => {
    const label = device.label.toLowerCase();
    if (/integrated|built-in|internal|facetime|front/.test(label)) return -20;
    if (/usb|uvc|external|logitech|brio|elgato|capture|avermedia|webcam/.test(label)) return 20;
    return 0;
  };

  const setConnected = (connected) => {
    root.classList.toggle('camera-connected', connected);
    cameraEmpty.hidden = connected;
    sourceLabel.textContent = connected
      ? `Camera / ${cameraLabel}`
      : cameraError || 'Camera / waiting';
  };

  const listCameras = async (selectedId = '') => {
    const devices = (await navigator.mediaDevices.enumerateDevices())
      .filter((device) => device.kind === 'videoinput')
      .filter(isPhysicalCamera);
    cameraSelect.replaceChildren(new Option(
      devices.length ? 'USB camera (auto)' : 'No physical camera found',
      ''
    ));
    devices.forEach((device, index) => {
      cameraSelect.add(new Option(device.label || `Camera ${index + 1}`, device.deviceId));
    });
    cameraSelect.value = devices.some((device) => device.deviceId === selectedId)
      ? selectedId
      : '';
    return devices;
  };

  const stopCamera = () => {
    cameraStream?.getTracks().forEach((track) => track.stop());
    cameraStream = null;
    cameraVideo.srcObject = null;
    setConnected(false);
  };

  const getCameraStream = async (requestedId = '') => {
    const video = {
      width: { ideal: 1920 },
      height: { ideal: 1080 },
      facingMode: { ideal: 'environment' }
    };
    if (requestedId) video.deviceId = { exact: requestedId };
    return navigator.mediaDevices.getUserMedia({ video, audio: false });
  };

  const startCamera = async (requestedId = cameraSelect.value) => {
    if (!navigator.mediaDevices?.getUserMedia) {
      cameraError = 'Camera unavailable / open through localhost in Chrome or Edge';
      setConnected(false);
      return;
    }
    cameraButton.disabled = true;
    cameraStart.disabled = true;
    notice.textContent = 'Connecting physical camera';
    try {
      let nextStream;
      try {
        nextStream = await getCameraStream(requestedId);
      } catch (error) {
        if (!requestedId || error.name === 'NotAllowedError') throw error;
        nextStream = await getCameraStream();
      }

      const devices = await listCameras(requestedId);
      const activeId = nextStream.getVideoTracks()[0]?.getSettings().deviceId || '';
      const savedId = localStorage.getItem(CAMERA_STORAGE_KEY) || '';
      const preferred = devices
        .filter((device) => device.deviceId !== activeId)
        .sort((a, b) => cameraPreferenceScore(b) - cameraPreferenceScore(a))[0];
      const targetId = requestedId
        || (devices.some((device) => device.deviceId === savedId) ? savedId : '')
        || (preferred && cameraPreferenceScore(preferred) > 0 ? preferred.deviceId : '')
        || devices[0]?.deviceId
        || '';

      if (targetId && activeId !== targetId) {
        nextStream.getTracks().forEach((track) => track.stop());
        nextStream = await getCameraStream(targetId);
      }

      stopCamera();
      cameraStream = nextStream;
      const finalId = cameraStream.getVideoTracks()[0]?.getSettings().deviceId || targetId;
      cameraLabel = devices.find((device) => device.deviceId === finalId)?.label || 'USB camera';
      if (finalId) {
        localStorage.setItem(CAMERA_STORAGE_KEY, finalId);
        cameraSelect.value = finalId;
      }
      cameraVideo.srcObject = cameraStream;
      await cameraVideo.play();
      cameraError = '';
      notice.textContent = '';
      setConnected(true);
    } catch (error) {
      cameraError = error.name === 'NotAllowedError'
        ? 'Camera permission required'
        : `Camera connection failed / ${error.name || 'unknown error'}`;
      stopCamera();
      notice.textContent = cameraError;
    } finally {
      cameraButton.disabled = false;
      cameraStart.disabled = false;
    }
  };

  const autoStart = async () => {
    if (!navigator.mediaDevices?.enumerateDevices) {
      setConnected(false);
      return;
    }
    const savedId = localStorage.getItem(CAMERA_STORAGE_KEY) || '';
    const devices = await listCameras(savedId).catch(() => []);
    const hasNamedDevice = devices.some((device) => device.label);
    if (
      new URLSearchParams(window.location.search).get('startCamera') === '1'
      || savedId
      || hasNamedDevice
    ) {
      await startCamera(savedId);
    }
  };

  cameraStart.addEventListener('click', () => startCamera());
  cameraButton.addEventListener('click', () => startCamera());
  cameraSelect.addEventListener('change', () => startCamera(cameraSelect.value));
  controlsToggle.addEventListener('click', () => {
    const expanded = controlsBody.hidden;
    controlsBody.hidden = !expanded;
    controlsToggle.textContent = expanded ? '−' : '+';
    controlsToggle.setAttribute('aria-expanded', String(expanded));
  });
  $('fullscreen-button').addEventListener('click', () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen();
  });
  navigator.mediaDevices?.addEventListener('devicechange', () => {
    listCameras(cameraSelect.value).catch(() => {});
  });
  window.addEventListener('pagehide', stopCamera);

  window.getMorphogenesisPageDetails = () => ({
    cameraActive: Boolean(cameraStream),
    cameraLabel,
    cameraError,
    source: cameraStream ? 'physical USB camera' : 'camera disconnected',
    rawImage: true
  });

  setConnected(false);
  autoStart().catch(() => {});
})();
