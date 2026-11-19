(() => {
  'use strict';
  const site = 'https://bizbase.geokeji.com';
  const { href, pathname } = window.location;
  // The mandatory frame-ancestors response header authenticates ancestors on every engine.
  // Chromium additionally exposes their origins here, even with no-referrer.
  const ancestors = location.ancestorOrigins;
  if (window === window.top || window.parent !== window.top || window.origin !== 'null' ||
      document.referrer !== '' || window.name !== '' ||
      (ancestors && (ancestors.length !== 1 || ancestors[0] !== site)) || href !== site + pathname ||
      !window.bizbaseUsageFeatures?.has(pathname)) return;

  window.clarity = function (method, config) {
    // Start in cookieless mode, before the tag consumes its queued consent signal.
    // Switching from track:true after startup would start a second session.
    if (method === 'start') config.track = false;
    (window.clarity.q ||= []).push(arguments);
  };
  window.clarity('consentv2', {ad_Storage: 'denied', analytics_Storage: 'denied'});
  const tag = document.createElement('script');
  tag.referrerPolicy = 'no-referrer';
  tag.src = 'https://www.clarity.ms/tag/uy7jcuzycs';
  document.head.append(tag);
})();
