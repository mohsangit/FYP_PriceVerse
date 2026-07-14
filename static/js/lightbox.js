(function () {
  const overlay = document.createElement("div");
  overlay.className = "pv-lightbox";
  overlay.innerHTML =
    '<div class="pv-lightbox__backdrop" data-lightbox-close></div>' +
    '<div class="pv-lightbox__dialog" role="dialog" aria-modal="true" aria-label="Product image">' +
    '<button type="button" class="pv-lightbox__close" data-lightbox-close aria-label="Close">&times;</button>' +
    '<img class="pv-lightbox__img" alt="" />' +
    "</div>";
  document.body.appendChild(overlay);

  const img = overlay.querySelector(".pv-lightbox__img");

  function openLightbox(src, alt) {
    if (!src) return;
    img.src = src;
    img.alt = alt || "Product image";
    overlay.classList.add("is-open");
    document.body.style.overflow = "hidden";
  }

  function closeLightbox() {
    overlay.classList.remove("is-open");
    document.body.style.overflow = "";
    img.removeAttribute("src");
  }

  document.addEventListener("click", (e) => {
    const trigger = e.target.closest("[data-lightbox-src]");
    if (trigger) {
      e.preventDefault();
      e.stopPropagation();
      openLightbox(trigger.getAttribute("data-lightbox-src"), trigger.getAttribute("data-lightbox-alt"));
      return;
    }
    if (e.target.closest("[data-lightbox-close]")) {
      closeLightbox();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && overlay.classList.contains("is-open")) {
      closeLightbox();
    }
  });
})();
