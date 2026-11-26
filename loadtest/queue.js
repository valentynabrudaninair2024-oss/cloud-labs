// Write-only profile through the queue: POST /libraries/async at a fixed arrival rate.
//   SCRIPT=queue.js RATE=15 ./loadtest/run.sh queue
import http from 'k6/http';
import { check } from 'k6';
import { Trend } from 'k6/metrics';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.1.0/index.js';

const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const RATE = parseInt(__ENV.RATE || '15', 10);
const LABEL = __ENV.LABEL || 'queue';

const enqueue = new Trend('enqueue_duration', true);

export const options = {
  scenarios: {
    writes: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: 20,
      maxVUs: 200,
      stages: [
        { duration: __ENV.RAMP_UP || '3m', target: RATE },
        { duration: __ENV.STEADY || '5m', target: RATE },
        { duration: __ENV.RAMP_DOWN || '2m', target: 0 },
      ],
    },
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(95)', 'p(99)', 'max'],
  thresholds: { http_req_failed: ['rate<0.01'] },
};

export default function () {
  const body = JSON.stringify({
    name: `Queued branch ${__VU}-${__ITER}`,
    address: `вул. Чергова, ${__VU}`,
    city: 'Львів',
    phone: `+q${__VU}${__ITER}${Math.floor(Math.random() * 1e6)}`.slice(0, 20),
  });
  const res = http.post(`${BASE_URL}/libraries/async`, body, {
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': uuidv4() },
    tags: { name: 'POST /libraries/async' },
  });
  check(res, { 'accepted 202': (r) => r.status === 202 });
  enqueue.add(res.timings.duration);

  if (res.status === 202 && Math.random() < 0.1) {
    const job = http.get(`${BASE_URL}${res.json('status_url')}`, { tags: { name: 'GET /jobs/{id}' } });
    check(job, { 'job 200': (r) => r.status === 200 });
  }
}

export function handleSummary(data) {
  const m = data.metrics;
  const dur = data.state.testRunDurationMs / 1000;
  const short = {
    label: LABEL,
    base_url: BASE_URL,
    rate: RATE,
    requests: m.http_reqs.values.count,
    rps: +(m.http_reqs.values.count / dur).toFixed(1),
    error_rate: m.http_req_failed.values.rate,
    enqueue_p50_ms: +m.enqueue_duration.values.med.toFixed(1),
    enqueue_p95_ms: +m.enqueue_duration.values['p(95)'].toFixed(1),
    enqueue_p99_ms: +m.enqueue_duration.values['p(99)'].toFixed(1),
  };
  return {
    stdout: textSummary(data, { indent: ' ', enableColors: true }) + '\n\nSUMMARY ' + JSON.stringify(short) + '\n',
    [`results/${LABEL}.json`]: JSON.stringify({ summary: short, k6: data }, null, 2),
  };
}
