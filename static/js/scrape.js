(function () {

  function getCookie(name) {

    const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));

    return match ? decodeURIComponent(match[2]) : "";

  }



  function createScrapeController(config) {

    const btn = document.getElementById(config.buttonId);

    const statusEl = document.getElementById(config.statusId);

    const progressEl = document.getElementById(config.progressId);

    if (!btn || !statusEl) return;



    function setStatus(text, state) {

      statusEl.textContent = text;

      statusEl.className = "scrape-status scrape-status--" + state;

    }



    function setProgress(text) {

      if (!progressEl) return;

      progressEl.textContent = text || "";

      progressEl.classList.toggle("scrape-progress--hidden", !text);

    }



    async function pollProgress() {

      while (true) {

        const response = await fetch(config.progressUrl, {

          headers: { "X-Requested-With": "XMLHttpRequest" },

        });

        const data = await response.json().catch(() => ({}));



        if (data.message) {

          const state =

            data.status === "waiting"

              ? "waiting"

              : data.status === "discovering"

                ? "running"

                : data.status === "completed"

                  ? "success"

                  : data.status === "failed"

                    ? "error"

                    : "running";

          setStatus(data.message, state);

        }



        if (data.running) {

          const website = data.current_store ? `Website: ${data.current_store}` : "Preparing scrape...";

          const unitLabel = data.current_store === "WhatMobile" ? "Phone" : "Batch";

          const batchInfo =

            data.total_batches > 0

              ? `${website} • ${unitLabel} ${data.current_batch} of ${data.total_batches}`

              : website;

          const batchProgress =

            data.batch_total > 0

              ? ` • ${data.batch_processed || 0}/${data.batch_total} in current batch`

              : "";

          const counts = [

            `${data.records_processed || 0} processed`,

            `${data.records_added || 0} added`,

            `${data.records_updated || 0} updated`,

          ].join(" • ");

          const pct =

            typeof data.progress_pct === "number" ? ` • ${data.progress_pct}% complete` : "";

          const waitInfo =

            data.status === "waiting" && data.waiting_seconds

              ? ` • waiting ${data.waiting_seconds}s`

              : "";

          setProgress(`${batchInfo}${batchProgress} • ${counts}${pct}${waitInfo}`);

        }



        if (data.status === "completed") {

          setStatus(data.message || "Scraping completed successfully.", "success");

          setProgress("");

          btn.textContent = config.againLabel;

          btn.disabled = false;

          return;

        }



        if (data.status === "failed") {

          setStatus(data.message || "Scraping failed.", "error");

          setProgress("");

          btn.textContent = config.startLabel;

          btn.disabled = false;

          return;

        }



        await new Promise((resolve) => setTimeout(resolve, 2000));

      }

    }



    btn.addEventListener("click", async () => {

      if (btn.disabled) return;



      btn.disabled = true;

      btn.textContent = config.runningLabel;

      setStatus(config.startedMessage, "running");

      setProgress("Initializing batch scrape...");



      const csrf = document.querySelector('meta[name="csrf-token"]')?.content || getCookie("csrftoken");



      try {

        const response = await fetch(config.startUrl, {

          method: "POST",

          headers: {

            "X-CSRFToken": csrf,

            "X-Requested-With": "XMLHttpRequest",

          },

        });



        const data = await response.json().catch(() => ({}));



        if (!response.ok || !data.ok) {

          throw new Error(data.message || "Could not start scraping.");

        }



        await pollProgress();

      } catch (err) {

        setStatus(err.message || "Scraping failed. Please try again.", "error");

        setProgress("");

        btn.textContent = config.startLabel;

        btn.disabled = false;

      }

    });

  }



  createScrapeController({

    buttonId: "startScrapeBtn",

    statusId: "scrapeStatus",

    progressId: "scrapeProgress",

    startUrl: window.PV_SCRAPE_START_URL || "/products/scrape/start/",

    progressUrl: window.PV_SCRAPE_PROGRESS_URL || "/products/scrape/progress/",

    startLabel: "Start Retailer Scraping",

    runningLabel: "Scraping...",

    againLabel: "Scrape Again",

    startedMessage: "Retailer scraping started.",

  });



  createScrapeController({

    buttonId: "startWmScrapeBtn",

    statusId: "wmScrapeStatus",

    progressId: "wmScrapeProgress",

    startUrl: window.PV_WM_SCRAPE_START_URL || "/products/scrape/whatmobile/start/",

    progressUrl: window.PV_WM_SCRAPE_PROGRESS_URL || "/products/scrape/whatmobile/progress/",

    startLabel: "Start WhatMobile Scraping",

    runningLabel: "Scraping WhatMobile...",

    againLabel: "Scrape WhatMobile Again",

    startedMessage: "WhatMobile scraping started.",

  });

})();

