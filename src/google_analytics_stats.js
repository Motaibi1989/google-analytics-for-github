#!/usr/bin/env node

/**
 * Google Analytics 4 → GitHub Stats Publisher
 *
 * Reads aggregate GA4 metrics with the Google Analytics Data API and writes
 * public-safe JSON files that can be consumed by GitHub badges, websites,
 * dashboards, or other JavaScript applications.
 */

const fs = require('node:fs/promises');
const path = require('node:path');
const { BetaAnalyticsDataClient } = require('@google-analytics/data');

const ROOT = path.resolve(__dirname, '..');
const STATS_DIR = path.join(ROOT, 'stats');
const DEFAULT_START_DATE = '2020-10-14';

function requiredEnv(name) {
  const value = (process.env[name] || '').trim();
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

function buildClient(serviceAccountJson) {
  let credentials;

  try {
    credentials = JSON.parse(serviceAccountJson);
  } catch (error) {
    throw new Error('GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON', { cause: error });
  }

  return new BetaAnalyticsDataClient({ credentials });
}

async function fetchMetrics(client, propertyId, startDate, endDate, metricNames) {
  const [response] = await client.runReport({
    property: `properties/${propertyId}`,
    dateRanges: [{ startDate, endDate }],
    metrics: metricNames.map((name) => ({ name })),
  });

  const row = response.rows?.[0];
  if (!row) {
    return Object.fromEntries(metricNames.map((name) => [name, 0]));
  }

  return Object.fromEntries(
    metricNames.map((name, index) => {
      const rawValue = row.metricValues?.[index]?.value || '0';
      return [name, Math.trunc(Number(rawValue) || 0)];
    }),
  );
}

async function writeJson(filePath, payload) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

function badge(label, value) {
  return {
    schemaVersion: 1,
    label,
    message: Number(value).toLocaleString('en-US'),
  };
}

async function main() {
  const propertyId = requiredEnv('GA_PROPERTY_ID');
  const serviceAccountJson = requiredEnv('GOOGLE_SERVICE_ACCOUNT_JSON');
  const startDate = (process.env.GA_START_DATE || '').trim() || DEFAULT_START_DATE;

  const client = buildClient(serviceAccountJson);

  const allTime = await fetchMetrics(
    client,
    propertyId,
    startDate,
    'yesterday',
    ['totalUsers', 'screenPageViews'],
  );

  const last30Days = await fetchMetrics(
    client,
    propertyId,
    '30daysAgo',
    'yesterday',
    ['activeUsers', 'sessions', 'screenPageViews'],
  );

  const stats = {
    source: 'Google Analytics 4',
    updated_at_utc: new Date().toISOString(),
    all_time: {
      start_date: startDate,
      end_date: 'yesterday',
      total_users: allTime.totalUsers,
      views: allTime.screenPageViews,
    },
    last_30_days: {
      start_date: '30daysAgo',
      end_date: 'yesterday',
      active_users: last30Days.activeUsers,
      sessions: last30Days.sessions,
      views: last30Days.screenPageViews,
    },
  };

  await Promise.all([
    writeJson(path.join(STATS_DIR, 'stats.json'), stats),
    writeJson(path.join(STATS_DIR, 'badge-total-users.json'), badge('Total users', allTime.totalUsers)),
    writeJson(path.join(STATS_DIR, 'badge-users-30d.json'), badge('Users (30d)', last30Days.activeUsers)),
    writeJson(path.join(STATS_DIR, 'badge-sessions-30d.json'), badge('Sessions (30d)', last30Days.sessions)),
    writeJson(path.join(STATS_DIR, 'badge-views-30d.json'), badge('Views (30d)', last30Days.screenPageViews)),
  ]);

  console.log('Google Analytics statistics updated successfully.');
  console.log(JSON.stringify(stats, null, 2));
}

main().catch((error) => {
  console.error(`Error: ${error.message}`);
  process.exitCode = 1;
});
