(function () {
  function activate(el) {
    var id = el.getAttribute("data-video-id");
    if (!id || el.querySelector("iframe")) return;
    var iframe = document.createElement("iframe");
    iframe.setAttribute("src",
      "https://www.youtube-nocookie.com/embed/" + id + "?autoplay=1&rel=0");
    iframe.setAttribute("title", el.getAttribute("data-title") || "YouTube video");
    iframe.setAttribute("allow",
      "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture");
    iframe.setAttribute("allowfullscreen", "");
    el.innerHTML = "";
    el.appendChild(iframe);
  }
  document.addEventListener("DOMContentLoaded", function () {
    var nodes = document.querySelectorAll(".yt-facade");
    for (var i = 0; i < nodes.length; i++) {
      (function (el) {
        el.addEventListener("click", function () { activate(el); });
        el.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(el); }
        });
      })(nodes[i]);
    }
  });
})();
