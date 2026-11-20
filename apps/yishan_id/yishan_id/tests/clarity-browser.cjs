// Set NODE_PATH to an installation of playwright-core with its matching Chromium.
// Download only the two public scripts. Map ALL Chromium hosts to a loopback TLS sink
// so the decoded POST and request headers are exactly what was transmitted on the wire.
const {chromium} = require('playwright-core');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const {readFileSync, mkdtempSync, rmSync} = require('node:fs');
const https = require('node:https');
const {tmpdir} = require('node:os');
const path = require('node:path');
const {gunzipSync} = require('node:zlib');

const site = 'https://bizbase.geokeji.com';
const usage = '/_usage/file-share/view';
const project = 'uy7jcuzycs';
const tagURL = `https://www.clarity.ms/tag/${project}`;
const assets = '/assets/yishan_id/';
const asset = name => readFileSync(path.join(__dirname, '../public', name));
const getScript = url => execFileSync('rtk', ['proxy', 'curl', '--disable', '--fail', '--silent', '--show-error', '--max-time', '25', url]);
const tag = getScript(tagURL);
const coreURL = tag.toString().match(/https:\/\/scripts\.clarity\.ms\/[a-z\d.-]+\/clarity\.js/)[0];
const scripts = new Map([[tagURL, tag], [coreURL, getScript(coreURL)]]);
const collect = tag.toString().match(/https:\/\/[a-z]+\.clarity\.ms\/collect/)[0];
const bad = ['SyntheticEmployeeCanary', 'SyntheticDocumentCanary', 'SyntheticTokenCanary', 'SyntheticFragmentCanary'];
const parentURL = `${site}/desk/form/${bad[1]}?token=${bad[2]}#${bad[3]}`;
const policy = `frame-ancestors ${site}; sandbox allow-scripts`;
const vendor = [], uploads = [], errors = [];
let child = site + usage, sandbox, referrer, frameName, direct, testOriginGuard;

async function serve(req, res) {
  const url = new URL(req.url, `https://${req.headers.host}`);
  const send = (type, body, headers = {}) => {
    res.writeHead(200, {'content-type':type, 'cache-control':'no-store', ...headers});
    res.end(body);
  };
  if (url.hostname.endsWith('.clarity.ms')) {
    vendor.push([req.method, url.href, req.headers]);
    if (scripts.has(url.href)) return send('text/javascript', scripts.get(url.href));
    if (url.href === collect && req.method === 'POST') {
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      let body = Buffer.concat(chunks);
      if (body[0] === 31 && body[1] === 139) body = gunzipSync(body);
      uploads.push(JSON.parse(body.toString()));
      res.writeHead(204, {'access-control-allow-origin':'null','access-control-allow-credentials':'true'});
      return res.end();
    }
  } else if (!direct && (url.pathname === '/source' || url.pathname === `/desk/form/${bad[1]}`)) {
    const html = `<title>${bad[0]}</title><p>${bad[0]}</p><iframe credentialless sandbox="${sandbox}" name="${frameName}" referrerpolicy="${referrer}" tabindex="-1" aria-hidden="true" style="width:1px;height:1px;pointer-events:none" src="${child}"></iframe>`;
    return send('text/html', html);
  } else if (['clarity-page.js', 'clarity-features.js'].some(name => url.pathname === assets + name)) {
    return send('text/javascript', asset(path.basename(url.pathname)));
  } else if (url.pathname.startsWith('/_usage/') || url.pathname === assets + 'clarity-page.html') {
    return send('text/html', asset('clarity-page.html'), {'referrer-policy':'no-referrer',
      'content-security-policy':testOriginGuard ? `frame-ancestors ${site}` : policy});
  }
  res.writeHead(404); res.end();
}

(async () => {
  const tmp = mkdtempSync(path.join(tmpdir(), 'clarity-tls-'));
  let server, browser;
  try {
    execFileSync('rtk', ['proxy','openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=synthetic.invalid',
      '-keyout',path.join(tmp,'key'),'-out',path.join(tmp,'cert')], {stdio:'ignore'});
    server = https.createServer({key:readFileSync(path.join(tmp,'key')),cert:readFileSync(path.join(tmp,'cert'))},
      (req,res) => serve(req,res).catch(error => {errors.push(error.message);res.destroy();}));
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    browser = await chromium.launch({args:['--no-proxy-server','--disable-quic',`--host-resolver-rules=MAP * 127.0.0.1:${server.address().port}`]});
    const context = await browser.newContext({ignoreHTTPSErrors:true});
    await context.addCookies([{name:'SyntheticVendorCookie', value:bad[2], domain:'.clarity.ms', path:'/', secure:true, sameSite:'None'}]);
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    sandbox = 'allow-scripts'; referrer = 'no-referrer'; frameName = '';
    await page.goto(parentURL);
    const frame = page.frames()[1];
    const state = await frame.evaluate(() => ({origin, referrer:document.referrer,
      readable: (() => {try {return !!parent.document;} catch {return false;}})()}));
    assert.deepEqual(state, {origin:'null', referrer:'', readable:false});
    for (let i=0; !uploads.some(batch => batch.p?.length) && i<100; i++) await page.waitForTimeout(100);
    await page.goto('about:blank'); // Include any final frame beacon in the assertions.
    console.log('Chromium', browser.version(), coreURL, vendor.map(r => r.slice(0,2)), errors);
    if (process.env.CLARITY_DEBUG) console.log(JSON.stringify([vendor,uploads]));
    assert.deepEqual(errors, []);
    assert.ok(uploads.length, 'official script must send a collect POST');
    for (const {e} of uploads) {
      assert.equal(e[4], project);
      if (e.length >= 12) assert.equal(e[11], site + usage);
    }
    assert.ok(uploads.some(({e}) => e[11] === site + usage));
    assert.equal(new Set(uploads.map(({e}) => JSON.stringify(e.slice(4, 8)))).size, 1,
      'all upload batches must belong to one SDK page view');
    const consent = uploads.flatMap(batch => batch.a || []).filter(event => event[1] === 47);
    assert.ok(consent.length && consent.every(event => event[3] === 0 && event[4] === 0));
    const replay = JSON.stringify(uploads.flatMap(batch => batch.p || []));
    for (const marker of ['BODY', 'TITLE', 'Feature usage']) assert.ok(replay.includes(marker), 'missing isolated DOM ' + marker);
    for (const [,url,hs] of vendor) {
      assert.ok(!hs.referer); assert.ok(!hs.cookie, `unexpected vendor Cookie at ${url}`);
      assert.ok(scripts.has(url) || url === collect);
    }
    assert.ok(vendor.some(([method,url,hs]) => method === 'POST' && url === collect && hs.origin === 'null'));
    for (const secret of bad) assert.ok(!JSON.stringify([vendor, uploads]).includes(secret));

    for (const [name, opts] of Object.entries({
      direct:{direct:true}, query:{path:usage+'?token=X'}, hash:{path:usage+'#X'}, emptyQuery:{path:usage+'?'}, emptyHash:{path:usage+'#'},
      record:{path:'/_usage/desk/form/synthetic-id-1937'}, arbitrary:{path:'/_usage/unknown'}, asset:{path:assets+'clarity-page.html'},
      wrongSite:{site:'https://preview.invalid'}, foreignParent:{parent:'https://preview.invalid/source'}, named:{frameName:bad[2]},
      encoded:{path:'/_usage/file-share/%76iew'}, referrer:{policy:'unsafe-url'}, sameOrigin:{sandbox:'allow-scripts allow-same-origin'},
    })) {
      vendor.length = 0; direct = !!opts.direct; sandbox = opts.sandbox || 'allow-scripts'; referrer = opts.policy || 'no-referrer';
      child = (opts.site || site) + (opts.path || usage); frameName = opts.frameName || ''; testOriginGuard = !!opts.sandbox;
      await page.goto(direct ? child : (opts.parent || parentURL));
      assert.equal(vendor.length, 0, `${name} contacted vendor`);
    }
    console.log('PASS: decoded collect, isolated replay, no credential/referrer/canaries, all 14 negative cases');
  } finally {
    if (browser) await browser.close();
    if (server) server.close();
    rmSync(tmp,{recursive:true,force:true});
  }
})().catch(e => {console.error(e);process.exitCode=1;});
