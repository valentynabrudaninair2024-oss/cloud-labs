// Main load profile of the Library API: every virtual reader does 1 write and 9 reads per loop.
//   VUS=45 ./loadtest/run.sh <label>
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.1.0/index.js';

const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const VUS = parseInt(__ENV.VUS || '30', 10);
const THINK = parseFloat(__ENV.THINK || '0.3');
const LABEL = __ENV.LABEL || 'run';

const cacheHit = new Rate('cache_hit');

export const options = {
  scenarios: {
    readers: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: __ENV.RAMP_UP || '3m', target: VUS },
        { duration: __ENV.STEADY || '5m', target: VUS },
        { duration: __ENV.RAMP_DOWN || '2m', target: 0 },
      ],
      gracefulRampDown: '10s',
    },
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(95)', 'p(99)', 'max'],
  thresholds: { http_req_failed: ['rate<0.01'] },
};

const JSON_HEADERS = { 'Content-Type': 'application/json' };
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

function getStats() {
  const r = http.get(`${BASE_URL}/stats`, { tags: { name: 'GET /stats' } });
  return r.status === 200 ? r.json() : null;
}

export function setup() {
  return { start: getStats(), startedAt: Date.now() };
}

export default function () {
  // 1 write: a new branch
  const phone = `+${__VU}${__ITER}${Math.floor(Math.random() * 1e6)}`.slice(0, 20);
  const created = http.post(`${BASE_URL}/libraries`, JSON.stringify({
    name: `Load branch ${__VU}-${__ITER}`, address: `вул. Навантажувальна, ${__VU}`, city: 'Львів', phone,
  }), { headers: JSON_HEADERS, tags: { name: 'POST /libraries' } });
  check(created, { 'create 201': (r) => r.status === 201 });
  const newId = created.status === 201 ? created.json('id') : null;
  sleep(THINK);

  // 4 reads of the branch list (the cached endpoint)
  let ids = [];
  for (let i = 0; i < 4; i++) {
    const list = http.get(`${BASE_URL}/libraries`, { tags: { name: 'GET /libraries' } });
    check(list, { 'list 200': (r) => r.status === 200 });
    cacheHit.add(list.headers['X-Cache'] === 'HIT');
    if (list.status === 200 && ids.length === 0) ids = list.json().map((l) => l.id);
    sleep(THINK);
  }
  if (ids.length === 0 && newId) ids = [newId];
  if (ids.length === 0) return;

  // 1 read of the branch just created (read-your-write, not cached)
  if (newId) {
    const own = http.get(`${BASE_URL}/libraries/${newId}`, { tags: { name: 'GET /libraries/{id}' } });
    check(own, { 'own 200': (r) => r.status === 200 });
    sleep(THINK);
  }

  // 2 random branches
  for (let i = 0; i < 2; i++) {
    const r = http.get(`${BASE_URL}/libraries/${pick(ids)}`, { tags: { name: 'GET /libraries/{id}' } });
    check(r, { 'branch 200': (x) => x.status === 200 });
    sleep(THINK);
  }

  // 2 branch catalogues (join holdings + books)
  for (let i = 0; i < 2; i++) {
    const r = http.get(`${BASE_URL}/libraries/${pick(ids)}/books`, { tags: { name: 'GET /libraries/{id}/books' } });
    check(r, { 'catalogue 200': (x) => x.status === 200 });
    sleep(THINK);
  }
}

export function teardown(data) {
  const end = getStats();
  if (!data.start || !end) return;
  const seconds = (Date.now() - data.startedAt) / 1000;
  const d = (k) => end.db[k] - data.start.db[k];
  console.log(JSON.stringify({
    duration_s: Math.round(seconds),
    db_queries: d('Questions'),
    db_queries_per_s: +(d('Questions') / seconds).toFixed(1),
    db_selects: d('Com_select'),
    db_inserts: d('Com_insert'),
    cache_enabled: end.cache.enabled,
    cache_hits: (end.cache.hits || 0) - (data.start.cache.hits || 0),
    cache_misses: (end.cache.misses || 0) - (data.start.cache.misses || 0),
  }));
}

export function handleSummary(data) {
  const m = data.metrics;
  const dur = data.state.testRunDurationMs / 1000;
  const short = {
    label: LABEL,
    base_url: BASE_URL,
    vus: VUS,
    requests: m.http_reqs.values.count,
    rps: +(m.http_reqs.values.count / dur).toFixed(1),
    error_rate: m.http_req_failed.values.rate,
    p50_ms: +m.http_req_duration.values.med.toFixed(1),
    p95_ms: +m.http_req_duration.values['p(95)'].toFixed(1),
    p99_ms: +m.http_req_duration.values['p(99)'].toFixed(1),
    cache_hit_rate: m.cache_hit ? m.cache_hit.values.rate : null,
  };
  return {
    stdout: textSummary(data, { indent: ' ', enableColors: true }) + '\n\nSUMMARY ' + JSON.stringify(short) + '\n',
    [`results/${LABEL}.json`]: JSON.stringify({ summary: short, k6: data }, null, 2),
  };
}
