"use strict";

const shareDialog = document.getElementById("share-dialog");
const noticeDialog = document.getElementById("notice-dialog");

function absoluteUrl(value) {
  try {
    return new URL(value || window.location.href, window.location.origin).href;
  } catch {
    return window.location.href;
  }
}

function openShare(title, value) {
  const url = absoluteUrl(value);
  const text = title || document.title;
  const encodedUrl = encodeURIComponent(url);
  const encodedText = encodeURIComponent(text);

  if (shareDialog && typeof shareDialog.showModal === "function") {
    const links = {
      whatsapp: `https://wa.me/?text=${encodeURIComponent(`${text} ${url}`)}`,
      telegram: `https://t.me/share/url?url=${encodedUrl}&text=${encodedText}`,
      linkedin: `https://www.linkedin.com/sharing/share-offsite/?url=${encodedUrl}`,
      reddit: `https://www.reddit.com/submit?url=${encodedUrl}&title=${encodedText}`,
      x: `https://twitter.com/intent/tweet?url=${encodedUrl}&text=${encodedText}`,
      facebook: `https://www.facebook.com/sharer/sharer.php?u=${encodedUrl}`,
      email: `mailto:?subject=${encodedText}&body=${encodeURIComponent(`${text}\n\n${url}`)}`,
    };
    Object.entries(links).forEach(([key, href]) => {
      const node = shareDialog.querySelector(`[data-share-channel="${key}"]`);
      if (node) node.href = href;
    });
    const copy = shareDialog.querySelector('[data-share-channel="copy"]');
    if (copy) copy.dataset.copyUrl = url;
    shareDialog.showModal();
    return;
  }

  if (navigator.share) {
    navigator.share({ title: text, url }).catch(() => {});
  }
}

function showNotice(action) {
  if (!noticeDialog) return;
  const title = noticeDialog.querySelector("#notice-title");
  const copy = noticeDialog.querySelector("#notice-copy");

  const messages = {
    subscribe: [
      "AIEO Brief subscriptions are next",
      "The interface is ready for subscriptions. The next community layer will store consent, preferences, and subscription behavior in the AIEO research data model. You can receive the current Monthly Pulse now.",
    ],
    follow: [
      "Story notifications are next",
      "This option will notify you when the same development returns, gains new source coverage, or changes relationship pattern. Account-based follows will be stored as first-party behavioral data.",
    ],
    discuss: [
      "Discussion is next",
      "Comments and replies will attach to this living development, so the conversation stays with the story when new coverage appears.",
    ],
    like: [
      "Reactions are next",
      "Likes and other reactions will become part of the first-party engagement layer used for transparent popularity rankings.",
    ],
    save: [
      "Saved stories are next",
      "Saving will be account-based so collections and reading behavior can persist across devices.",
    ],
  };
  const message = messages[action] || ["Coming next", "This interaction is reserved for the community phase."];
  if (title) title.textContent = message[0];
  if (copy) copy.textContent = message[1];
  noticeDialog.showModal();
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (button) {
    const action = button.dataset.action;
    if (action === "share") {
      const title = button.dataset.shareTitle || document.title;
      const url = button.dataset.shareUrl || window.location.href;

      if (
        navigator.share &&
        window.matchMedia("(max-width: 760px)").matches
      ) {
        try {
          await navigator.share({ title, url: absoluteUrl(url) });
          return;
        } catch (_) {}
      }
      openShare(title, url);
      return;
    }

    if (["subscribe","follow","discuss","like","save"].includes(action)) {
      showNotice(action);
      return;
    }
  }

  const copyButton = event.target.closest('[data-share-channel="copy"]');
  if (copyButton) {
    const value = copyButton.dataset.copyUrl || window.location.href;
    try {
      await navigator.clipboard.writeText(value);
      const old = copyButton.textContent;
      copyButton.textContent = "✓ Copied";
      setTimeout(() => { copyButton.textContent = old; }, 1500);
    } catch (_) {
      window.prompt("Copy this link", value);
    }
  }
});

const storyGrid = document.getElementById("story-grid");
const searchInput = document.getElementById("story-search");
const showMore = document.getElementById("show-more-stories");
const status = document.getElementById("story-count-status");
let activeFilter = "all";
let visibleLimit = 6;

function filteredCards() {
  if (!storyGrid) return [];
  const query = (searchInput?.value || "").trim().toLowerCase();
  return [...storyGrid.querySelectorAll("[data-story-card]")].filter((card) => {
    const relationship = card.dataset.relationship;
    const early = card.dataset.early === "true";
    const filterMatch =
      activeFilter === "all" ||
      (activeFilter === "early" && early) ||
      relationship === activeFilter;
    const searchMatch =
      !query || (card.dataset.search || "").includes(query);
    return filterMatch && searchMatch;
  });
}

function renderCards() {
  if (!storyGrid) return;
  const matches = filteredCards();
  const allCards = [...storyGrid.querySelectorAll("[data-story-card]")];

  allCards.forEach((card) => {
    const shouldMatch = matches.includes(card);
    const index = matches.indexOf(card);
    card.hidden = !shouldMatch || index >= visibleLimit;
    card.classList.remove("is-extra");
  });

  const ad = storyGrid.querySelector(".feed-ad");
  if (ad) {
    ad.classList.toggle("visible", matches.length > 6 && visibleLimit > 6);
  }

  const shown = Math.min(visibleLimit, matches.length);
  if (status) {
    status.textContent = `${shown} of ${matches.length} shown`;
  }
  if (showMore) {
    showMore.hidden = shown >= matches.length;
    showMore.textContent = `Show ${Math.min(6, matches.length - shown)} more`;
  }
}

document.querySelectorAll("[data-story-filter]").forEach((button) => {
  button.addEventListener("click", () => {
    activeFilter = button.dataset.storyFilter;
    visibleLimit = 6;
    document.querySelectorAll("[data-story-filter]").forEach((node) => {
      node.classList.toggle("active", node === button);
    });
    renderCards();
  });
});

searchInput?.addEventListener("input", () => {
  visibleLimit = 6;
  renderCards();
});

showMore?.addEventListener("click", () => {
  visibleLimit += 6;
  renderCards();
});

renderCards();
