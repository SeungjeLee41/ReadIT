/* ==========================================================================
   BCDS Investment Landing — interactions & WebGL liquid glass blob
   (no external dependencies)
   ========================================================================== */
(function () {
  "use strict";

  var prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  /* ---------------- nav ---------------- */
  var nav = document.getElementById("nav");
  var navToggle = document.getElementById("navToggle");
  var navMenu = document.getElementById("navMenu");

  function onScroll() {
    nav.classList.toggle("scrolled", window.scrollY > 24);
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  navToggle.addEventListener("click", function () {
    var open = navMenu.classList.toggle("open");
    navToggle.setAttribute("aria-expanded", String(open));
    navToggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  });
  navMenu.addEventListener("click", function (e) {
    if (e.target.tagName === "A") {
      navMenu.classList.remove("open");
      navToggle.setAttribute("aria-expanded", "false");
    }
  });

  document.getElementById("year").textContent = String(new Date().getFullYear());

  /* ---------------- scroll reveal ---------------- */
  var revealEls = document.querySelectorAll("[data-reveal]");
  if (!prefersReduced && "IntersectionObserver" in window) {
    var revealObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("in-view");
            revealObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15, rootMargin: "0px 0px -40px 0px" }
    );
    revealEls.forEach(function (el) {
      var delay = parseInt(el.getAttribute("data-delay") || "0", 10);
      el.style.transitionDelay = delay * 90 + "ms";
      revealObserver.observe(el);
    });
  } else {
    revealEls.forEach(function (el) { el.classList.add("in-view"); });
  }

  /* ---------------- counters ---------------- */
  var counters = document.querySelectorAll("[data-count]");
  function animateCounter(el) {
    var target = parseFloat(el.getAttribute("data-count"));
    var prefix = el.getAttribute("data-prefix") || "";
    var suffix = el.getAttribute("data-suffix") || "";
    var duration = 1600;
    var start = null;
    function frame(ts) {
      if (start === null) start = ts;
      var p = Math.min((ts - start) / duration, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      var value = Math.round(target * eased);
      el.textContent = prefix + value.toLocaleString("en-US") + suffix;
      if (p < 1) requestAnimationFrame(frame);
    }
    if (prefersReduced) {
      el.textContent = prefix + target.toLocaleString("en-US") + suffix;
    } else {
      requestAnimationFrame(frame);
    }
  }
  if ("IntersectionObserver" in window) {
    var countObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            animateCounter(entry.target);
            countObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.5 }
    );
    counters.forEach(function (el) { countObserver.observe(el); });
  } else {
    counters.forEach(animateCounter);
  }

  /* ---------------- tilt cards ---------------- */
  if (finePointer && !prefersReduced) {
    document.querySelectorAll("[data-tilt]").forEach(function (card) {
      card.addEventListener("pointermove", function (e) {
        var r = card.getBoundingClientRect();
        var px = (e.clientX - r.left) / r.width;
        var py = (e.clientY - r.top) / r.height;
        card.style.setProperty("--rx", ((0.5 - py) * 7).toFixed(2) + "deg");
        card.style.setProperty("--ry", ((px - 0.5) * 7).toFixed(2) + "deg");
        card.style.setProperty("--mx", (px * 100).toFixed(1) + "%");
        card.style.setProperty("--my", (py * 100).toFixed(1) + "%");
        card.style.setProperty("--glare", "1");
      });
      card.addEventListener("pointerleave", function () {
        card.style.setProperty("--rx", "0deg");
        card.style.setProperty("--ry", "0deg");
        card.style.setProperty("--glare", "0");
      });
    });
  }

  /* ---------------- magnetic buttons ---------------- */
  if (finePointer && !prefersReduced) {
    document.querySelectorAll("[data-magnetic]").forEach(function (btn) {
      btn.addEventListener("pointermove", function (e) {
        var r = btn.getBoundingClientRect();
        var dx = (e.clientX - (r.left + r.width / 2)) * 0.22;
        var dy = (e.clientY - (r.top + r.height / 2)) * 0.22;
        btn.style.transform = "translate(" + dx.toFixed(1) + "px," + dy.toFixed(1) + "px)";
      });
      btn.addEventListener("pointerleave", function () {
        btn.style.transform = "";
      });
    });
  }

  /* ---------------- custom cursor ---------------- */
  if (finePointer && !prefersReduced) {
    var dot = document.getElementById("cursorDot");
    var ring = document.getElementById("cursorRing");
    var mx = -100, my = -100, rx = -100, ry = -100;
    var cursorShown = false;

    document.addEventListener("pointermove", function (e) {
      mx = e.clientX;
      my = e.clientY;
      if (!cursorShown) {
        cursorShown = true;
        rx = mx; ry = my;
        document.body.classList.add("cursor-on", "custom-cursor");
      }
    });
    document.addEventListener("pointerleave", function () {
      document.body.classList.remove("cursor-on");
      cursorShown = false;
    });

    var hoverables = "a, button, [data-tilt]";
    document.addEventListener("pointerover", function (e) {
      if (e.target.closest(hoverables)) ring.classList.add("is-hover");
    });
    document.addEventListener("pointerout", function (e) {
      if (e.target.closest(hoverables)) ring.classList.remove("is-hover");
    });

    (function cursorLoop() {
      rx += (mx - rx) * 0.16;
      ry += (my - ry) * 0.16;
      dot.style.transform = "translate(" + (mx - 4) + "px," + (my - 4) + "px)";
      ring.style.transform = "translate(" + (rx - 19) + "px," + (ry - 19) + "px)";
      requestAnimationFrame(cursorLoop);
    })();
  }

  /* ---------------- FAQ accordion (one open at a time) ---------------- */
  var faqItems = document.querySelectorAll(".faq-item");
  faqItems.forEach(function (item) {
    item.addEventListener("toggle", function () {
      if (!item.open) return;
      faqItems.forEach(function (other) {
        if (other !== item) other.open = false;
      });
    });
  });

  /* ---------------- contact form → mailto ---------------- */
  var CONTACT_EMAIL = "smilesean41@gmail.com";
  var contactForm = document.getElementById("contactForm");
  if (contactForm) {
    contactForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var data = new FormData(contactForm);
      var name = String(data.get("name") || "").trim();
      var email = String(data.get("email") || "").trim();
      var company = String(data.get("company") || "").trim();
      var message = String(data.get("message") || "").trim();

      var subject = "[BCDS] Demo Request" + (name ? " — " + name : "");
      var body =
        "Name: " + name + "\n" +
        "Email: " + email + "\n" +
        "Company: " + company + "\n\n" +
        message;

      document.getElementById("formNote").hidden = false;

      window.location.href =
        "mailto:" + CONTACT_EMAIL +
        "?subject=" + encodeURIComponent(subject) +
        "&body=" + encodeURIComponent(body);
    });
  }

  /* ==========================================================================
     WebGL liquid glass blob (dependency-free)
     ========================================================================== */
  var canvas = document.getElementById("glCanvas");
  var gl = canvas.getContext("webgl", { alpha: true, antialias: true, premultipliedAlpha: false });
  if (!gl) return; // CSS blobs remain as graceful fallback

  var NOISE_GLSL = [
    "vec3 mod289(vec3 x){return x - floor(x * (1.0/289.0)) * 289.0;}",
    "vec4 mod289(vec4 x){return x - floor(x * (1.0/289.0)) * 289.0;}",
    "vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}",
    "vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}",
    "float snoise(vec3 v){",
    "  const vec2 C = vec2(1.0/6.0, 1.0/3.0);",
    "  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);",
    "  vec3 i = floor(v + dot(v, C.yyy));",
    "  vec3 x0 = v - i + dot(i, C.xxx);",
    "  vec3 g = step(x0.yzx, x0.xyz);",
    "  vec3 l = 1.0 - g;",
    "  vec3 i1 = min(g.xyz, l.zxy);",
    "  vec3 i2 = max(g.xyz, l.zxy);",
    "  vec3 x1 = x0 - i1 + C.xxx;",
    "  vec3 x2 = x0 - i2 + C.yyy;",
    "  vec3 x3 = x0 - D.yyy;",
    "  i = mod289(i);",
    "  vec4 p = permute(permute(permute(i.z + vec4(0.0, i1.z, i2.z, 1.0)) + i.y + vec4(0.0, i1.y, i2.y, 1.0)) + i.x + vec4(0.0, i1.x, i2.x, 1.0));",
    "  float n_ = 0.142857142857;",
    "  vec3 ns = n_ * D.wyz - D.xzx;",
    "  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);",
    "  vec4 x_ = floor(j * ns.z);",
    "  vec4 y_ = floor(j - 7.0 * x_);",
    "  vec4 x = x_ * ns.x + ns.yyyy;",
    "  vec4 y = y_ * ns.x + ns.yyyy;",
    "  vec4 h = 1.0 - abs(x) - abs(y);",
    "  vec4 b0 = vec4(x.xy, y.xy);",
    "  vec4 b1 = vec4(x.zw, y.zw);",
    "  vec4 s0 = floor(b0) * 2.0 + 1.0;",
    "  vec4 s1 = floor(b1) * 2.0 + 1.0;",
    "  vec4 sh = -step(h, vec4(0.0));",
    "  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;",
    "  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;",
    "  vec3 p0 = vec3(a0.xy, h.x);",
    "  vec3 p1 = vec3(a0.zw, h.y);",
    "  vec3 p2 = vec3(a1.xy, h.z);",
    "  vec3 p3 = vec3(a1.zw, h.w);",
    "  vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));",
    "  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;",
    "  vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);",
    "  m = m * m;",
    "  return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));",
    "}"
  ].join("\n");

  var VERT_SRC = [
    "attribute vec3 aPos;",
    "attribute vec3 aNormal;",
    "uniform mat4 uProj;",
    "uniform mat4 uMV;",
    "uniform mat3 uNormalMat;",
    "uniform float uTime;",
    "uniform float uAmp;",
    "varying vec3 vN;",
    "varying vec3 vV;",
    "varying float vNoise;",
    NOISE_GLSL,
    "void main(){",
    "  float n = snoise(aNormal * 1.6 + vec3(uTime * 0.3));",
    "  float n2 = snoise(aNormal * 3.2 - vec3(uTime * 0.42));",
    "  float d = n * uAmp + n2 * uAmp * 0.22;",
    "  vec3 p = aPos + aNormal * d;",
    "  vec4 mv = uMV * vec4(p, 1.0);",
    "  vN = normalize(uNormalMat * aNormal);",
    "  vV = normalize(-mv.xyz);",
    "  vNoise = n;",
    "  gl_Position = uProj * mv;",
    "}"
  ].join("\n");

  var FRAG_SRC = [
    "precision highp float;",
    "varying vec3 vN;",
    "varying vec3 vV;",
    "varying float vNoise;",
    "uniform vec3 uColor;",
    "uniform vec3 uDeep;",
    "uniform float uAlpha;",
    "void main(){",
    "  vec3 N = normalize(vN);",
    "  vec3 V = normalize(vV);",
    "  float fres = pow(1.0 - max(dot(N, V), 0.0), 2.2);",
    "  vec3 L = normalize(vec3(0.55, 0.8, 0.5));",
    "  float spec = pow(max(dot(reflect(-L, N), V), 0.0), 42.0);",
    "  vec3 col = mix(vec3(1.0), uColor, 0.05 + vNoise * 0.04);",
    "  col = mix(col, uColor, smoothstep(0.12, 1.0, fres));",
    "  col = mix(col, uDeep, fres * fres * 0.55);",
    "  col += spec * 0.5;",
    "  float a = (0.05 + fres * 0.55) * uAlpha;",
    "  gl_FragColor = vec4(col, a);",
    "}"
  ].join("\n");

  function compile(type, src) {
    var s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      return null;
    }
    return s;
  }

  var vs = compile(gl.VERTEX_SHADER, VERT_SRC);
  var fs = compile(gl.FRAGMENT_SHADER, FRAG_SRC);
  if (!vs || !fs) return;

  var prog = gl.createProgram();
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
  gl.useProgram(prog);

  /* ---- sphere geometry ---- */
  function createSphere(latBands, lonBands) {
    var positions = [], normals = [], indices = [];
    for (var lat = 0; lat <= latBands; lat++) {
      var theta = (lat * Math.PI) / latBands;
      var sinT = Math.sin(theta), cosT = Math.cos(theta);
      for (var lon = 0; lon <= lonBands; lon++) {
        var phi = (lon * 2 * Math.PI) / lonBands;
        var x = Math.cos(phi) * sinT;
        var y = cosT;
        var z = Math.sin(phi) * sinT;
        positions.push(x, y, z);
        normals.push(x, y, z);
      }
    }
    for (var a = 0; a < latBands; a++) {
      for (var b = 0; b < lonBands; b++) {
        var first = a * (lonBands + 1) + b;
        var second = first + lonBands + 1;
        indices.push(first, second, first + 1, second, second + 1, first + 1);
      }
    }
    return {
      positions: new Float32Array(positions),
      normals: new Float32Array(normals),
      indices: new Uint16Array(indices),
      count: indices.length
    };
  }

  var sphere = createSphere(80, 80);

  function makeBuffer(target, data) {
    var buf = gl.createBuffer();
    gl.bindBuffer(target, buf);
    gl.bufferData(target, data, gl.STATIC_DRAW);
    return buf;
  }
  var posBuf = makeBuffer(gl.ARRAY_BUFFER, sphere.positions);
  var normBuf = makeBuffer(gl.ARRAY_BUFFER, sphere.normals);
  var idxBuf = makeBuffer(gl.ELEMENT_ARRAY_BUFFER, sphere.indices);

  var aPos = gl.getAttribLocation(prog, "aPos");
  var aNormal = gl.getAttribLocation(prog, "aNormal");
  gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
  gl.enableVertexAttribArray(aPos);
  gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 0, 0);
  gl.bindBuffer(gl.ARRAY_BUFFER, normBuf);
  gl.enableVertexAttribArray(aNormal);
  gl.vertexAttribPointer(aNormal, 3, gl.FLOAT, false, 0, 0);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, idxBuf);

  var U = {
    proj: gl.getUniformLocation(prog, "uProj"),
    mv: gl.getUniformLocation(prog, "uMV"),
    normalMat: gl.getUniformLocation(prog, "uNormalMat"),
    time: gl.getUniformLocation(prog, "uTime"),
    amp: gl.getUniformLocation(prog, "uAmp"),
    color: gl.getUniformLocation(prog, "uColor"),
    deep: gl.getUniformLocation(prog, "uDeep"),
    alpha: gl.getUniformLocation(prog, "uAlpha")
  };

  gl.uniform3f(U.color, 0.91, 0.063, 0.18);   /* #E8102E */
  gl.uniform3f(U.deep, 0.7, 0.047, 0.133);    /* #B30C22 */

  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  gl.disable(gl.DEPTH_TEST);
  gl.clearColor(0, 0, 0, 0);

  /* ---- minimal mat4 helpers (column-major) ---- */
  function mat4Identity() {
    return new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]);
  }
  function mat4Perspective(fovy, aspect, near, far) {
    var f = 1 / Math.tan(fovy / 2);
    var nf = 1 / (near - far);
    var out = new Float32Array(16);
    out[0] = f / aspect;
    out[5] = f;
    out[10] = (far + near) * nf;
    out[11] = -1;
    out[14] = 2 * far * near * nf;
    return out;
  }
  function mat4Multiply(a, b) {
    var out = new Float32Array(16);
    for (var c = 0; c < 4; c++) {
      for (var r = 0; r < 4; r++) {
        out[c * 4 + r] =
          a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] +
          a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
      }
    }
    return out;
  }
  function mat4Translate(x, y, z) {
    var m = mat4Identity();
    m[12] = x; m[13] = y; m[14] = z;
    return m;
  }
  function mat4Scale(s) {
    var m = mat4Identity();
    m[0] = s; m[5] = s; m[10] = s;
    return m;
  }
  function mat4RotateX(rad) {
    var c = Math.cos(rad), s = Math.sin(rad);
    var m = mat4Identity();
    m[5] = c; m[6] = s; m[9] = -s; m[10] = c;
    return m;
  }
  function mat4RotateY(rad) {
    var c = Math.cos(rad), s = Math.sin(rad);
    var m = mat4Identity();
    m[0] = c; m[2] = -s; m[8] = s; m[10] = c;
    return m;
  }
  function mat3FromMat4(m) {
    return new Float32Array([m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10]]);
  }

  /* ---- scene state ---- */
  var proj = mat4Identity();
  var wide = true;
  var mouseX = 0, mouseY = 0, smX = 0, smY = 0;

  var orbs = [
    { x: -1.9, y: 0.9, z: -1.2, s: 0.3, amp: 0.10, alpha: 0.45, spd: 0.7, ph: 0.0 },
    { x: -1.2, y: -1.15, z: -0.6, s: 0.2, amp: 0.12, alpha: 0.4, spd: 1.1, ph: 2.1 },
    { x: 2.4, y: -1.15, z: -1.4, s: 0.36, amp: 0.09, alpha: 0.35, spd: 0.55, ph: 4.0 },
    { x: 0.6, y: 1.5, z: -1.8, s: 0.16, amp: 0.14, alpha: 0.4, spd: 1.4, ph: 5.2 }
  ];

  function resize() {
    var dpr = Math.min(window.devicePixelRatio || 1, 1.75);
    var w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    gl.viewport(0, 0, canvas.width, canvas.height);
    proj = mat4Perspective((35 * Math.PI) / 180, w / h, 0.1, 100);
    gl.uniformMatrix4fv(U.proj, false, proj);
    wide = w / h > 0.9;
  }
  window.addEventListener("resize", resize);
  resize();

  if (finePointer) {
    document.addEventListener("pointermove", function (e) {
      mouseX = (e.clientX / window.innerWidth) * 2 - 1;
      mouseY = (e.clientY / window.innerHeight) * 2 - 1;
    });
  }

  var view = mat4Translate(0, 0, -5.6);

  function drawMesh(model, amp, alpha) {
    var mv = mat4Multiply(view, model);
    gl.uniformMatrix4fv(U.mv, false, mv);
    gl.uniformMatrix3fv(U.normalMat, false, mat3FromMat4(model));
    gl.uniform1f(U.amp, amp);
    gl.uniform1f(U.alpha, alpha);
    gl.drawElements(gl.TRIANGLES, sphere.count, gl.UNSIGNED_SHORT, 0);
  }

  var heroVisible = true;
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      heroVisible = entries[0].isIntersecting;
    }).observe(canvas);
  }

  var startTime = performance.now();
  function render() {
    var t = (performance.now() - startTime) / 1000;
    smX += (mouseX - smX) * 0.05;
    smY += (mouseY - smY) * 0.05;

    gl.uniform1f(U.time, t);
    gl.clear(gl.COLOR_BUFFER_BIT);

    /* orbs (background) */
    for (var i = 0; i < orbs.length; i++) {
      var o = orbs[i];
      var fy = Math.sin(t * o.spd + o.ph) * 0.18;
      var model = mat4Multiply(
        mat4Translate(o.x + smX * 0.25, o.y + fy - smY * 0.18, o.z),
        mat4Multiply(mat4RotateY(t * 0.3 + o.ph), mat4Scale(o.s))
      );
      drawMesh(model, o.amp, o.alpha);
    }

    /* main blob */
    var bx = wide ? 1.85 : 0;
    var by = wide ? 0.15 : 1.15;
    var bs = wide ? 1.12 : 0.78;
    var rot = mat4Multiply(
      mat4RotateY(t * 0.12 + smX * 0.55),
      mat4RotateX(smY * 0.35 + Math.sin(t * 0.2) * 0.1)
    );
    var blobModel = mat4Multiply(
      mat4Translate(bx, by, 0),
      mat4Multiply(rot, mat4Scale(bs))
    );
    drawMesh(blobModel, 0.17 + Math.abs(smX) * 0.05, wide ? 0.85 : 0.4);

    if (!prefersReduced) {
      if (heroVisible && !document.hidden) {
        requestAnimationFrame(render);
      } else {
        /* keep polling cheaply until visible again */
        setTimeout(function () { requestAnimationFrame(render); }, 250);
      }
    }
  }
  render();
})();
