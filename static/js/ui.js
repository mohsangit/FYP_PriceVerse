/* PriceVerse — UI interactions: navbar, mobile menu, scroll reveal,
   page transitions, lazy image fade. Lightweight & dependency-free. */
(function () {
  "use strict";

  var prefersReduced = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- Sticky navbar scroll state ---------- */
  var nav = document.getElementById("siteNav");
  if (nav) {
    var onScroll = function () {
      nav.classList.toggle("nav--scrolled", window.scrollY > 8);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  /* ---------- Mobile menu toggle ---------- */
  var toggle = document.getElementById("navToggle");
  var links = document.getElementById("navLinks");
  if (toggle && links) {
    toggle.addEventListener("click", function () {
      var open = links.classList.toggle("is-open");
      toggle.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    links.addEventListener("click", function (e) {
      if (e.target.tagName === "A") {
        links.classList.remove("is-open");
        toggle.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* ---------- Scroll reveal (IntersectionObserver) ---------- */
  var revealEls = document.querySelectorAll("[data-reveal]");
  if (revealEls.length) {
    if (prefersReduced || !("IntersectionObserver" in window)) {
      revealEls.forEach(function (el) { el.classList.add("is-visible"); });
    } else {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            io.unobserve(entry.target);
          }
        });
      }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
      revealEls.forEach(function (el) { io.observe(el); });
    }
  }

  /* ---------- Lazy image fade-in ---------- */
  document.querySelectorAll(".product__img img").forEach(function (img) {
    var wrap = img.closest(".product__img");
    var done = function () {
      img.classList.remove("is-img-loading");
      img.classList.add("is-img-loaded");
      if (wrap) wrap.classList.remove("is-loading");
    };
    if (img.complete && img.naturalWidth > 0) {
      done();
    } else {
      img.classList.add("is-img-loading");
      if (wrap) wrap.classList.add("is-loading");
      img.addEventListener("load", done);
      img.addEventListener("error", done);
    }
  });

  /* ---------- Smooth page-leave transition ---------- */
  if (!prefersReduced) {
    document.addEventListener("click", function (e) {
      var a = e.target.closest("a");
      if (!a) return;
      var href = a.getAttribute("href");
      if (!href) return;

      // skip new tabs, anchors, downloads, modified clicks, external links
      if (
        a.target === "_blank" ||
        a.hasAttribute("download") ||
        href.charAt(0) === "#" ||
        href.indexOf("mailto:") === 0 ||
        href.indexOf("tel:") === 0 ||
        e.metaKey || e.ctrlKey || e.shiftKey || e.altKey ||
        e.button !== 0
      ) return;

      var url;
      try { url = new URL(a.href, window.location.href); } catch (_) { return; }
      if (url.origin !== window.location.origin) return;
      // same page (incl. hash navigations) -> let browser handle
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;

      e.preventDefault();
      document.body.classList.add("is-leaving");
      window.setTimeout(function () { window.location.href = a.href; }, 220);
    });

    // Restore state when navigating back via bfcache
    window.addEventListener("pageshow", function (ev) {
      if (ev.persisted) document.body.classList.remove("is-leaving");
    });
  }
})();
