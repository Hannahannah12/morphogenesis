(() => {
  'use strict';

  let lastUpdatedAt = '';
  let currentSession = null;

  const sessionTime = (session) => {
    const playback = session?.playback;
    const duration = Number(playback?.durationSeconds);
    if (!playback?.startedAtEpochMs || !Number.isFinite(duration) || duration <= 0) return 0;
    const elapsed = (Date.now() - Number(playback.startedAtEpochMs)) / 1000;
    return ((elapsed + Number(playback.offsetSeconds || 0)) % duration + duration) % duration;
  };

  const mediaTime = (video, session, timeline) => {
    const duration = Number(video.duration);
    const sharedTime = sessionTime(session);
    if (!Number.isFinite(duration) || duration <= 0) return sharedTime;
    if (timeline === 'normalized') {
      const sourceDuration = Number(session?.playback?.durationSeconds);
      if (Number.isFinite(sourceDuration) && sourceDuration > 0) {
        return (sharedTime / sourceDuration) * duration;
      }
    }
    return ((sharedTime % duration) + duration) % duration;
  };

  const mediaPlaybackRate = (video, session, timeline) => {
    if (timeline !== 'normalized') return 1;
    const mediaDuration = Number(video.duration);
    const sourceDuration = Number(session?.playback?.durationSeconds);
    if (
      !Number.isFinite(mediaDuration)
      || mediaDuration <= 0
      || !Number.isFinite(sourceDuration)
      || sourceDuration <= 0
    ) return 1;
    return Math.min(16, Math.max(0.0625, mediaDuration / sourceDuration));
  };

  window.syncMorphogenesisVideo = async (video, session, url, options = {}) => {
    if (!video || !url) return;
    const absolute = new URL(url, window.location.origin).href;
    const timeline = options.timeline === 'normalized' ? 'normalized' : 'seconds';
    // During the first seconds after a reload, Chromium can expose a transient
    // canonical form of `video.src`. Comparing that property on every 500 ms
    // session tick caused the same URL to be assigned again and again, trapping
    // playback inside the first half-second. Keep an explicit binding instead.
    if (video.dataset.morphogenesisSourceUrl !== absolute) {
      video.pause();
      video.srcObject = null;
      video.src = absolute;
      video.dataset.morphogenesisSourceUrl = absolute;
      video.dataset.morphogenesisSyncInitializing = 'true';
      video.loop = true;
      try {
        if (video.readyState < HTMLMediaElement.HAVE_METADATA) {
          await Promise.race([
            new Promise((resolve) => {
              video.addEventListener('loadedmetadata', resolve, { once: true });
            }),
            new Promise((resolve) => window.setTimeout(resolve, 4000)),
          ]);
        }
        const duration = Number(video.duration);
        if (Number.isFinite(duration) && duration > 0) {
          const localExpected = mediaTime(video, session, timeline);
          video.playbackRate = mediaPlaybackRate(video, session, timeline);
          video.dataset.morphogenesisExpectedTime = String(localExpected);
          // Do not open a page on the final couple of seconds and immediately
          // wrap to frame zero; that looks like a reload glitch.
          const initialTime = timeline === 'seconds' && localExpected > duration - 2.5
            ? 0
            : localExpected;
          video.currentTime = Math.min(initialTime, Math.max(0, duration - 0.05));
        }
        const now = Date.now();
        video.dataset.lastHardSyncAt = String(now);
        video.dataset.morphogenesisSourceBoundAt = String(now);
      } finally {
        video.dataset.morphogenesisSyncInitializing = 'false';
      }
      await video.play().catch(() => {});
      return;
    }
    if (video.dataset.morphogenesisSyncInitializing === 'true') return;
    if (video.readyState >= HTMLMediaElement.HAVE_METADATA) {
      const duration = Number(video.duration);
      const localExpected = mediaTime(video, session, timeline);
      const baseRate = mediaPlaybackRate(video, session, timeline);
      video.dataset.morphogenesisExpectedTime = String(localExpected);
      let drift = localExpected - video.currentTime;
      if (Number.isFinite(duration) && duration > 0 && Math.abs(drift) > duration / 2) {
        drift += drift > 0 ? -duration : duration;
      }
      // Periodic hard seeks are intentionally forbidden. With this H.264 file,
      // Chromium occasionally resolves an otherwise valid seek to the first
      // GOP, producing a 0.x-second loop. Gentle speed correction preserves
      // continuity while keeping exhibition pages near the shared clock.
      if (Math.abs(drift) > 2) {
        video.playbackRate = baseRate * (drift > 0 ? 1.08 : 0.92);
      } else if (Math.abs(drift) > 0.3) {
        video.playbackRate = baseRate * (drift > 0 ? 1.04 : 0.96);
      } else {
        video.playbackRate = baseRate;
      }
    }
    if (video.paused) await video.play().catch(() => {});
  };

  const publish = (session) => {
    currentSession = session;
    window.morphogenesisSession = session;
    window.dispatchEvent(new CustomEvent('morphogenesis-session', { detail: session }));
  };

  const poll = async () => {
    try {
      const response = await fetch('/api/agent/session', { cache: 'no-store' });
      if (!response.ok) return;
      const session = await response.json();
      if (!session?.id) {
        if (currentSession?.id) {
          currentSession = null;
          window.morphogenesisSession = null;
          window.location.reload();
        }
        return;
      }
      if (session.updatedAt !== lastUpdatedAt) {
        lastUpdatedAt = session.updatedAt || '';
        publish(session);
      } else if (currentSession) {
        window.dispatchEvent(new CustomEvent('morphogenesis-session-tick', {
          detail: currentSession,
        }));
      }
    } catch {
      // Pages remain usable as standalone exhibition pages when Agent is absent.
    }
  };

  poll();
  window.setInterval(poll, 500);
  window.addEventListener('pageshow', poll);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') poll();
  });
  window.morphogenesisRefreshSession = poll;
})();
