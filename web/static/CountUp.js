// ============================================================================
// Component from React Bits - reactbits.dev
// CountUp - Smooth Counting Animation with Easing, View Trigger & Replay on Hover
// ============================================================================

// ============================================================================
//  COUNT UP SPEED CONFIGURATION:
// EDIT THIS NUMBER BELOW to change how fast or slow the numbers count up:
//   1.0 = Fast (1 second)
//   2.0 = Smooth (2 seconds)
//   2.5 = Smooth count (2.5 seconds) [CURRENT SETTING]
//   3.5 = Very slow / Dramatic (3.5 seconds)
// ============================================================================
const COUNT_UP_DURATION = 2.5; // <--  CHANGE THIS VALUE TO ADJUST COUNT SPEED

const DEFAULT_COUNT_UP_CONFIG = {
  from: 0,
  to: null,
  mode: 'count',
  easing: 'easeOut',
  format: 'standard',
  separator: ',',
  prefix: '',
  suffix: '',
  direction: 'up',
  duration: COUNT_UP_DURATION, // in seconds (configured above: 2.5s)
  delay: 0, // in seconds
  trigger: 'view',
  replayOnHover: false, // Disabled: count once and never restart when cursor hovers
  className: 'count-up-text'
};

class CountUp {
  constructor(element, options = {}) {
    this.element = typeof element === 'string' ? document.querySelector(element) : element;
    if (!this.element) return;

    this.config = Object.assign({}, DEFAULT_COUNT_UP_CONFIG, options);
    this.rafId = null;
    this.isAnimating = false;
    this.hasTriggered = false;
    this.observer = null;
    this.parsedData = null;

    this.init();
  }

  init() {
    if (this.config.className) {
      this.element.classList.add(this.config.className);
    }

    // Save initial target data attribute if not set
    if (!this.element.getAttribute('data-count-target') && this.element.textContent.trim()) {
      this.element.setAttribute('data-count-target', this.element.textContent.trim());
    }

    this.parsedData = this.parseElementData();
    if (!this.parsedData) return;

    this.setupReplayOnHover();
    this.setupObserver();
  }

  parseElementData(overrideTo = null) {
    let rawText = (overrideTo !== null && overrideTo !== undefined)
      ? String(overrideTo)
      : (this.element.getAttribute('data-count-target') || this.element.textContent || '');

    rawText = rawText.trim();
    if (!rawText || rawText === '—' || rawText === '-') {
      return null;
    }

    // Regex to extract prefix, number, suffix
    const match = rawText.match(/^([^\d\.\-]*)([\-]?\d+(?:\.\d+)?)(.*)$/);
    if (!match) return null;

    const detectedPrefix = match[1] || '';
    const numStr = match[2];
    const detectedSuffix = match[3] || '';

    const numVal = parseFloat(numStr);
    if (isNaN(numVal)) return null;

    // Detect decimal places from the formatted string
    const decMatch = numStr.match(/\.(\d+)/);
    const decimals = decMatch ? decMatch[1].length : 0;

    const prefix = this.config.prefix !== '' ? this.config.prefix : detectedPrefix;
    const suffix = this.config.suffix !== '' ? this.config.suffix : detectedSuffix;
    const fromVal = (typeof this.config.from === 'number') ? this.config.from : 0;
    const toVal = (typeof this.config.to === 'number') ? this.config.to : numVal;

    return {
      from: fromVal,
      to: toVal,
      decimals: decimals,
      prefix: prefix,
      suffix: suffix
    };
  }

  getEasing(type) {
    if (typeof type === 'function') return type;
    switch (type) {
      case 'linear':
        return t => t;
      case 'expo':
        return t => (t === 1 ? 1 : 1 - Math.pow(2, -10 * t));
      case 'spring':
        return t => 1 + Math.sin(t * Math.PI * 2) * Math.pow(1 - t, 2);
      case 'easeOut':
      default:
        // High-precision cubic easeOut
        return t => 1 - Math.pow(1 - t, 3);
    }
  }

  formatValue(value, decimals, separator) {
    const fixed = value.toFixed(decimals);
    if (!separator) return fixed;

    const parts = fixed.split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, separator);
    return parts.join('.');
  }

  start(fromOverride = null, toOverride = null) {
    if (this.isAnimating) {
      cancelAnimationFrame(this.rafId);
      this.isAnimating = false;
    }

    const data = this.parseElementData(toOverride);
    if (!data) return;

    this.parsedData = data;
    const startVal = fromOverride !== null ? fromOverride : data.from;
    const endVal = toOverride !== null ? toOverride : data.to;
    const durationMs = (this.config.duration || 1) * 1000;
    const delayMs = (this.config.delay || 0) * 1000;
    const easeFn = this.getEasing(this.config.easing);

    this.isAnimating = true;

    const run = () => {
      const startTime = performance.now();

      const step = (currentTime) => {
        const elapsed = currentTime - startTime;
        const progress = Math.min(1, Math.max(0, elapsed / durationMs));
        const easedProgress = easeFn(progress);

        const currentVal = startVal + (endVal - startVal) * easedProgress;
        const formatted = this.formatValue(currentVal, data.decimals, this.config.separator);

        this.element.textContent = `${data.prefix}${formatted}${data.suffix}`;

        if (progress < 1) {
          this.rafId = requestAnimationFrame(step);
        } else {
          // Set exact final value
          const finalFormatted = this.formatValue(endVal, data.decimals, this.config.separator);
          this.element.textContent = `${data.prefix}${finalFormatted}${data.suffix}`;
          this.isAnimating = false;
        }
      };

      this.rafId = requestAnimationFrame(step);
    };

    if (delayMs > 0) {
      setTimeout(run, delayMs);
    } else {
      run();
    }
  }

  update(newTo) {
    if (newTo !== undefined && newTo !== null) {
      this.element.setAttribute('data-count-target', String(newTo));
    }
    this.start(0, newTo);
  }

  setupObserver() {
    if (this.config.trigger !== 'view' || typeof IntersectionObserver === 'undefined') {
      this.start();
      return;
    }

    this.observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          if (!this.hasTriggered) {
            this.hasTriggered = true;
            this.start();
          }
        }
      });
    }, {
      threshold: 0.1
    });

    const triggerTarget = this.getCardContainer() || this.element;
    this.observer.observe(triggerTarget);
  }

  setupReplayOnHover() {
    if (!this.config.replayOnHover) return;

    const hoverTarget = this.getCardContainer() || this.element;

    hoverTarget.addEventListener('mouseenter', () => {
      if (!this.isAnimating) {
        this.start(0, this.parsedData ? this.parsedData.to : null);
      }
    });
  }

  getCardContainer() {
    return this.element.closest(
      '.overview-kpi-card, .quick-stat-box, .tele-box, .kpi-card, .pace-metric-tile, .release-metric-tile'
    );
  }

  destroy() {
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
    }
    if (this.observer) {
      this.observer.disconnect();
    }
  }
}

// Global Registry of CountUp instances
const countUpInstances = new Map();

// Helper to attach or update CountUp on an element
function applyCountUp(selectorOrElement, options = {}) {
  const el = typeof selectorOrElement === 'string' ? document.querySelector(selectorOrElement) : selectorOrElement;
  if (!el) return null;

  if (countUpInstances.has(el)) {
    const existing = countUpInstances.get(el);
    existing.update(options.to);
    return existing;
  }

  const instance = new CountUp(el, options);
  countUpInstances.set(el, instance);
  return instance;
}

// Initialize CountUp specifically on the user's requested number elements
function initWebsiteCountUps() {
  const targetElements = [
    // Image 1: Overview 6 KPI Cards
    { selector: '#okpi-avg-speed', options: {} },
    { selector: '#okpi-length-pct', options: { suffix: '%' } },
    { selector: '#okpi-swing-val', options: {} },
    { selector: '#okpi-release-val', options: {} },
    { selector: '#okpi-stumps-val', options: { suffix: '%' } },

    // Image 2: Overview Banner Quick Stats
    { selector: '#qs-peak-speed', options: { suffix: ' km/h' } },

    // Image 3: Delivery Studio Live Telemetry HUD Tiles
    { selector: '#stat-speed-mph', options: {} },
    { selector: '#stat-speed-kph', options: { suffix: ' km/h' } },
    { selector: '#stat-swing-val', options: {} },

    // Image 4: Spell Analytics 4 Top KPI Cards
    { selector: '#insights-avg-speed', options: {} },
    { selector: '#insights-avg-release', options: {} },
    { selector: '#insights-avg-swing', options: {} },
    { selector: '#insights-avg-spin', options: {} },
    { selector: '#insights-consistency', options: { suffix: '%' } },

    // Image 5: Spell Analytics Pace Metrics Grid
    { selector: '#pace-max-speed', options: { suffix: ' mph' } },
    { selector: '#pace-max-speed-kph', options: { suffix: ' km/h' } },
    { selector: '#pace-min-speed', options: { suffix: ' mph' } },
    { selector: '#pace-min-speed-kph', options: { suffix: ' km/h' } },
    { selector: '#pace-spread', options: { suffix: ' mph' } },
    { selector: '#pace-decay', options: { prefix: '~', suffix: '%' } }
  ];

  targetElements.forEach(({ selector, options }) => {
    applyCountUp(selector, Object.assign({ duration: COUNT_UP_DURATION, easing: 'easeOut', replayOnHover: false }, options));
  });
}

// Refresh / re-trigger all CountUp instances on the active view
function triggerViewCountUps(viewId) {
  if (!viewId) return;
  const panelId = 'view-' + viewId.replace('view-', '');
  const panel = document.getElementById(panelId);
  if (!panel) return;

  countUpInstances.forEach((inst, el) => {
    if (panel.contains(el)) {
      setTimeout(() => {
        inst.start();
      }, 50);
    }
  });
}

// Global exports
if (typeof window !== 'undefined') {
  window.CountUp = CountUp;
  window.COUNT_UP_DURATION = COUNT_UP_DURATION;
  window.applyCountUp = applyCountUp;
  window.initWebsiteCountUps = initWebsiteCountUps;
  window.triggerViewCountUps = triggerViewCountUps;
  window.countUpInstances = countUpInstances;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    CountUp,
    COUNT_UP_DURATION,
    applyCountUp,
    initWebsiteCountUps,
    triggerViewCountUps
  };
}
