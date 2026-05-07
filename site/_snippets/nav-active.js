(function(){
  var path = window.location.pathname;
  document.querySelectorAll('.nav-links a').forEach(function(a){
    var href = a.getAttribute('href');
    if (href && href.startsWith('/') && href !== '/' && path.startsWith(href)) {
      a.classList.add('active');
    }
  });
})();
