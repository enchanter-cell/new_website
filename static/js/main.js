/* 格物 · 交互脚本
   导航 / 阅读进度 / Canvas 配图 / 滚动动画 / 搜索守卫 / 评论表单 / 登录注册校验 / flash 提示
   （文章与书目的筛选、搜索已改为服务端渲染，不再需要 JS） */
(function () {
  'use strict';

  document.documentElement.classList.add('js-anim');

  /* ---------- 工具 ---------- */
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function toast(msg, type) {
    var stack = $('#toastStack');
    if (!stack) return;
    var el = document.createElement('div');
    el.className = 'toast' + (type ? ' ' + type : '');
    el.innerHTML = '<i></i><span></span>';
    el.lastChild.textContent = msg;
    stack.appendChild(el);
    setTimeout(function () {
      el.classList.add('is-out');
      setTimeout(function () { el.remove(); }, 240);
    }, 3200);
  }
  window.gwToast = toast;

  /* ---------- 1. 导航 ---------- */
  var header = $('#siteHeader');
  var nav = $('#siteNav');
  var navToggle = $('#navToggle');

  function onScrollHeader() {
    if (header) header.classList.toggle('is-scrolled', window.scrollY > 8);
  }
  window.addEventListener('scroll', onScrollHeader, { passive: true });
  onScrollHeader();

  if (navToggle && nav) {
    navToggle.addEventListener('click', function () {
      var open = nav.classList.toggle('is-open');
      navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    $$('.nav-link', nav).forEach(function (a) {
      a.addEventListener('click', function () {
        nav.classList.remove('is-open');
        navToggle.setAttribute('aria-expanded', 'false');
      });
    });
  }

  /* ---------- 2. 阅读进度 + 目录高亮 ---------- */
  var bar = $('#readProgress');
  var barFill = bar ? bar.firstElementChild : null;
  var prose = $('.prose');

  if (bar && barFill && prose) {
    bar.hidden = false;
    var tick = function () {
      var total = prose.offsetHeight - window.innerHeight * 0.6;
      var passed = window.scrollY - (prose.offsetTop - window.innerHeight * 0.4);
      var p = total > 0 ? Math.min(1, Math.max(0, passed / total)) : 0;
      barFill.style.width = (p * 100).toFixed(2) + '%';
    };
    window.addEventListener('scroll', tick, { passive: true });
    window.addEventListener('resize', tick);
    tick();
  }

  var tocLinks = $$('.toc a');
  if (tocLinks.length && 'IntersectionObserver' in window) {
    var heads = tocLinks.map(function (a) { return document.querySelector(a.getAttribute('href')); }).filter(Boolean);
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        tocLinks.forEach(function (a) {
          a.classList.toggle('is-current', a.getAttribute('href') === '#' + en.target.id);
        });
      });
    }, { rootMargin: '-88px 0px -70% 0px' });
    heads.forEach(function (h) { io.observe(h); });
  }

  /* ---------- 3. 卡片配图（Canvas 绘制，无外链图片） ---------- */
  var T = 'rgba(126,226,214,';   // 青色前缀，省得每处写全

  function drawArt(canvas) {
    var kind = canvas.dataset.art || 'net';
    var w = canvas.clientWidth || 400;
    var h = canvas.clientHeight || 225;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    var ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    // 固定种子伪随机：同一张卡每次刷新图形一致
    var seed = parseInt(canvas.dataset.seed || '3', 10) || 3;
    var rnd = (function (s) {
      return function () { s = (s * 9301 + 49297) % 233280; return s / 233280; };
    })(seed * 17 + 11);

    // 深色底 + 两个光晕（所有图形共用）
    var g = ctx.createLinearGradient(0, 0, w, h);
    g.addColorStop(0, '#0c1418');
    g.addColorStop(1, '#121e23');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
    [[0.72, 0.26, 0.55, '79,209,197', .34], [0.18, 0.86, 0.5, '86,116,255', .28]].forEach(function (o) {
      var gl = ctx.createRadialGradient(w * o[0], h * o[1], 0, w * o[0], h * o[1], w * o[2]);
      gl.addColorStop(0, 'rgba(' + o[3] + ',' + o[4] + ')');
      gl.addColorStop(1, 'rgba(' + o[3] + ',0)');
      ctx.fillStyle = gl;
      ctx.fillRect(0, 0, w, h);
    });
    ctx.lineWidth = 1;

    if (kind === 'net') {            // 粒子网络：点 + 近距连线
      var pts = [];
      for (var i = 0; i < 26; i++) pts.push({ x: rnd() * w, y: rnd() * h, r: 0.8 + rnd() * 1.6 });
      var link = w * 0.19;
      for (var a = 0; a < pts.length; a++) {
        for (var b = a + 1; b < pts.length; b++) {
          var dx = pts[a].x - pts[b].x, dy = pts[a].y - pts[b].y;
          var d = Math.sqrt(dx * dx + dy * dy);
          if (d < link) {
            ctx.strokeStyle = T + (0.26 * (1 - d / link)).toFixed(3) + ')';
            ctx.beginPath(); ctx.moveTo(pts[a].x, pts[a].y); ctx.lineTo(pts[b].x, pts[b].y); ctx.stroke();
          }
        }
      }
      pts.forEach(function (p) {
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(190,240,235,.9)'; ctx.fill();
      });
    } else if (kind === 'wave') {    // 波形：四条正弦叠加 + 中线
      for (var k = 0; k < 4; k++) {
        ctx.beginPath();
        ctx.strokeStyle = T + (0.5 - k * 0.1).toFixed(2) + ')';
        ctx.lineWidth = 1.3;
        for (var x = 0; x <= w; x += 4) {
          var y = h * 0.5 + Math.sin(x / (34 + k * 16) + k * 1.2 + seed) * (h * (0.16 - k * 0.025)) + Math.sin(x / 11 + k) * 3;
          x ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
        }
        ctx.stroke();
      }
      ctx.strokeStyle = 'rgba(255,255,255,.15)';
      ctx.beginPath(); ctx.moveTo(0, h * 0.5); ctx.lineTo(w, h * 0.5); ctx.stroke();
    } else if (kind === 'orbit') {   // 轨道：四条椭圆 + 中心光核
      var cx = w * 0.5, cy = h * 0.52;
      for (var o = 1; o <= 4; o++) {
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(200,235,232,' + (0.3 - o * 0.05).toFixed(2) + ')';
        ctx.ellipse(cx, cy, w * 0.1 * o, h * 0.12 * o, -0.3, 0, Math.PI * 2);
        ctx.stroke();
        var ang = rnd() * Math.PI * 2;
        var px = cx + Math.cos(ang) * w * 0.1 * o * Math.cos(-0.3) - Math.sin(ang) * h * 0.12 * o * Math.sin(-0.3);
        var py = cy + Math.cos(ang) * h * 0.12 * o * Math.sin(-0.3) + Math.sin(ang) * h * 0.12 * o * Math.cos(-0.3);
        ctx.beginPath(); ctx.arc(px, py, 2.4, 0, Math.PI * 2);
        ctx.fillStyle = T + '.95)'; ctx.fill();
      }
      var core = ctx.createRadialGradient(cx, cy, 0, cx, cy, h * 0.22);
      core.addColorStop(0, 'rgba(255,255,255,.95)');
      core.addColorStop(0.4, T + '.55)');
      core.addColorStop(1, T + '0)');
      ctx.fillStyle = core;
      ctx.beginPath(); ctx.arc(cx, cy, h * 0.22, 0, Math.PI * 2); ctx.fill();
    } else if (kind === 'grid') {    // 点阵：右上向左下衰减
      var step = 18;
      for (var gx = 0; gx < w; gx += step) {
        for (var gy = 0; gy < h; gy += step) {
          var dist = Math.sqrt(Math.pow(gx - w * 0.7, 2) + Math.pow(gy - h * 0.3, 2));
          var alpha = Math.max(0, 0.5 - dist / (w * 0.85));
          ctx.beginPath(); ctx.arc(gx, gy, 1.1, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(190,240,235,' + alpha.toFixed(3) + ')'; ctx.fill();
        }
      }
    } else if (kind === 'bars') {    // 柱状：22 根渐变柱
      var n = 22, bw = w / n;
      for (var j = 0; j < n; j++) {
        var bh = (0.18 + rnd() * 0.62) * h;
        var grd = ctx.createLinearGradient(0, h - bh, 0, h);
        grd.addColorStop(0, T + '.85)');
        grd.addColorStop(1, T + '.06)');
        ctx.fillStyle = grd;
        ctx.fillRect(j * bw + 1.5, h - bh, bw - 3, bh);
      }
    }

    // 细网格叠加
    ctx.strokeStyle = 'rgba(255,255,255,.05)';
    for (var vx = 0; vx < w; vx += 40) { ctx.beginPath(); ctx.moveTo(vx, 0); ctx.lineTo(vx, h); ctx.stroke(); }
    for (var vy = 0; vy < h; vy += 40) { ctx.beginPath(); ctx.moveTo(0, vy); ctx.lineTo(w, vy); ctx.stroke(); }
  }

  function renderArts() { $$('canvas[data-art]').forEach(drawArt); }
  renderArts();
  var rt;
  window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(renderArts, 220); });

  /* ---------- 4. 滚动出现 ---------- */
  var reveals = $$('.reveal');
  if (reveals.length) {
    if ('IntersectionObserver' in window) {
      var ro = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting) { en.target.classList.add('is-in'); ro.unobserve(en.target); }
        });
      }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
      reveals.forEach(function (el, idx) {
        el.style.transitionDelay = Math.min(idx % 3, 2) * 70 + 'ms';
        ro.observe(el);
      });
    } else {
      reveals.forEach(function (el) { el.classList.add('is-in'); });
    }
  }

  /* ---------- 5. 筛选与搜索（已改为服务端） ----------
     筛选 chips 和 hero 搜索原来是 JS 在浏览器里“藏卡片”实现的，
     现在改成了链接跳转 / 表单 GET，由 Flask 查 SQL 后返回结果页：
     筛选状态进 URL，可分享、可后退、翻页不丢。这里不再需要任何 JS。
     只留一个空关键词守卫：搜索框为空时阻止提交并提示，避免白跳一页。 */
  var heroSearch = $('.hero-search');
  if (heroSearch) {
    heroSearch.addEventListener('submit', function (e) {
      if (!$('input', heroSearch).value.trim()) {
        e.preventDefault();
        toast('先输入一个关键词试试，比如「量子」', 'warn');
      }
    });
  }

  /* ---------- 6. 评论表单：星级 / 字数 / 快捷标签 / 提交 ---------- */
  var ratingBox = $('#ratingBox');
  var ratingValue = 0;
  var ratingText = { 1: '1 星 · 没读懂', 2: '2 星 · 一般', 3: '3 星 · 不错', 4: '4 星 · 很好', 5: '5 星 · 强烈推荐' };

  function paintRating(v) {
    $$('button', ratingBox).forEach(function (b, i) {
      b.classList.toggle('is-on', i < v);
      b.textContent = i < v ? '★' : '☆';
    });
    var lab = $('#ratingLabel');
    if (lab) lab.textContent = v ? ratingText[v] : '还没有评分';
    var hidden = $('#starsInput');          // 星级写进隐藏域，POST 才带得上
    if (hidden) hidden.value = v;
  }

  if (ratingBox) {
    $$('button', ratingBox).forEach(function (btn, i) {
      btn.addEventListener('click', function () { ratingValue = i + 1; paintRating(ratingValue); });
      btn.addEventListener('mouseenter', function () { paintRating(i + 1); });
    });
    ratingBox.addEventListener('mouseleave', function () { paintRating(ratingValue); });
    paintRating(0);
  }

  var commentInput = $('#commentBody');
  var counter = $('#charCount');
  function updateCount() {
    if (!commentInput || !counter) return;
    var len = commentInput.value.length;
    counter.textContent = len + ' / 500';
    counter.style.color = len > 500 ? 'var(--danger)' : '';
  }
  if (commentInput) {
    commentInput.addEventListener('input', updateCount);
    updateCount();
  }

  $$('[data-quick-tag]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (!commentInput) return;
      var cur = commentInput.value.trim();
      commentInput.value = cur ? btn.dataset.quickTag + '：' + cur : btn.dataset.quickTag + '：';
      commentInput.focus();
      updateCount();
    });
  });

  /* 前端只拦不合格的提交；合格就放行给 Flask，后端会再校验一遍 */
  var commentForm = $('#commentForm');
  if (commentForm) {
    commentForm.addEventListener('submit', function (e) {
      var name = $('#guestName');
      if (name && !name.value.trim()) {
        e.preventDefault();
        name.focus(); name.classList.add('shake');
        setTimeout(function () { name.classList.remove('shake'); }, 400);
        toast('请填写你的昵称', 'warn');
        return;
      }
      if (commentInput && commentInput.value.trim().length < 10) {
        e.preventDefault();
        commentInput.focus();
        toast('评论至少写 10 个字，方便作者回应你', 'warn');
        return;
      }
      if (!ratingValue) {
        e.preventDefault();
        toast('顺手点个星级评价吧', 'warn');
        return;
      }
      var btn = $('button[type="submit"]', commentForm);
      if (btn) { btn.disabled = true; btn.textContent = '发布中…'; }
    });
  }

  /* ---------- 7. 登录 / 注册 ---------- */
  $$('[data-pw-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var input = document.getElementById(btn.dataset.pwToggle);
      if (!input) return;
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.textContent = show ? '隐藏' : '显示';
    });
  });

  var pwInput = $('#password');
  var meter = $('#pwMeter');
  if (pwInput && meter) {
    pwInput.addEventListener('input', function () {
      var v = pwInput.value, score = 0;
      if (v.length >= 8) score++;
      if (/[a-z]/i.test(v) && /[0-9]/.test(v)) score++;
      if (/[^a-zA-Z0-9]/.test(v)) score++;
      if (v.length >= 12) score++;
      meter.dataset.score = v ? String(Math.max(1, score)) : '0';
      var tip = $('#pwTip');
      if (tip) {
        tip.textContent = !v ? '建议 8 位以上，含字母与数字'
          : score <= 1 ? '强度偏弱，容易猜中'
          : score === 2 ? '强度中等，可再加入符号'
          : score === 3 ? '强度良好，够用了'
          : '强度很高，记得自己也别忘';
      }
    });
  }

  var loginForm = $('#loginForm');
  if (loginForm) {
    loginForm.addEventListener('submit', function (e) {
      var acc = $('#account').value.trim();
      var pw = $('#password').value;
      if (!acc) { e.preventDefault(); toast('请输入邮箱', 'warn'); $('#account').focus(); return; }
      if (pw.length < 6) { e.preventDefault(); toast('密码至少 6 位', 'warn'); $('#password').focus(); return; }
      var btn = $('button[type="submit"]', loginForm);
      if (btn) { btn.disabled = true; btn.textContent = '登录中…'; }
    });
  }

  var registerForm = $('#registerForm');
  if (registerForm) {
    registerForm.addEventListener('submit', function (e) {
      var nick = $('#nickname').value.trim();
      var mail = $('#email').value.trim();
      var pw = $('#password').value;
      var pw2 = $('#password2').value;
      var agree = $('#agree');

      if (nick.length < 2) { e.preventDefault(); toast('昵称至少 2 个字', 'warn'); $('#nickname').focus(); return; }
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(mail)) { e.preventDefault(); toast('邮箱格式看起来不对', 'warn'); $('#email').focus(); return; }
      if (pw.length < 8) { e.preventDefault(); toast('密码至少 8 位', 'warn'); $('#password').focus(); return; }
      if (pw !== pw2) {
        e.preventDefault();
        toast('两次输入的密码不一致', 'err');
        $('#password2').focus();
        registerForm.classList.add('shake');
        setTimeout(function () { registerForm.classList.remove('shake'); }, 400);
        return;
      }
      if (agree && !agree.checked) { e.preventDefault(); toast('请先同意内容与隐私条款', 'warn'); return; }
      var btn = $('button[type="submit"]', registerForm);
      if (btn) { btn.disabled = true; btn.textContent = '创建中…'; }
    });
  }

  /* ---------- 8. 轻交互：收藏 / 分享 / 订阅 / 演示按钮 / 兴趣多选 / flash ---------- */
  $$('[data-action]').forEach(function (el) {
    el.addEventListener('click', function () {
      var act = el.dataset.action;
      if (act === 'bookmark') {
        toast(el.classList.toggle('is-on') ? '已加入收藏' : '已取消收藏');
      } else if (act === 'share') {
        var url = window.location.href;
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(url).then(
            function () { toast('链接已复制，去分享给同学吧'); },
            function () { toast('复制失败，可以手动复制地址栏链接', 'warn'); });
        } else {
          toast('当前浏览器不支持一键复制，请手动复制地址栏链接', 'warn');
        }
      } else if (act === 'like') {
        el.classList.toggle('is-on');
      }
    });
  });

  var subForm = $('#subForm');
  if (subForm) {
    subForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var v = $('input', subForm).value.trim();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v)) { toast('请输入正确的邮箱地址', 'warn'); return; }
      $('input', subForm).value = '';
      toast('订阅成功，每周一封科普信（演示模式）');
    });
  }

  $$('[data-demo]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      e.preventDefault();
      toast(el.dataset.demo + ' 功能此处为演示，未接入后端');
    });
  });

  $$('[data-pick]').forEach(function (btn) {
    btn.setAttribute('aria-pressed', 'false');
    btn.addEventListener('click', function () {
      var on = btn.getAttribute('aria-pressed') === 'true';
      btn.setAttribute('aria-pressed', on ? 'false' : 'true');
    });
  });

  /* flash 消息：几秒后自动淡出 */
  $$('#flashZone .flash').forEach(function (el) {
    setTimeout(function () {
      el.classList.add('is-out');
      setTimeout(function () { el.remove(); }, 320);
    }, 4500);
  });

  /* 评论页：清空重写后同步字数与星级 */
  var resetBtn = $('#resetForm');
  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      setTimeout(function () {
        updateCount();
        ratingValue = 0;
        paintRating(0);
      }, 0);
    });
  }
})();