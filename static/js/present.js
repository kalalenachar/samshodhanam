/*
  =========================================
  Samshodhana Mandiram Presentation Script
  =========================================
*/

document.addEventListener('DOMContentLoaded', () => {
  initNavbar();
  initParticles();
  initRoadmap();
  initScrollReveal();
  fetchStats();
  initPipelineModal();
});

/* --- Navbar Scroll Effect --- */
function initNavbar() {
  const header = document.querySelector('header');
  window.addEventListener('scroll', () => {
    if (window.scrollY > 50) {
      header.classList.add('scrolled');
    } else {
      header.classList.remove('scrolled');
    }
  });

  // Active Link Tracking based on scroll
  const sections = document.querySelectorAll('section');
  const navLinks = document.querySelectorAll('.nav-link');

  window.addEventListener('scroll', () => {
    let current = '';
    sections.forEach(section => {
      const sectionTop = section.offsetTop;
      const sectionHeight = section.clientHeight;
      if (window.scrollY >= sectionTop - 150) {
        current = section.getAttribute('id');
      }
    });

    navLinks.forEach(link => {
      link.classList.remove('active');
      if (link.getAttribute('href') === `#${current}`) {
        link.classList.add('active');
      }
    });
  });
}

/* --- Particle Canvas Background (Neural & Constellation Mesh) --- */
function initParticles() {
  const canvas = document.getElementById('canvas-particles');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  
  let width = canvas.width = window.innerWidth;
  let height = canvas.height = window.innerHeight;

  const particles = [];
  const particleCount = Math.min(60, Math.floor(width / 25));
  const connectionDistance = 140;

  const mouse = {
    x: null,
    y: null,
    radius: 150
  };

  window.addEventListener('mousemove', (e) => {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
  });

  window.addEventListener('mouseleave', () => {
    mouse.x = null;
    mouse.y = null;
  });

  window.addEventListener('resize', () => {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  });

  class Particle {
    constructor() {
      this.x = Math.random() * width;
      this.y = Math.random() * height;
      this.vx = (Math.random() - 0.5) * 0.4;
      this.vy = (Math.random() - 0.5) * 0.4;
      this.radius = Math.random() * 2 + 1;
      this.alpha = Math.random() * 0.5 + 0.2;
    }

    update() {
      // Repel from mouse cursor
      if (mouse.x !== null && mouse.y !== null) {
        const dx = this.x - mouse.x;
        const dy = this.y - mouse.y;
        const dist = Math.hypot(dx, dy);
        if (dist < mouse.radius) {
          const force = (mouse.radius - dist) / mouse.radius;
          const angle = Math.atan2(dy, dx);
          // Gently push particles away from cursor
          this.x += Math.cos(angle) * force * 1.5;
          this.y += Math.sin(angle) * force * 1.5;
        }
      }

      this.x += this.vx;
      this.y += this.vy;

      // Wrap around bounds or bounce
      if (this.x < 0 || this.x > width) this.vx = -this.vx;
      if (this.y < 0 || this.y > height) this.vy = -this.vy;
    }

    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255, 186, 68, ${this.alpha})`;
      ctx.fill();
    }
  }

  for (let i = 0; i < particleCount; i++) {
    particles.push(new Particle());
  }

  let lastAccentUpdate = 0;
  let activeAccentColor = '#FF9933';

  function animate(timestamp) {
    ctx.clearRect(0, 0, width, height);

    if (timestamp - lastAccentUpdate > 500) {
      activeAccentColor = getComputedStyle(document.documentElement).getPropertyValue('--t-accent').trim() || '#FF9933';
      lastAccentUpdate = timestamp;
    }

    particles.forEach(p => {
      p.update();
      p.draw();
    });

    // Draw lines between close particles (constellation neural network)
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dist = Math.hypot(particles[i].x - particles[j].x, particles[i].y - particles[j].y);
        if (dist < connectionDistance) {
          const alpha = (1 - dist / connectionDistance) * 0.15;
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = activeAccentColor;
          ctx.globalAlpha = alpha;
          ctx.lineWidth = 1;
          ctx.stroke();
          ctx.globalAlpha = 1.0;
        }
      }
    }

    // Draw lines between particles and mouse cursor
    if (mouse.x !== null && mouse.y !== null) {
      particles.forEach(p => {
        const dist = Math.hypot(p.x - mouse.x, p.y - mouse.y);
        if (dist < mouse.radius) {
          const alpha = (1 - dist / mouse.radius) * 0.25;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(mouse.x, mouse.y);
          ctx.strokeStyle = activeAccentColor;
          ctx.globalAlpha = alpha * 1.5;
          ctx.lineWidth = 1.2;
          ctx.stroke();
          ctx.globalAlpha = 1.0;
        }
      });
    }

    requestAnimationFrame(animate);
  }

  animate();
}

/* --- Roadmap Interactive Dashboard --- */
const ROADMAP_DATA = {
  2025: {
    tagline: "Software Architecture & Ingest Setup",
    metrics: [
      { name: "Ingestion Core Schema", pct: 100, status: "completed" },
      { name: "Vedic Unicode Normalizer", pct: 100, status: "completed" },
      { name: "Unified Server Entry Point", pct: 100, status: "completed" }
    ],
    chartMetric: "100%",
    chartLabel: "Architecture Complete",
    badge: "Foundation Year",
    linePath: "M 40,180 L 40,180",
    areaPath: "M 40,180 L 40,180 Z"
  },
  2026: {
    tagline: "First 4% of Corpus Completed & Trained",
    metrics: [
      { name: "Acquire & Vetting Batch", pct: 90, status: "completed" },
      { name: "Page Ingest Pipeline", pct: 40, status: "active" },
      { name: "OCR Ingestion Target", pct: 30, status: "active" }
    ],
    chartMetric: "4,000+",
    chartLabel: "Books in Active Pipeline",
    badge: "Active Ingest",
    linePath: "M 40,180 L 125,170",
    areaPath: "M 40,180 L 125,170 L 125,180 L 40,180 Z"
  },
  2027: {
    tagline: "The 40,000,000+ Pages Verification Blitz",
    metrics: [
      { name: "Pandit-AI Collaborative Editor", pct: 15, status: "active" },
      { name: "Edition Merging Alignment", pct: 20, status: "active" },
      { name: "Target 4 Crore Pages Verification", pct: 10, status: "active" }
    ],
    chartMetric: "4 Crore+",
    chartLabel: "Pages Target Verifying",
    badge: "Scale Verification",
    linePath: "M 40,180 L 125,170 L 210,130",
    areaPath: "M 40,180 L 125,170 L 210,130 L 210,180 L 40,180 Z"
  },
  2028: {
    tagline: "High-Throughput Chunking & Neural Training",
    metrics: [
      { name: "Shloka Commentary Segmenter", pct: 5, status: "planned" },
      { name: "ChromaDB Vector Embedding", pct: 0, status: "planned" },
      { name: "Neural Model Training Setup", pct: 0, status: "planned" }
    ],
    chartMetric: "2.5M+",
    chartLabel: "Semantic Training Chunks",
    badge: "AI Ingestion",
    linePath: "M 40,180 L 125,170 L 210,130 L 295,80",
    areaPath: "M 40,180 L 125,170 L 210,130 L 295,80 L 295,180 L 40,180 Z"
  },
  2029: {
    tagline: "Complete 4 Crore+ Chunks Trained AI LLM",
    metrics: [
      { name: "Multi-Billion Param LLM Training", pct: 0, status: "planned" },
      { name: "Public API Cluster Deployment", pct: 0, status: "planned" },
      { name: "Global Query Terminals", pct: 0, status: "planned" }
    ],
    chartMetric: "40M+",
    chartLabel: "Vector Trained Chunks",
    badge: "Gateway Horizon",
    linePath: "M 40,180 L 125,170 L 210,130 L 295,80 L 380,30",
    areaPath: "M 40,180 L 125,170 L 210,130 L 295,80 L 380,30 L 380,180 L 40,180 Z"
  }
};

function initRoadmap() {
  const nodes = document.querySelectorAll('.roadmap-year-node');
  const fill = document.querySelector('.roadmap-progress-bar-fill');
  const dashYear = document.querySelector('.dash-year-header');
  const dashTagline = document.querySelector('.dash-tagline');
  const dashBadge = document.querySelector('.dash-milestone-badge');

  function updateRoadmap(year, index) {
    // Fill progress bar width
    if (fill) {
      const percentage = (index / (nodes.length - 1)) * 100;
      fill.style.width = `${percentage}%`;
    }

    // Toggle active state
    nodes.forEach((n, idx) => {
      if (idx <= index) {
        n.classList.add('active');
      } else {
        n.classList.remove('active');
      }
    });

    // Update Dashboard Data
    const data = ROADMAP_DATA[year];
    if (data) {
      if (dashYear) dashYear.textContent = year;
      if (dashTagline) dashTagline.textContent = data.tagline;
      if (dashBadge) dashBadge.textContent = data.badge;
      
      // Update visual deliverables list
      const metricsContainer = document.getElementById('roadmap-metrics-visuals');
      if (metricsContainer && data.metrics) {
        metricsContainer.innerHTML = '';
        data.metrics.forEach(m => {
          const card = document.createElement('div');
          card.className = 'roadmap-metric-card';
          card.innerHTML = `
            <div class="roadmap-metric-header">
              <span class="roadmap-metric-title">${m.name}</span>
              <span class="roadmap-metric-status ${m.status}">${m.status}</span>
            </div>
            <div class="roadmap-metric-bar-bg">
              <div class="roadmap-metric-bar-fill" style="width: 0%"></div>
            </div>
            <span style="font-size:0.65rem; color:var(--text-muted); align-self:flex-end; margin-top:2px; font-weight:700;">${m.pct}%</span>
          `;
          metricsContainer.appendChild(card);
          
          setTimeout(() => {
            const fillBar = card.querySelector('.roadmap-metric-bar-fill');
            if (fillBar) fillBar.style.width = m.pct + '%';
          }, 80);
        });
      }

      // Update SVG line chart paths
      const chartLine = document.getElementById('chart-line-path');
      const chartArea = document.getElementById('chart-area-fill');
      if (chartLine && data.linePath) {
        chartLine.setAttribute('d', data.linePath);
      }
      if (chartArea && data.areaPath) {
        chartArea.setAttribute('d', data.areaPath);
      }

      // Highlight active point nodes in SVG chart
      document.querySelectorAll('.chart-point').forEach((pt, idx) => {
        const outerCircle = pt.querySelector('circle');
        const innerCircle = pt.querySelectorAll('circle')[1];
        if (idx <= index) {
          if (outerCircle) {
            outerCircle.setAttribute('stroke', 'var(--secondary-saffron)');
            outerCircle.setAttribute('fill', 'rgba(255, 153, 51, 0.2)');
          }
          if (innerCircle) innerCircle.setAttribute('fill', 'var(--secondary-saffron)');
          pt.style.filter = 'drop-shadow(0 0 5px var(--secondary-saffron))';
        } else {
          if (outerCircle) {
            outerCircle.setAttribute('stroke', 'var(--border-light)');
            outerCircle.setAttribute('fill', 'var(--bg-darkest)');
          }
          if (innerCircle) innerCircle.setAttribute('fill', 'var(--primary-gold)');
          pt.style.filter = 'none';
        }
      });

      // Update overlay metrics box
      const overlayMetric = document.getElementById('chart-overlay-metric');
      const overlayLabel = document.getElementById('chart-overlay-label');
      if (overlayMetric) overlayMetric.textContent = data.chartMetric;
      if (overlayLabel) overlayLabel.textContent = data.chartLabel;
    }
  }

  // Click bindings
  nodes.forEach((node, index) => {
    node.addEventListener('click', () => {
      const year = parseInt(node.getAttribute('data-year'));
      updateRoadmap(year, index);
    });
  });

  // Initialize active roadmap with 2025
  updateRoadmap(2025, 0);
}

/* --- Scroll-driven Reveal Animations (Intersection Observer) --- */
function initScrollReveal() {
  const options = {
    threshold: 0.15,
    rootMargin: "0px 0px -50px 0px"
  };

  const observer = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('reveal-active');
        observer.unobserve(entry.target);
      }
    });
  }, options);

  const revealElements = document.querySelectorAll('.compare-card, .pipeline-chart-card, .roadmap-dashboard, .cta-banner-wrapper, .mission-card, .mission-card-visual');
  
  const style = document.createElement('style');
  style.innerHTML = `
    .compare-card, .pipeline-chart-card, .roadmap-dashboard, .cta-banner-wrapper, .mission-card, .mission-card-visual {
      opacity: 0;
      transform: translateY(30px);
      transition: opacity 0.8s cubic-bezier(0.16, 1, 0.3, 1), transform 0.8s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .reveal-active {
      opacity: 1 !important;
      transform: translateY(0) !important;
    }
  `;
  document.head.appendChild(style);

  revealElements.forEach(el => {
    observer.observe(el);
  });
}

// =============================================================================
// PILLARS CONSTELLATION ACTION SCRIPTS
// =============================================================================
let appStats = null;
let selectedNodeId = null;

function animateValue(obj, start, end, duration) {
    if (!obj) return;
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        obj.innerHTML = Math.floor(progress * (end - start) + start).toLocaleString();
        if (progress < 1) {
            window.requestAnimationFrame(step);
        }
    };
    window.requestAnimationFrame(step);
}

function selectNode(nodeId) {
    selectedNodeId = nodeId;
    document.querySelectorAll('.node-item').forEach(el => el.classList.remove('selected'));
    const nodeEl = document.getElementById('node-' + nodeId);
    if (nodeEl) nodeEl.classList.add('selected');
    
    document.querySelectorAll('.constellation-svg path').forEach(path => {
        path.style.stroke = 'var(--border-light)';
        path.style.strokeWidth = '1.5';
    });
    const pathEl = document.getElementById('path-' + nodeId);
    if (pathEl) {
        pathEl.style.stroke = 'var(--secondary-saffron)';
        pathEl.style.strokeWidth = '3';
    }
    
    const detailTitle = document.getElementById('node-detail-title');
    const detailSanskrit = document.getElementById('node-detail-sanskrit');
    const detailDesc = document.getElementById('node-detail-desc');
    const detailStats = document.getElementById('node-detail-stats');
    
    if (!detailTitle || !detailDesc || !detailStats) return;
    
    let titleText = '';
    let sanskritText = '';
    let descText = '';
    let statsHtml = '';
    
    const countBooks = appStats ? appStats.books : 575;
    const countPages = appStats ? appStats.pages : 266507;
    const countChunks = appStats ? appStats.chunks : 77;
    const countArticles = appStats ? appStats.articles : 0;
    const countStories = appStats ? appStats.stories : 0;
    const countQuizzes = appStats ? appStats.quizzes : 2599;
    const countSubmissions = appStats ? appStats.quiz_submissions : 0;
    const countGames = appStats ? appStats.games_played : 342;
    const countUsers = appStats ? appStats.users : 120;
    
    if (nodeId === 'library') {
        titleText = 'Sanskrit Digital Library';
        sanskritText = 'ग्रन्थालयः';
        descText = 'A comprehensive repository of digitized Sanskrit books, scriptures, and manuscripts, fully searchable at the page level with character highlighting and metadata indices.';
        statsHtml = `
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">${countBooks}</span><span class="sub-stat-lbl-present">Books</span></div>
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">${countPages.toLocaleString()}</span><span class="sub-stat-lbl-present">Pages</span></div>
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">100%</span><span class="sub-stat-lbl-present">OCR Search</span></div>
        `;
    } else if (nodeId === 'chatai') {
        titleText = 'Chat & Vyakhya AI';
        sanskritText = 'संभाषण AI';
        descText = 'Sanskrit dialogue conversational AI assistant that translates text, extracts grammar structures, and answers philosophical inquiries utilizing vectorized data context.';
        statsHtml = `
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">${countChunks}</span><span class="sub-stat-lbl-present">Vector Nodes</span></div>
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">Sanskrit AI</span><span class="sub-stat-lbl-present">Model</span></div>
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">Key Pool</span><span class="sub-stat-lbl-present">Redundancy</span></div>
        `;
    } else if (nodeId === 'games') {
        titleText = 'Sanskrit Games';
        sanskritText = 'क्रीडा';
        descText = 'Educational and interactive Sanskrit games designed to build spelling, vocabulary, and synonym recognition skills in Sanskrit for kids and learners.';
        statsHtml = `
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">3</span><span class="sub-stat-lbl-present">Game Types</span></div>
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">${countGames}</span><span class="sub-stat-lbl-present">Played Runs</span></div>
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">HTML5</span><span class="sub-stat-lbl-present">Core Engine</span></div>
        `;
    } else if (nodeId === 'quizzes') {
        titleText = 'Grammar Quizzes';
        sanskritText = 'प्रश्नोत्तरी';
        descText = 'Customized Sanskrit grammar and textual comprehension quiz banks. Tracks user performance over time to help master Sanskrit verb conjugations and cases.';
        statsHtml = `
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">${countQuizzes}</span><span class="sub-stat-lbl-present">Questions</span></div>
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">${countSubmissions}</span><span class="sub-stat-lbl-present">Submissions</span></div>
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">Level-Based</span><span class="sub-stat-lbl-present">Structure</span></div>
        `;
    } else if (nodeId === 'stories') {
        titleText = 'Puranic Stories';
        sanskritText = 'कथा';
        descText = 'Rich illustrated stories and audio recordings showcasing moral lessons, Puranas, and standard narrative prose for reading and listening.';
        statsHtml = `
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">${countStories}</span><span class="sub-stat-lbl-present">Stories</span></div>
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">Audio</span><span class="sub-stat-lbl-present">Player</span></div>
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">Bilingual</span><span class="sub-stat-lbl-present">Translation</span></div>
        `;
    } else if (nodeId === 'articles') {
        titleText = 'Research Articles';
        sanskritText = 'शोधलेखाः';
        descText = 'Original, scholarly articles exploring complex aspects of Sanskrit literature, digital humanities pipelines, translation methodologies, and linguistics.';
        statsHtml = `
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">${countArticles}</span><span class="sub-stat-lbl-present">Articles</span></div>
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">HTML</span><span class="sub-stat-lbl-present">Formatting</span></div>
            <div class="sub-stat-item-present"><span class="sub-stat-val-present">Peer-Reviewed</span><span class="sub-stat-lbl-present">Standard</span></div>
        `;
    }
    
    if (detailTitle) detailTitle.textContent = titleText;
    if (detailSanskrit) detailSanskrit.textContent = sanskritText;
    if (detailDesc) detailDesc.innerHTML = descText;
    if (detailStats) detailStats.innerHTML = statsHtml;
}

async function fetchStats() {
    try {
        const res = await fetch('/about-stats');
        if (!res.ok) throw new Error("Failed to fetch stats");
        appStats = await res.json();
        
        // Update stats counters on hero
        animateValue(document.getElementById('stat-books'), 0, appStats.books, 1000);
        animateValue(document.getElementById('stat-pages'), 0, appStats.pages, 1200);
        
        // Re-select active node to show live stats
        if (selectedNodeId) selectNode(selectedNodeId);
        else selectNode('library');
    } catch (e) {
        console.error("Error loading stats:", e);
        
        // Offline Fallbacks
        animateValue(document.getElementById('stat-books'), 0, 575, 500);
        animateValue(document.getElementById('stat-pages'), 0, 266507, 500);
        
        selectNode('library');
    }
}

/* --- Pipeline Zoom Modal --- */
function initPipelineModal() {
  const modal = document.getElementById('pipeline-modal');
  const modalClose = document.getElementById('pipeline-modal-close');
  const modalPrev = document.getElementById('pipeline-modal-prev');
  const modalNext = document.getElementById('pipeline-modal-next');
  const modalVisualContainer = document.querySelector('.pipeline-modal-visual-container');
  const modalBadge = document.getElementById('pipeline-modal-badge');
  const modalTitle = document.getElementById('pipeline-modal-title');
  const modalDesc = document.getElementById('pipeline-modal-desc');

  const fsModal = document.getElementById('image-fullscreen-modal');
  const fsClose = document.getElementById('fs-modal-close');
  const fsPrev = document.getElementById('fs-modal-prev');
  const fsNext = document.getElementById('fs-modal-next');
  const fsImage = document.getElementById('fs-preview-image');
  const fsZoomBtn = document.getElementById('fs-modal-zoom');

  if (!modal || !modalClose || !fsModal) return;

  const cards = Array.from(document.querySelectorAll('.pipeline-chart-card'));
  let currentStageIndex = 0;
  let isFsActive = false;

  const updateModalContent = (index) => {
    if (index < 0 || index >= cards.length) return;
    currentStageIndex = index;
    const card = cards[index];

    const img = card.querySelector('.pipeline-stage-img');
    const badge = card.querySelector('.stage-flow-badge');
    const num = card.querySelector('.stage-flow-num');
    const title = card.querySelector('.stage-flow-title');
    const desc = card.querySelector('.stage-flow-desc');
    const visualBox = card.querySelector('.chart-visual-box');

    if (isFsActive) {
      if (img && fsImage) {
        fsImage.src = img.src;
        fsImage.alt = img.alt;
      }
      if (fsPrev) fsPrev.style.display = index === 0 ? 'none' : 'flex';
      if (fsNext) fsNext.style.display = index === cards.length - 1 ? 'none' : 'flex';
    } else {
      if (badge && title && desc && visualBox) {
        modalBadge.textContent = `${num ? num.textContent : ''} - ${badge.textContent}`;
        modalTitle.textContent = title.textContent;
        modalDesc.textContent = desc.textContent;
        
        modalVisualContainer.innerHTML = '';
        const clonedVisual = visualBox.cloneNode(true);
        modalVisualContainer.appendChild(clonedVisual);
      }
      if (modalPrev) modalPrev.style.display = index === 0 ? 'none' : 'flex';
      if (modalNext) modalNext.style.display = index === cards.length - 1 ? 'none' : 'flex';
    }
  };

  const closeDetailedModal = () => {
    modal.classList.remove('open');
    setTimeout(() => {
      modal.style.display = 'none';
      modalVisualContainer.innerHTML = '';
    }, 400);
  };

  const resetZoom = () => {
    if (fsImage) {
      fsImage.classList.remove('zoomed');
    }
    if (fsZoomBtn) {
      const zoomIcon = fsZoomBtn.querySelector('i');
      if (zoomIcon) zoomIcon.className = 'fa-solid fa-magnifying-glass-plus';
    }
  };

  const toggleZoom = () => {
    if (!fsImage) return;
    const isZoomed = fsImage.classList.toggle('zoomed');
    if (fsZoomBtn) {
      const zoomIcon = fsZoomBtn.querySelector('i');
      if (zoomIcon) {
        if (isZoomed) {
          zoomIcon.className = 'fa-solid fa-magnifying-glass-minus';
        } else {
          zoomIcon.className = 'fa-solid fa-magnifying-glass-plus';
        }
      }
    }
  };

  const closeFsModal = () => {
    fsModal.classList.remove('open');
    resetZoom();
    setTimeout(() => {
      fsModal.style.display = 'none';
      if (fsImage) fsImage.src = '';
    }, 400);

    // Exit native browser fullscreen if active
    if (document.fullscreenElement === fsModal || document.webkitFullscreenElement === fsModal || document.msFullscreenElement === fsModal) {
      if (document.exitFullscreen) {
        document.exitFullscreen().catch(err => console.warn(err));
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      } else if (document.msExitFullscreen) {
        document.msExitFullscreen();
      }
    }
  };

  // Synchronize close when native escape exits fullscreen
  const syncFsExit = () => {
    if (!document.fullscreenElement && !document.webkitFullscreenElement && !document.msFullscreenElement && fsModal.classList.contains('open')) {
      fsModal.classList.remove('open');
      resetZoom();
      setTimeout(() => {
        fsModal.style.display = 'none';
        if (fsImage) fsImage.src = '';
      }, 400);
    }
  };
  document.addEventListener('fullscreenchange', syncFsExit);
  document.addEventListener('webkitfullscreenchange', syncFsExit);
  document.addEventListener('MSFullscreenChange', syncFsExit);

  cards.forEach((card, index) => {
    // Click on the image -> Opens fullscreen image modal
    const visualBox = card.querySelector('.chart-visual-box');
    if (visualBox) {
      visualBox.addEventListener('click', (e) => {
        e.stopPropagation();
        isFsActive = true;
        updateModalContent(index);

        fsModal.style.display = 'flex';
        fsModal.offsetHeight; // force reflow
        fsModal.classList.add('open');

        // Request native browser fullscreen
        if (fsModal.requestFullscreen) {
          fsModal.requestFullscreen().catch(err => console.warn(err));
        } else if (fsModal.webkitRequestFullscreen) {
          fsModal.webkitRequestFullscreen();
        } else if (fsModal.msRequestFullscreen) {
          fsModal.msRequestFullscreen();
        }
      });
    }

    // Click on card body/header -> Opens detailed modal
    const cardHeader = card.querySelector('.card-header-flow');
    const cardTitle = card.querySelector('.stage-flow-title');
    const cardDesc = card.querySelector('.stage-flow-desc');
    const openDetailed = (e) => {
      e.stopPropagation();
      isFsActive = false;
      updateModalContent(index);

      modal.style.display = 'flex';
      modal.offsetHeight;
      modal.classList.add('open');
    };

    if (cardHeader) cardHeader.addEventListener('click', openDetailed);
    if (cardTitle) cardTitle.addEventListener('click', openDetailed);
    if (cardDesc) cardDesc.addEventListener('click', openDetailed);
  });

  const goPrev = () => {
    if (currentStageIndex > 0) {
      resetZoom();
      updateModalContent(currentStageIndex - 1);
    }
  };

  const goNext = () => {
    if (currentStageIndex < cards.length - 1) {
      resetZoom();
      updateModalContent(currentStageIndex + 1);
    }
  };

  if (modalPrev) {
    modalPrev.addEventListener('click', (e) => {
      e.stopPropagation();
      goPrev();
    });
  }

  if (modalNext) {
    modalNext.addEventListener('click', (e) => {
      e.stopPropagation();
      goNext();
    });
  }

  if (fsPrev) {
    fsPrev.addEventListener('click', (e) => {
      e.stopPropagation();
      goPrev();
    });
  }

  if (fsNext) {
    fsNext.addEventListener('click', (e) => {
      e.stopPropagation();
      goNext();
    });
  }

  // Keyboard navigation
  window.addEventListener('keydown', (e) => {
    const isDetailedOpen = modal.classList.contains('open');
    const isFsOpen = fsModal.classList.contains('open');
    if (!isDetailedOpen && !isFsOpen) return;

    if (e.key === 'ArrowLeft') {
      goPrev();
    } else if (e.key === 'ArrowRight') {
      goNext();
    } else if (e.key === 'Escape') {
      if (isDetailedOpen) closeDetailedModal();
      if (isFsOpen) closeFsModal();
    }
  });

  modalClose.addEventListener('click', closeDetailedModal);
  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      closeDetailedModal();
    }
  });

  fsClose.addEventListener('click', closeFsModal);
  fsModal.addEventListener('click', (e) => {
    if (e.target === fsModal) {
      closeFsModal();
    }
  });

  // Toggle Zoom on Image click
  if (fsImage) {
    fsImage.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleZoom();
    });
  }

  // Toggle Zoom on Zoom button click
  if (fsZoomBtn) {
    fsZoomBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleZoom();
    });
  }
}

