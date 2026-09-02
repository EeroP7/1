/* SR-Kiinteistöt — shared site behaviour */
(function () {
  'use strict';

  /* sticky nav shadow */
  var nav = document.getElementById('nav');
  if (nav) {
    addEventListener('scroll', function () {
      nav.classList.toggle('scrolled', scrollY > 8);
    }, { passive: true });
  }

  /* mobile menu */
  var btn = document.getElementById('menuBtn');
  var links = document.getElementById('navLinks');
  if (btn && links) {
    btn.addEventListener('click', function () {
      var open = links.classList.toggle('open');
      btn.setAttribute('aria-expanded', open);
      btn.setAttribute('aria-label', open ? 'Sulje valikko' : 'Avaa valikko');
    });
    links.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') {
        links.classList.remove('open');
        btn.setAttribute('aria-expanded', 'false');
      }
    });
  }

  var reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* staggered reveal groups: children of [data-stagger] rise in sequence */
  document.querySelectorAll('[data-stagger]').forEach(function (parent) {
    Array.prototype.forEach.call(parent.children, function (child, i) {
      child.classList.add('reveal');
      child.style.transitionDelay = (i * 90) + 'ms';
      child.addEventListener('transitionend', function clear(e) {
        if (e.propertyName === 'opacity') {
          child.style.transitionDelay = '';
          child.removeEventListener('transitionend', clear);
        }
      });
    });
  });

  /* reveal on scroll */
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
  document.querySelectorAll('.reveal').forEach(function (el) { io.observe(el); });

  /* count-up numbers */
  function animateCount(el) {
    var to = parseInt(el.dataset.to, 10);
    function fmt(n) { return n.toLocaleString('en').replace(/,/g, ' '); }
    if (reduced) { el.textContent = fmt(to); return; }
    var t0 = null, dur = 1500;
    function step(t) {
      if (!t0) t0 = t;
      var p = Math.min((t - t0) / dur, 1);
      el.textContent = fmt(Math.round(to * (1 - Math.pow(1 - p, 3))));
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  var counts = document.querySelectorAll('.count');
  if (counts.length) {
    var cio = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { animateCount(e.target); cio.unobserve(e.target); }
      });
    }, { threshold: 0.5 });
    counts.forEach(function (el) {
      if (!reduced) el.textContent = '0';
      cio.observe(el);
    });
  }

  /* hero blueprint: line-drawing entrance */
  var heroSvg = document.querySelector('.hero-art svg');
  if (heroSvg && !reduced && 'animate' in Element.prototype) {
    var shapes = heroSvg.querySelectorAll('path,line,rect,circle');
    var di = 0;
    shapes.forEach(function (el) {
      if (el.getAttribute('stroke') || el.closest('[stroke]')) {
        el.setAttribute('pathLength', '1');
        el.style.strokeDasharray = '1';
        el.style.strokeDashoffset = '1';
        el.animate(
          [{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }],
          { duration: 1300, delay: 250 + di * 26, fill: 'forwards', easing: 'cubic-bezier(.22,.61,.24,1)' }
        );
        di++;
      }
    });
    heroSvg.querySelectorAll('text').forEach(function (el, i) {
      el.style.opacity = '0';
      el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 700, delay: 1400 + i * 120, fill: 'forwards' });
    });
  }

  /* ---------- listings filter (kohteet.html) ---------- */
  var filterBar = document.getElementById('filters');
  if (filterBar) {
    var typeChips = filterBar.querySelectorAll('.chip[data-type]');
    var freeChip = filterBar.querySelector('.chip.free-toggle');
    var countEl = document.getElementById('filterCount');
    var groups = document.querySelectorAll('.listing-group[data-type]');

    var state = { type: 'all', freeOnly: false };

    function apply() {
      var visible = 0;
      groups.forEach(function (group) {
        var typeMatch = state.type === 'all' || group.dataset.type === state.type;
        var rowsShown = 0;
        group.querySelectorAll('tbody tr').forEach(function (row) {
          var statusOk = !state.freeOnly || row.dataset.status === 'free' || row.dataset.status === 'part';
          var show = typeMatch && statusOk;
          row.classList.toggle('hidden', !show);
          if (show) rowsShown++;
        });
        group.classList.toggle('hidden', !typeMatch || rowsShown === 0);
        if (typeMatch && rowsShown > 0) { group.open = true; visible += rowsShown; }
      });
      if (countEl) countEl.textContent = visible + ' kohdetta';
    }

    typeChips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        state.type = chip.dataset.type;
        typeChips.forEach(function (c) { c.setAttribute('aria-pressed', c === chip); });
        apply();
      });
    });
    if (freeChip) {
      freeChip.addEventListener('click', function () {
        state.freeOnly = !state.freeOnly;
        freeChip.setAttribute('aria-pressed', state.freeOnly);
        apply();
      });
    }
    apply();
  }

  /* ---------- contact form (yhteystiedot.html) ---------- */
  var form = document.getElementById('contactForm');
  if (form) {
    var fields = {
      name: form.querySelector('#f-name'),
      company: form.querySelector('#f-company'),
      email: form.querySelector('#f-email'),
      phone: form.querySelector('#f-phone'),
      topic: form.querySelector('#f-topic'),
      msg: form.querySelector('#f-msg')
    };

    function setInvalid(el, invalid) {
      el.closest('.field').classList.toggle('invalid', invalid);
      el.setAttribute('aria-invalid', invalid ? 'true' : 'false');
    }

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var ok = true;

      var nameOk = fields.name.value.trim().length > 1;
      setInvalid(fields.name, !nameOk); ok = ok && nameOk;

      var msgOk = fields.msg.value.trim().length > 4;
      setInvalid(fields.msg, !msgOk); ok = ok && msgOk;

      var emailVal = fields.email.value.trim();
      var phoneVal = fields.phone.value.trim();
      var reachOk = /.+@.+\..+/.test(emailVal) || phoneVal.replace(/\D/g, '').length >= 5;
      setInvalid(fields.email, !reachOk);
      ok = ok && reachOk;

      if (!ok) {
        var firstInvalid = form.querySelector('.field.invalid input, .field.invalid textarea');
        if (firstInvalid) firstInvalid.focus();
        return;
      }

      var subject = 'Yhteydenotto: ' + fields.topic.value + ' — ' + fields.name.value.trim();
      var body = [
        'Nimi: ' + fields.name.value.trim(),
        'Yritys: ' + (fields.company.value.trim() || '-'),
        'Sähköposti: ' + (emailVal || '-'),
        'Puhelin: ' + (phoneVal || '-'),
        'Aihe: ' + fields.topic.value,
        '',
        fields.msg.value.trim()
      ].join('\n');

      location.href = 'mailto:petri.kylvo@sampo-rosenlew.fi'
        + '?subject=' + encodeURIComponent(subject)
        + '&body=' + encodeURIComponent(body);

      var status = document.getElementById('formStatus');
      if (status) {
        status.classList.add('ok');
        status.textContent = 'Sähköpostiohjelmasi avautui — viesti on valmiina lähetettäväksi. Voit myös soittaa suoraan: 040 661 3006.';
      }
    });
  }
})();
