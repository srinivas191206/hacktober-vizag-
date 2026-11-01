// ============================================================================
//  CARD SLIDE ANIMATION SPEED CONFIGURATION:
// EDIT THESE NUMBERS to adjust card entrance speed & stagger gaps:
//   ANIMATED_CONTENT_DURATION (seconds): 0.8 = Fast, 1.2 = Smooth/Medium [CURRENT], 1.8 = Slower
//   ANIMATED_CONTENT_STAGGER (seconds): 0.08 = Quick wave [CURRENT], 0.15 = Slower wave
// ============================================================================
const ANIMATED_CONTENT_DURATION = 1.9; // <--  CHANGE THIS VALUE TO ADJUST CARD SPEED
const ANIMATED_CONTENT_STAGGER = 0.08;  // <--  CHANGE THIS TO ADJUST GAP BETWEEN CARDS

const DEFAULT_ANIMATED_CONTENT_CONFIG = {
  distance: 100,
  direction: 'vertical',
  duration: ANIMATED_CONTENT_DURATION,
  ease: 'power3.out',
  blur: 0,
  stagger: ANIMATED_CONTENT_STAGGER,
  threshold: 0.1,
  reverse: false,
  initialOpacity: 0,
  animateOpacity: true,
  scale: 1,
  delay: 0
};

// Map of standard GSAP easings to CSS cubic-bezier
const EASING_MAP = {
  'power3.out': 'cubic-bezier(0.215, 0.61, 0.355, 1)',
  'power3.inOut': 'cubic-bezier(0.645, 0.045, 0.355, 1)',
  'power2.out': 'cubic-bezier(0.25, 0.46, 0.45, 0.94)',
  'expo.out': 'cubic-bezier(0.16, 1, 0.3, 1)',
  'ease-out': 'cubic-bezier(0, 0, 0.2, 1)',
  'linear': 'linear'
};

function getInitialTransform(direction, distance, reverse, scale) {
  const dist = reverse ? -distance : distance;
  const scaleStr = (scale && scale !== 1) ? ` scale(${scale})` : '';
  if (direction === 'horizontal') {
    return `translate3d(${dist}px, 0, 0)${scaleStr}`;
  }
  return `translate3d(0, ${dist}px, 0)${scaleStr}`;
}

function isStadiumDRSElement(el) {
  if (!el || !(el instanceof Element)) return false;
  if (el.id === 'stadium-modal' || el.id === 'stadium-3d-canvas-container' || el.id === 'stadium-canvas') {
    return true;
  }
  if (el.closest && (
    el.closest('#stadium-modal') ||
    el.closest('.stadium-modal-backdrop') ||
    el.closest('.stadium-viewport-wrapper') ||
    el.closest('.stadium-drs-hud') ||
    el.closest('.stadium-flight-scrubber')
  )) {
    return true;
  }
  return false;
}

class AnimatedContent {
  constructor(target, options = {}) {
    this.container = typeof target === 'string' ? document.querySelector(target) : target;
    if (!this.container) return;

    // Do not attach to 3D stadium DRS
    if (isStadiumDRSElement(this.container)) return;

    this.config = Object.assign({}, DEFAULT_ANIMATED_CONTENT_CONFIG, options);
    this.easingCss = EASING_MAP[this.config.ease] || this.config.ease || 'cubic-bezier(0.215, 0.61, 0.355, 1)';
    this.isTriggered = false;
    this.items = [];
    this.observer = null;

    this.init();
  }

  init() {
    // If container has multiple children or is a designated container, animate direct child cards in turn
    const isMultiItem = this.container.hasAttribute('data-animated-container') ||
      this.container.classList.contains('animated-content-container') ||
      (this.container.children && this.container.children.length > 1 && !this.config.singleItem);

    const rawItems = isMultiItem ? Array.from(this.container.children) : [this.container];

    // Filter out stadium DRS and non-element nodes
    this.items = rawItems.filter(el => el instanceof Element && !isStadiumDRSElement(el));
    if (this.items.length === 0) return;

    this.prepareInitialState();
    this.setupObserver();
  }

  prepareInitialState() {
    const initialTransform = getInitialTransform(
      this.config.direction,
      this.config.distance,
      this.config.reverse,
      this.config.scale
    );

    this.items.forEach(item => {
      item.classList.add('animated-content-item');
      item.style.opacity = this.config.animateOpacity ? String(this.config.initialOpacity) : '1';
      item.style.transform = initialTransform;
      if (this.config.blur > 0) {
        item.style.filter = `blur(${this.config.blur}px)`;
      }
      item.style.willChange = 'transform, opacity';
    });
  }

  setupObserver() {
    if (typeof IntersectionObserver === 'undefined') {
      this.play();
      return;
    }

    this.observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting && !this.isTriggered) {
          // If the container is currently hidden (e.g. inactive tab), wait until visible
          if (this.container.offsetParent === null && !this.container.closest('.dashboard-view-panel:not(.hidden)')) {
            return;
          }
          this.play();
        }
      });
    }, {
      threshold: this.config.threshold || 0.1,
      rootMargin: '0px 0px 40px 0px'
    });

    this.observer.observe(this.container);
  }

  play() {
    this.isTriggered = true;
    const duration = this.config.duration || 0.8;
    const stagger = this.config.stagger || 0.08;
    const baseDelay = this.config.delay || 0;

    this.items.forEach((item, index) => {
      const delay = baseDelay + (index * stagger);
      const transitionStr = `transform ${duration}s ${this.easingCss} ${delay}s, opacity ${duration}s ${this.easingCss} ${delay}s` +
        (this.config.blur > 0 ? `, filter ${duration}s ${this.easingCss} ${delay}s` : '');

      item.style.transition = transitionStr;

      // Ensure transition is applied cleanly on next animation frame
      requestAnimationFrame(() => {
        item.style.opacity = '1';
        item.style.transform = 'translate3d(0, 0, 0)';
        if (this.config.blur > 0) {
          item.style.filter = 'blur(0px)';
        }
      });

      // Cleanup willChange and transition once animation completes
      const totalMs = Math.round((delay + duration) * 1000) + 60;
      setTimeout(() => {
        if (this.isTriggered) {
          item.style.willChange = 'auto';
          item.style.transform = '';
          item.style.transition = '';
          item.classList.add('animated-content-done');
        }
      }, totalMs);
    });
  }

  reset() {
    this.isTriggered = false;
    const initialTransform = getInitialTransform(
      this.config.direction,
      this.config.distance,
      this.config.reverse,
      this.config.scale
    );

    this.items.forEach(item => {
      item.classList.remove('animated-content-done');
      item.style.transition = 'none';
      item.style.opacity = this.config.animateOpacity ? String(this.config.initialOpacity) : '1';
      item.style.transform = initialTransform;
      if (this.config.blur > 0) {
        item.style.filter = `blur(${this.config.blur}px)`;
      }
      item.style.willChange = 'transform, opacity';
    });
  }

  destroy() {
    if (this.observer) {
      this.observer.disconnect();
    }
  }
}

// Global Registry of AnimatedContent instances
const animatedContentInstances = [];

// Helper to wrap / apply AnimatedContent to a target or list
function applyAnimatedContent(target, options = {}) {
  if (!target) return null;
  if (Array.isArray(target) || target instanceof NodeList) {
    const list = Array.from(target).map(t => applyAnimatedContent(t, options));
    return list;
  }
  const el = typeof target === 'string' ? document.querySelector(target) : target;
  if (!el || isStadiumDRSElement(el)) return null;

  const instance = new AnimatedContent(el, options);
  animatedContentInstances.push(instance);
  return instance;
}

// Initialize AnimatedContent on all cards and parts across all sections of all pages
function initWebsiteAnimatedContent() {
  // Clear any previous instances
  animatedContentInstances.forEach(inst => inst.destroy());
  animatedContentInstances.length = 0;

  // 1. PAGE: Insights Command Center / Overview (#view-overview)
  // Banner Card
  applyAnimatedContent('.overview-banner-card', { singleItem: true, delay: 0 });

  // 6 KPI Cards Grid (Direct children animate in turn with stagger 0.08)
  applyAnimatedContent('.overview-kpi-grid', { stagger: 0.08, delay: 0.05 });

  // Computer Vision Upload Studio Card
  applyAnimatedContent('.command-upload-card', { singleItem: true, delay: 0.1 });

  // Two-Column Deep-Dive Analytics (Length Corridor & Stumps Line Cards staggered)
  applyAnimatedContent('.command-two-col-grid', { stagger: 0.08, delay: 0.12 });

  // Recorded Deliveries Live Feed Card
  applyAnimatedContent('.command-deliveries-card', { singleItem: true, delay: 0.15 });

  // 2. PAGE: Bowling Sessions & Spells Manager (#view-sessions)
  // Hero Section Card
  applyAnimatedContent('.create-session-hero .hero-card', { singleItem: true, delay: 0 });

  // Saved Sessions Grid (if present)
  applyAnimatedContent('#saved-sessions-container', { stagger: 0.08, delay: 0.08 });

  // 3. PAGE: Delivery Vision Studio (#view-delivery-studio)
  // Spell Status Bar Card
  applyAnimatedContent('.session-overview-card', { singleItem: true, delay: 0 });

  // Ball Timeline Carousel Strip Card
  applyAnimatedContent('.timeline-strip-card', { singleItem: true, delay: 0.06 });

  // Workspace Two-Column Grid (Upload Studio on Left | Player Studio on Right)
  applyAnimatedContent('.delivery-analysis-grid', { stagger: 0.08, delay: 0.1 });

  // Live Delivery Metrics HUD Bar (4 Telemetry tiles inside player studio)
  applyAnimatedContent('.telemetry-grid-card', { stagger: 0.08, delay: 0.15 });

  // 4. PAGE: Spell Analytics & Multi-Ball Hawk-Eye (#view-spell-insights)
  // Overall Session Performance Banner Card
  applyAnimatedContent('.section-banner', { singleItem: true, delay: 0 });

  // 4 Top KPI Cards Grid (staggered in turn: 0s, 0.08s, 0.16s, 0.24s)
  applyAnimatedContent('.insights-kpi-grid', { stagger: 0.08, delay: 0.06 });

  // Performance Views Navigation Tabs Bar
  applyAnimatedContent('.perf-tabs-bar', { singleItem: true, delay: 0.08 });

  // Performance Cards Grid: Row 1 (Pitch Heatmap Card & Side View Card)
  const perfRows = document.querySelectorAll('.perf-grid-row');
  if (perfRows.length >= 1) {
    applyAnimatedContent(perfRows[0], { stagger: 0.08, delay: 0.1 });
  }
  if (perfRows.length >= 2) {
    applyAnimatedContent(perfRows[1], { stagger: 0.08, delay: 0.12 });
  }

  // Release Points Sub-tiles
  applyAnimatedContent('.release-metrics-grid', { stagger: 0.08, delay: 0.15 });

  // Pace Progression Sub-tiles
  applyAnimatedContent('.pace-metrics-grid', { stagger: 0.08, delay: 0.15 });

  // Length Distribution & Coaching Advice Card
  applyAnimatedContent('.distribution-card', { singleItem: true, delay: 0.14 });

  // Delivery Comprehensive Log Table Card
  applyAnimatedContent('.deliveries-table-card', { singleItem: true, delay: 0.16 });

  // 5. SIDEBAR: Active Bowler Profile Card
  applyAnimatedContent('.sidebar-bowler-card', { singleItem: true, delay: 0.2 });

  // Trigger elements on current active view
  const currentPanel = document.querySelector('.dashboard-view-panel:not(.hidden)');
  if (currentPanel) {
    triggerViewAnimatedContent(currentPanel.id.replace('view-', ''));
  }
}

// Trigger animation on all cards when switching to a view
function triggerViewAnimatedContent(viewId) {
  if (!viewId) return;
  const panelId = 'view-' + viewId.replace('view-', '');
  const panel = document.getElementById(panelId);
  if (!panel) return;

  // Find all AnimatedContent instances belonging to this panel
  const panelInstances = animatedContentInstances.filter(inst => {
    return inst.container && panel.contains(inst.container);
  });

  // Reset and play visible ones
  panelInstances.forEach((inst, index) => {
    inst.reset();

    // Check if element is in viewport
    const rect = inst.container.getBoundingClientRect();
    const inViewport = (rect.top <= window.innerHeight * 0.95 && rect.bottom >= 0);

    if (inViewport) {
      setTimeout(() => {
        inst.play();
      }, 30 + (index * 40));
    }
  });
}

// Global exports
if (typeof window !== 'undefined') {
  window.AnimatedContent = AnimatedContent;
  window.applyAnimatedContent = applyAnimatedContent;
  window.initWebsiteAnimatedContent = initWebsiteAnimatedContent;
  window.triggerViewAnimatedContent = triggerViewAnimatedContent;
  window.animatedContentInstances = animatedContentInstances;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    AnimatedContent,
    applyAnimatedContent,
    initWebsiteAnimatedContent,
    triggerViewAnimatedContent
  };
}
