(function () {
  "use strict";

  const filters = document.querySelectorAll("[data-source-filter]");
  if (!filters.length) return;

  filters.forEach((filter) => {
    filter.addEventListener("mousedown", () => {
      filter.classList.add("is-pressed");
    });

    const release = () => filter.classList.remove("is-pressed");
    filter.addEventListener("mouseup", release);
    filter.addEventListener("mouseleave", release);
    filter.addEventListener("blur", release, true);
  });

  document.querySelectorAll("[data-source-clear]").forEach((clearBtn) => {
    clearBtn.addEventListener("click", (event) => {
      event.stopPropagation();
    });
  });
})();
