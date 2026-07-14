(function () {

  "use strict";



  var selA = document.getElementById("cmpA");

  var selB = document.getElementById("cmpB");



  function syncDisabledOptions() {

    if (!selA || !selB) return;

    [[selA, selB], [selB, selA]].forEach(function (pair) {

      var source = pair[0], target = pair[1];

      Array.prototype.forEach.call(target.options, function (opt) {

        if (!opt.value) return;

        opt.disabled = opt.value === source.value && source.value !== "";

      });

    });

  }



  if (selA && selB) {

    selA.addEventListener("change", syncDisabledOptions);

    selB.addEventListener("change", syncDisabledOptions);

    syncDisabledOptions();

  }



  var cmpForm = document.getElementById("cmpForm");

  var pageLoading = document.getElementById("cmpPageLoading");

  var startBtn = document.getElementById("cmpStartBtn");

  var resultsLoading = document.getElementById("cmpResultsLoading");

  var resultsContent = document.getElementById("cmpResultsContent");



  if (cmpForm) {

    cmpForm.addEventListener("submit", function (e) {

      if (!selA || !selB || !selA.value || !selB.value) {

        e.preventDefault();

        alert("Please select a phone in both dropdowns.");

        return;

      }

      if (selA.value === selB.value) {

        e.preventDefault();

        alert("Please choose two different phones.");

        return;

      }



      try {

        sessionStorage.setItem("cmpResultsPending", "1");

      } catch (err) {

        /* ignore */

      }



      if (pageLoading) {

        pageLoading.hidden = false;

        pageLoading.setAttribute("aria-hidden", "false");

      }

      if (startBtn) {

        startBtn.disabled = true;

        startBtn.textContent = "Loading…";

      }

    });

  }



  function resetCompareUi() {

    if (pageLoading) {

      pageLoading.hidden = true;

      pageLoading.setAttribute("aria-hidden", "true");

    }

    if (startBtn) {

      startBtn.disabled = false;

      startBtn.textContent = "Start Comparison →";

    }

  }



  function revealResultsPage() {

    if (resultsLoading) {

      resultsLoading.hidden = true;

      resultsLoading.setAttribute("aria-hidden", "true");

    }

    if (resultsContent) {

      resultsContent.classList.remove("is-pending");

    }

    try {

      sessionStorage.removeItem("cmpResultsPending");

    } catch (err) {

      /* ignore */

    }

  }



  function initResultsPage() {

    if (!resultsContent) return;



    var pending = false;

    try {

      pending = sessionStorage.getItem("cmpResultsPending") === "1";

    } catch (err) {

      pending = true;

    }



    if (!pending && resultsLoading) {

      resultsLoading.hidden = true;

      resultsLoading.setAttribute("aria-hidden", "true");

      resultsContent.classList.remove("is-pending");

      return;

    }



    window.requestAnimationFrame(function () {

      window.setTimeout(revealResultsPage, 180);

    });

  }



  document.addEventListener("DOMContentLoaded", function () {

    resetCompareUi();

    initResultsPage();

  });



  window.addEventListener("pageshow", function () {

    resetCompareUi();

    if (resultsContent && resultsContent.classList.contains("is-pending")) {

      initResultsPage();

    }

  });

})();

