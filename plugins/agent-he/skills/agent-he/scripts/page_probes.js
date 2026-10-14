/*
 * In-page probes for pass two of a heuristic evaluation.
 *
 * Measurements come from the page, never from a screenshot.
 * A cropped screenshot lies about scale, crop and device
 * pixel ratio; getBoundingClientRect() does not.
 *
 * Paste this whole file into the page context once (a
 * Runtime.evaluate, a javascript_tool call, or the console),
 * then call the individual probes. Each returns plain JSON.
 *
 *   agentHE.viewport()
 *   agentHE.hitTargets()
 *   agentHE.tabOrder()
 *   agentHE.mediaState()
 *   agentHE.centering('main')
 *   agentHE.spacing('.rail .mark')
 *   agentHE.emptyState('.list')
 *   agentHE.headings()
 *   agentHE.all()
 *
 * Keep each call SHORT. A long evaluate can die with the
 * renderer when a large media fetch is in flight; re-read
 * state in a separate call rather than one that has to
 * survive the fetch.
 */

(function (global) {
  "use strict";

  var INTERACTIVE =
    'a[href], button, input, select, textarea, summary, ' +
    '[tabindex]:not([tabindex="-1"]), [role="button"], [role="link"], ' +
    "[contenteditable]:not([contenteditable=false])";

  // WCAG 2.5.8 Target Size (Minimum), AA.
  var MIN_TARGET = 24;

  function round(value) {
    return Math.round(value * 100) / 100;
  }

  function rect(element) {
    var box = element.getBoundingClientRect();
    return {
      x: round(box.x),
      y: round(box.y),
      width: round(box.width),
      height: round(box.height)
    };
  }

  function label(element) {
    var text =
      element.getAttribute("aria-label") ||
      (element.textContent || "").trim() ||
      element.getAttribute("title") ||
      element.getAttribute("alt") ||
      element.getAttribute("placeholder") ||
      "";
    return text.replace(/\s+/g, " ").slice(0, 80);
  }

  function describe(element) {
    var box = rect(element);
    var style = global.getComputedStyle(element);
    var classes = null;
    if (typeof element.className === "string") {
      classes = element.className;
    }
    return {
      tag: element.tagName.toLowerCase(),
      id: element.id || null,
      className: classes,
      label: label(element),
      width: box.width,
      height: box.height,
      x: box.x,
      y: box.y,
      opacity: style.opacity,
      visibility: style.visibility,
      display: style.display
    };
  }

  function visible(element) {
    var box = element.getBoundingClientRect();
    if (box.width === 0 && box.height === 0) {
      return false;
    }
    var style = global.getComputedStyle(element);
    if (style.visibility === "hidden" || style.display === "none") {
      return false;
    }
    return true;
  }

  var api = {};

  /* The real viewport. Compare against any screenshot before
   * trusting a measurement taken from an image. */
  api.viewport = function () {
    return {
      innerWidth: global.innerWidth,
      innerHeight: global.innerHeight,
      devicePixelRatio: global.devicePixelRatio,
      documentWidth: document.documentElement.scrollWidth,
      documentHeight: document.documentElement.scrollHeight,
      horizontalOverflow:
        document.documentElement.scrollWidth > global.innerWidth,
      scrollY: global.scrollY
    };
  };

  /* Every interactive element smaller than 24x24 CSS px.
   * WCAG 2.5.8 (AA). Report the count and the denominator. */
  api.hitTargets = function (selector) {
    var nodes = Array.prototype.slice.call(
      document.querySelectorAll(selector || INTERACTIVE)
    );
    var measured = nodes.map(describe);
    var undersized = measured.filter(function (item) {
      return item.width < MIN_TARGET || item.height < MIN_TARGET;
    });
    return {
      minimum: MIN_TARGET,
      total: measured.length,
      undersized: undersized.length,
      items: undersized.slice(0, 100)
    };
  };

  /* Document tab order, in order, with sizes. Count the
   * stops that precede the primary control. */
  api.tabOrder = function () {
    var nodes = Array.prototype.slice
      .call(document.querySelectorAll(INTERACTIVE))
      .filter(function (element) {
        if (element.disabled) {
          return false;
        }
        return visible(element) || element.tabIndex >= 0;
      });
    var stops = nodes.map(function (element, index) {
      var item = describe(element);
      item.index = index;
      item.tabIndex = element.tabIndex;
      return item;
    });
    return {
      count: stops.length,
      tinyStops: stops.filter(function (item) {
        return item.width < MIN_TARGET || item.height < MIN_TARGET;
      }).length,
      stops: stops.slice(0, 200)
    };
  };

  /* Real media state. The control is a claim; this is the
   * observation. Read it AFTER a genuine user-gesture click
   * — a programmatic .play() is blocked by autoplay policy
   * and measures the browser, not the product. */
  api.mediaState = function (selector) {
    var nodes = Array.prototype.slice.call(
      document.querySelectorAll(selector || "audio, video")
    );
    return {
      count: nodes.length,
      elements: nodes.slice(0, 20).map(function (element, index) {
        var buffered = [];
        var slot;
        for (slot = 0; slot < element.buffered.length; slot += 1) {
          buffered.push([
            round(element.buffered.start(slot)),
            round(element.buffered.end(slot))
          ]);
        }
        var errorCode = null;
        if (element.error) {
          errorCode = element.error.code;
        }
        return {
          index: index,
          src: element.currentSrc || element.src || null,
          preload: element.preload,
          paused: element.paused,
          ended: element.ended,
          currentTime: round(element.currentTime),
          duration: element.duration,
          readyState: element.readyState,
          networkState: element.networkState,
          buffered: buffered,
          error: errorCode
        };
      })
    };
  };

  /* Centering, measured. Do not file an off-centre finding
   * from a screenshot; this is what actually settles it. */
  api.centering = function (selector) {
    var element = document.querySelector(selector);
    if (!element) {
      return { error: "no element for " + selector };
    }
    var box = element.getBoundingClientRect();
    var left = round(box.left);
    var right = round(global.innerWidth - box.right);
    return {
      selector: selector,
      viewportWidth: global.innerWidth,
      elementWidth: round(box.width),
      spaceLeft: left,
      spaceRight: right,
      delta: round(Math.abs(left - right)),
      centred: Math.abs(left - right) <= 1
    };
  };

  /* Gaps between repeated marks. Quantify crowding; do not
   * describe it. */
  api.spacing = function (selector) {
    var nodes = Array.prototype.slice.call(document.querySelectorAll(selector));
    var boxes = nodes
      .map(function (element) {
        return element.getBoundingClientRect();
      })
      .sort(function (first, second) {
        return first.left - second.left;
      });
    var gaps = [];
    var overlaps = 0;
    var index;
    for (index = 1; index < boxes.length; index += 1) {
      var gap = round(boxes[index].left - boxes[index - 1].right);
      gaps.push(gap);
      if (gap < 0) {
        overlaps += 1;
      }
    }
    var under = gaps.filter(function (gap) {
      return gap < MIN_TARGET;
    }).length;
    var markWidth = null;
    if (boxes.length) {
      markWidth = round(boxes[0].width);
    }
    var smallestGap = null;
    if (gaps.length) {
      smallestGap = Math.min.apply(null, gaps);
    }
    return {
      selector: selector,
      count: boxes.length,
      markWidth: markWidth,
      gaps: gaps,
      smallestGap: smallestGap,
      overlappingPairs: overlaps,
      gapsUnderMinimum: under,
      minimum: MIN_TARGET
    };
  };

  /* What a container looks like after a no-match filter.
   * Run it before and after typing a query that matches
   * nothing, and diff the two. */
  api.emptyState = function (selector) {
    var element = document.querySelector(selector);
    if (!element) {
      return { error: "no element for " + selector };
    }
    var box = element.getBoundingClientRect();
    var counters = Array.prototype.slice
      .call(document.querySelectorAll('[role="status"], [aria-live], .count, .counter'))
      .map(function (node) {
        return (node.textContent || "").trim().slice(0, 80);
      });
    return {
      selector: selector,
      height: round(box.height),
      childCount: element.children.length,
      visibleChildren: Array.prototype.slice.call(element.children).filter(visible).length,
      collapsed: box.height === 0,
      textContent: (element.textContent || "").trim().slice(0, 200),
      counters: counters
    };
  };

  /* Heading outline. A jump in level, or no h1, is an H4/H11
   * finding. */
  api.headings = function () {
    return Array.prototype.slice
      .call(document.querySelectorAll("h1, h2, h3, h4, h5, h6"))
      .map(function (element) {
        return {
          level: Number(element.tagName.slice(1)),
          text: (element.textContent || "").trim().replace(/\s+/g, " ").slice(0, 80)
        };
      });
  };

  /* Every link, split into internal and external. Zero
   * external links on a page that cites a source is a
   * finding. */
  api.links = function () {
    var origin = global.location.origin;
    var hrefs = Array.prototype.slice
      .call(document.querySelectorAll("a[href]"))
      .map(function (element) {
        return element.href;
      });
    var external = hrefs.filter(function (href) {
      return href.indexOf(origin) !== 0 && href.indexOf("javascript:") !== 0;
    });
    return {
      total: hrefs.length,
      external: external.length,
      externalHrefs: Array.prototype.slice.call(new Set(external)).slice(0, 50)
    };
  };

  /* A cheap everything-at-once for a first look. Prefer the
   * individual probes when the page is busy. */
  api.all = function () {
    return {
      url: global.location.href,
      viewport: api.viewport(),
      headings: api.headings(),
      hitTargets: api.hitTargets(),
      tabOrder: { count: api.tabOrder().count, tinyStops: api.tabOrder().tinyStops },
      media: { count: document.querySelectorAll("audio, video").length },
      links: api.links()
    };
  };

  global.agentHE = api;
  return api;
})(
  (function () {
    if (typeof window !== "undefined") {
      return window;
    }
    return this;
  })()
);
