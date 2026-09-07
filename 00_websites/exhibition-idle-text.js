(() => {
  'use strict';

  const script = document.currentScript;
  const idleMilliseconds = Math.max(1000, Number(script?.dataset.idleMs) || 4000);
  const preserveSelectors = String(script?.dataset.preserve || '')
    .split(',')
    .map((selector) => selector.trim())
    .filter(Boolean);
  const textSelector = [
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'p', 'span', 'strong',
    'small', 'b', 'em', 'time', 'a', 'button', 'label', 'output', 'li',
    'figcaption', 'legend', 'td', 'th', 'summary', 'input[type="text"]',
    'input[type="search"]', 'textarea', 'select'
  ].join(',');

  const isPreserved = (element) => preserveSelectors.some((selector) => {
    try {
      return Boolean(element.closest(selector));
    } catch (_) {
      return false;
    }
  });

  const containsDirectText = (element) => Array.from(element.childNodes).some(
    (node) => node.nodeType === Node.TEXT_NODE && node.textContent.trim()
  );

  const markElement = (element) => {
    if (!(element instanceof Element)) return;
    if (!element.matches(textSelector)) return;
    if (isPreserved(element)) {
      element.classList.remove('exhibition-idle-copy');
      return;
    }
    const carriesValueText = element.matches(
      'input[type="text"], input[type="search"], textarea, select'
    );
    if (containsDirectText(element) || carriesValueText) {
      element.classList.add('exhibition-idle-copy');
    }
  };

  const scan = (root) => {
    if (root instanceof Element) markElement(root);
    root.querySelectorAll?.(textSelector).forEach(markElement);
  };

  scan(document);
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.type === 'characterData') {
        markElement(mutation.target.parentElement);
        return;
      }
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType === Node.TEXT_NODE) markElement(node.parentElement);
        else if (node instanceof Element) scan(node);
      });
    });
  });
  if (document.body) {
    observer.observe(document.body, { childList: true, characterData: true, subtree: true });
  }

  let idleTimer = 0;
  let activityQueued = false;
  const scheduleIdle = () => {
    window.clearTimeout(idleTimer);
    idleTimer = window.setTimeout(() => {
      document.body.classList.add('exhibition-text-idle');
    }, idleMilliseconds);
  };
  const revealText = () => {
    if (activityQueued) return;
    activityQueued = true;
    window.requestAnimationFrame(() => {
      document.body.classList.remove('exhibition-text-idle');
      scheduleIdle();
      activityQueued = false;
    });
  };

  ['pointermove', 'pointerdown', 'wheel', 'touchstart', 'keydown', 'focusin']
    .forEach((eventName) => window.addEventListener(eventName, revealText, { passive: true }));
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) revealText();
  });
  revealText();
})();
