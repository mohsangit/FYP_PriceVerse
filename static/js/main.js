(function () {
  const input = document.getElementById("searchInput");
  const btn = document.getElementById("searchBtn");

  function doSearch() {
    const q = (input?.value || "").trim();
    if (!q) {
      alert("Type a product name to search.");
      return;
    }
    window.location.href = "/products/?q=" + encodeURIComponent(q);
  }

  btn?.addEventListener("click", doSearch);
  input?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doSearch();
  });
})();

(function () {
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const isAuthenticated = document.querySelector('meta[name="user-authenticated"]')?.content === "true";
  const countEl = document.querySelector("[data-favorites-count]");

  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
    return match ? decodeURIComponent(match[2]) : "";
  }

  function updateFavoritesCount(count) {
    if (!countEl) return;
    countEl.textContent = String(count);
    countEl.classList.toggle("nav__favorites-count--hidden", count < 1);
  }

  function setButtonState(button, isFavorited) {
    button.classList.toggle("favorite-btn--active", isFavorited);
    button.setAttribute(
      "aria-label",
      isFavorited ? "Remove from favorites" : "Add to favorites"
    );
    button.setAttribute(
      "title",
      isFavorited ? "Remove from favorites" : "Add to favorites"
    );
  }

  document.addEventListener("click", async (event) => {
    const button = event.target.closest(".favorite-btn");
    if (!button) return;

    event.preventDefault();
    event.stopPropagation();

    if (!isAuthenticated) {
      const loginUrl = button.dataset.loginUrl || "/auth/login/";
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.href = loginUrl + "?next=" + next;
      return;
    }

    const url = button.dataset.toggleUrl;
    if (!url || button.classList.contains("favorite-btn--loading")) return;

    button.classList.add("favorite-btn--loading");

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken || getCookie("csrftoken"),
          "X-Requested-With": "XMLHttpRequest",
        },
      });

      if (response.status === 401 || response.status === 403) {
        window.location.href = button.dataset.loginUrl || "/auth/login/";
        return;
      }

      if (!response.ok) {
        throw new Error("Failed to update favorite");
      }

      const data = await response.json();
      setButtonState(button, data.is_favorited);
      updateFavoritesCount(data.favorites_count);

      const card = button.closest(".product");
      const onFavoritesPage = window.location.pathname.includes("/products/favorites");
      if (onFavoritesPage && !data.is_favorited && card) {
        card.style.transition = "opacity .2s, transform .2s";
        card.style.opacity = "0";
        card.style.transform = "scale(.96)";
        setTimeout(() => card.remove(), 200);
      }
    } catch (err) {
      alert("Could not update favorites. Please try again.");
    } finally {
      button.classList.remove("favorite-btn--loading");
    }
  });
})();

(function () {
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const isAuthenticated = document.querySelector('meta[name="user-authenticated"]')?.content === "true";

  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
    return match ? decodeURIComponent(match[2]) : "";
  }

  function setNotifyState(button, isSubscribed) {
    button.classList.toggle("notify-btn--active", isSubscribed);
    const label = button.querySelector(".notify-btn__label");
    if (label) {
      label.textContent = isSubscribed ? "Subscribed" : "Notify Me";
    }
    button.setAttribute(
      "aria-label",
      isSubscribed ? "Unsubscribe from price alerts" : "Notify me when price drops"
    );
    button.setAttribute(
      "title",
      isSubscribed ? "Unsubscribe from price alerts" : "Notify me when price drops"
    );
  }

  document.addEventListener("click", async (event) => {
    const button = event.target.closest(".notify-btn");
    if (!button) return;

    event.preventDefault();
    event.stopPropagation();

    if (!isAuthenticated) {
      const loginUrl = button.dataset.loginUrl || "/auth/login/";
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.href = loginUrl + "?next=" + next;
      return;
    }

    const url = button.dataset.toggleUrl;
    if (!url || button.classList.contains("notify-btn--loading")) return;

    button.classList.add("notify-btn--loading");

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken || getCookie("csrftoken"),
          "X-Requested-With": "XMLHttpRequest",
        },
      });

      if (response.status === 401 || response.status === 403) {
        window.location.href = button.dataset.loginUrl || "/auth/login/";
        return;
      }

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || "Failed to update price alert");
      }

      const data = await response.json();
      setNotifyState(button, data.is_subscribed);
      if (data.email_sent) {
        alert("Confirmation email sent! Check your inbox.");
      }
    } catch (err) {
      alert(err.message || "Could not update price alert. Please try again.");
    } finally {
      button.classList.remove("notify-btn--loading");
    }
  });
})();
